"""Диагностика состояния бота/БД/Volume (раздел 11 ТЗ по надёжности).

Общая логика для команды /diagnostics и периодического health-check —
см. app/services/health_monitor.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import app.database.db as _db_module
from app.database.db import get_connection
from app.services import backups, error_log
from app.services.cache_cleanup import RENDER_CACHE
from app.services.creator_tournaments import find_matches_needing_attention
from app.version import get_started_at

_PROCESS_START_MONOTONIC = time.monotonic()


def _database_path():
    return _db_module.DATABASE_PATH


def uploads_dir():
    """ВАЖНО: railway_boot.py нельзя импортировать как модуль — весь его код верхнего
    уровня выполняется при импорте и заканчивается os.execv(), который заменяет текущий
    процесс. Путь к uploads вычисляется независимо, тем же способом, что и там
    (DATA_UPLOADS = /app/data/uploads = DATABASE_PATH.parent / "uploads")."""
    return _database_path().parent / "uploads"


def media_dir():
    return _database_path().parent / "media"


def format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.1f} {unit}" if unit != "Б" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def format_uptime() -> str:
    seconds = int(time.monotonic() - _PROCESS_START_MONOTONIC)
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"


@dataclass(frozen=True)
class DbHealth:
    ok: bool
    quick_check_result: str
    size_bytes: int
    wal_size_bytes: int


def get_db_health() -> DbHealth:
    database_path = _database_path()
    ok = backups.quick_check(database_path)
    size = database_path.stat().st_size if database_path.exists() else 0
    wal_path = database_path.with_name(database_path.name + "-wal")
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0
    return DbHealth(ok=ok, quick_check_result="ok" if ok else "FAILED", size_bytes=size, wal_size_bytes=wal_size)


@dataclass(frozen=True)
class VolumeHealth:
    free_bytes: int
    total_bytes: int
    used_percent: float
    free_percent: float


def get_volume_health() -> VolumeHealth:
    total, used, free = backups.get_disk_usage()
    used_percent = round(used / total * 100, 1) if total else 0.0
    free_percent = round(free / total * 100, 1) if total else 100.0
    return VolumeHealth(free_bytes=free, total_bytes=total, used_percent=used_percent, free_percent=free_percent)


@dataclass(frozen=True)
class StorageBreakdown:
    database: tuple[int, int]
    uploads: tuple[int, int]
    backups_regular: tuple[int, int]
    backups_predeploy: tuple[int, int]
    render_cache: tuple[int, int]


def get_storage_breakdown() -> StorageBreakdown:
    database_path = _database_path()
    db_count = 1 if database_path.exists() else 0
    db_size = database_path.stat().st_size if database_path.exists() else 0
    return StorageBreakdown(
        database=(db_count, db_size),
        uploads=backups.dir_stats(uploads_dir(), recursive=True),
        backups_regular=backups.dir_stats(backups.backups_dir()),
        backups_predeploy=backups.dir_stats(backups.predeploy_backups_dir()),
        render_cache=backups.dir_stats(RENDER_CACHE, recursive=True),
    )


@dataclass(frozen=True)
class TournamentHealth:
    active_tournaments: int
    matches_playing: int
    stuck_matches: int


async def get_tournament_health() -> TournamentHealth:
    with get_connection() as connection:
        active = connection.execute("SELECT COUNT(*) c FROM creator_tournaments WHERE status='active'").fetchone()["c"]
        playing = connection.execute("SELECT COUNT(*) c FROM creator_tournament_matches WHERE status='playing'").fetchone()["c"]
    stuck = await find_matches_needing_attention()
    return TournamentHealth(active_tournaments=int(active), matches_playing=int(playing), stuck_matches=len(stuck))


@dataclass(frozen=True)
class ErrorsHealth:
    last_error_at: str | None
    last_error_message: str | None
    count_last_24h: int


def get_errors_health() -> ErrorsHealth:
    recent = error_log.get_recent_errors(limit=1)
    last = recent[0] if recent else None
    return ErrorsHealth(
        last_error_at=last["created_at"] if last else None,
        last_error_message=last["message"] if last else None,
        count_last_24h=error_log.count_errors_since_hours(24),
    )


@dataclass(frozen=True)
class DiagnosticsReport:
    uptime: str
    db: DbHealth
    volume: VolumeHealth
    storage: StorageBreakdown
    tournaments: TournamentHealth
    errors: ErrorsHealth
    started_at: str


async def build_diagnostics_report() -> DiagnosticsReport:
    return DiagnosticsReport(
        uptime=format_uptime(),
        db=get_db_health(),
        volume=get_volume_health(),
        storage=get_storage_breakdown(),
        tournaments=await get_tournament_health(),
        errors=get_errors_health(),
        started_at=get_started_at(),
    )


def format_diagnostics_text(report: DiagnosticsReport) -> str:
    db_icon = "✅" if report.db.ok else "🚨"
    lines = [
        "<b>🩺 Диагностика</b>",
        "",
        "Бот: Online",
        f"Uptime: {report.uptime}",
        f"База: {db_icon} {'OK' if report.db.ok else 'ОШИБКА'}",
        f"PRAGMA quick_check: {report.db.quick_check_result}",
        f"Размер базы: {format_bytes(report.db.size_bytes)}",
        f"WAL: {format_bytes(report.db.wal_size_bytes)}",
        "",
        f"Свободно на Volume: {format_bytes(report.volume.free_bytes)}",
        f"Использование Volume: {report.volume.used_percent}%",
        "",
        f"Uploads: {format_bytes(report.storage.uploads[1])}",
        f"Backups: {report.storage.backups_regular[0]} файл(ов) / {format_bytes(report.storage.backups_regular[1])}",
        f"Predeploy backups: {report.storage.backups_predeploy[0]}",
        f"Render cache: {format_bytes(report.storage.render_cache[1])} (вне Volume)",
        "",
        f"Активные турниры: {report.tournaments.active_tournaments}",
        f"Матчи playing: {report.tournaments.matches_playing}",
        f"Зависшие матчи: {report.tournaments.stuck_matches}",
        "",
        f"Ошибок за 24ч: {report.errors.count_last_24h}",
        (
            f"Последняя ошибка: {report.errors.last_error_at} — {report.errors.last_error_message}"
            if report.errors.last_error_at
            else "Последняя ошибка: не зафиксировано."
        ),
    ]
    return "\n".join(lines)
