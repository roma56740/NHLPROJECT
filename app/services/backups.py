"""Ротация резервных копий БД (раздел 13 ТЗ по надёжности).

Директории — на persistent Railway Volume, рядом с основной базой (см. раздел 12 ТЗ):
    data/backups            — обычные/ежедневные backup, retention см. RETENTION
    data/predeploy_backups  — backup перед миграцией, retention 1

Порядок в create_backup() соблюдён буквально по ТЗ: проверить базу -> удалить старые
копии сверх лимита -> проверить место -> создать -> проверить целостность нового backup.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import app.database.db as _db_module

# ВАЖНО: пути вычисляются функциями, а не замороженными на импорте константами —
# `from app.database.db import DATABASE_PATH` захватил бы значение один раз при первом
# импорте модуля и не увидел бы более поздние переопределения (в т.ч. monkeypatch в
# тестах, где DATABASE_PATH подменяется на временный файл per-test).


def _database_path() -> Path:
    return _db_module.DATABASE_PATH


def backups_dir() -> Path:
    return _database_path().parent / "backups"


def predeploy_backups_dir() -> Path:
    return _database_path().parent / "predeploy_backups"


def state_file() -> Path:
    return _database_path().parent / "backup_state.json"

# Простой ручной счётчик схемы — растёт при значимых изменениях schema.py/миграций
# турниров. Полноценная таблица database_migrations с checksum (раздел 17 ТЗ) — Этап 3;
# этого счётчика достаточно, чтобы не создавать predeploy backup на каждый restart с
# неизменной схемой (требование раздела 13 ТЗ).
SCHEMA_VERSION = 3

RETENTION: dict[str, int] = {"manual": 2, "daily": 1, "predeploy": 1}

FREE_SPACE_WARN_PCT = 30.0
FREE_SPACE_CLEAN_CACHE_PCT = 20.0
FREE_SPACE_DELETE_BACKUPS_PCT = 15.0
FREE_SPACE_STOP_PCT = 10.0


@dataclass(frozen=True)
class BackupResult:
    success: bool
    message: str
    path: Path | None = None


def _dir_for(kind: str) -> Path:
    return predeploy_backups_dir() if kind == "predeploy" else backups_dir()


def quick_check(path: Path) -> bool:
    """PRAGMA quick_check — True только если explicitно вернулось 'ok'."""
    if not path.exists():
        return False
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            return bool(row) and str(row[0]).strip().lower() == "ok"
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def get_disk_usage(path: Path | None = None) -> tuple[int, int, int]:
    """(total, used, free) в байтах для диска, на котором лежит path (по умолчанию — DATABASE_PATH)."""
    target = path or _database_path().parent
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    return usage.total, usage.used, usage.free


def free_space_percent(path: Path | None = None) -> float:
    total, _used, free = get_disk_usage(path)
    if total <= 0:
        return 100.0
    return round(free / total * 100, 1)


def list_backups(kind: str) -> list[Path]:
    directory = _dir_for(kind)
    if not directory.exists():
        return []
    return sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix == ".sqlite3"),
        key=lambda p: p.stat().st_mtime,
    )


def dir_stats(path: Path, recursive: bool = False) -> tuple[int, int]:
    """(количество файлов, суммарный размер в байтах)."""
    if not path.exists():
        return 0, 0
    files = [p for p in (path.rglob("*") if recursive else path.iterdir()) if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def _enforce_retention(kind: str, keep: int) -> int:
    files = list_backups(kind)
    removed = 0
    while len(files) > max(keep, 0):
        oldest = files.pop(0)
        try:
            oldest.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _read_state() -> dict:
    path = state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict) -> None:
    try:
        path = state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def should_create_predeploy_backup() -> bool:
    return int(_read_state().get("schema_version", -1)) != SCHEMA_VERSION


def mark_predeploy_backup_done() -> None:
    state = _read_state()
    state["schema_version"] = SCHEMA_VERSION
    state["last_predeploy_backup_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    _write_state(state)


def create_backup(kind: Literal["manual", "daily", "predeploy"] = "manual") -> BackupResult:
    """См. докстринг модуля для порядка шагов. Не бросает исключений — всегда BackupResult."""
    if kind == "predeploy" and not should_create_predeploy_backup():
        return BackupResult(True, "Версия схемы не изменилась — predeploy backup не требуется.", None)

    database_path = _database_path()

    # 1) проверить базу
    if not database_path.exists():
        return BackupResult(False, "База данных не найдена — backup невозможен.", None)
    if not quick_check(database_path):
        return BackupResult(False, "PRAGMA quick_check основной базы вернул ошибку — backup остановлен для безопасности.", None)

    # 2) удалить старые копии сверх лимита (место под новую копию)
    _enforce_retention(kind, max(RETENTION.get(kind, 1) - 1, 0))

    # 3) проверить свободное место
    free_pct = free_space_percent()
    if free_pct < FREE_SPACE_STOP_PCT:
        return BackupResult(False, f"Недостаточно места на диске ({free_pct}% свободно) — backup остановлен.", None)

    # 4) создать новый backup
    # ВАЖНО: временная метка — с точностью до микросекунд. При секундном разрешении
    # (%Y%m%d_%H%M%S) два backup, созданных в пределах одной секунды, получали бы
    # ИДЕНТИЧНОЕ имя файла и второй молча перезаписывал первый вместо создания отдельной
    # копии — retention считал бы файлы корректно, но копий физически стало бы меньше,
    # чем ожидается. Поймано тестом test_manual_backup_retention_keeps_only_last_two.
    directory = _dir_for(kind)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = directory / f"nhl_bot_{kind}_{timestamp}.sqlite3"

    try:
        source = sqlite3.connect(database_path)
        try:
            destination = sqlite3.connect(backup_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
    except sqlite3.Error as error:
        return BackupResult(False, f"Ошибка при создании backup: {error}", None)

    # 5) проверить backup через PRAGMA quick_check
    if not quick_check(backup_path):
        try:
            backup_path.unlink()
        except OSError:
            pass
        return BackupResult(False, "Новый backup не прошёл проверку целостности и был удалён.", None)

    _enforce_retention(kind, RETENTION.get(kind, 1))

    if kind == "predeploy":
        mark_predeploy_backup_done()

    return BackupResult(True, f"Backup создан: {backup_path.name}", backup_path)


def delete_backups_over_limit(kind: str = "manual") -> int:
    """Ручная очистка (кнопка "🗑 Удалить старые бэкапы" в диагностике/админке)."""
    return _enforce_retention(kind, RETENTION.get(kind, 1))
