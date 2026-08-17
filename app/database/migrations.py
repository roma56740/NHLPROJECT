"""Реестр выполненных миграций (раздел 17 ТЗ по надёжности) — таблица database_migrations.

Существующие ~30 вызовов ensure_column() в app/database/db.py:run_migrations() НЕ
переписаны под этот реестр: они уже идемпотентны сами по себе (PRAGMA table_info +
условный ALTER TABLE), годами проверены в проде без git как страховки, и переписывание
ради единообразия не стоило бы риска регрессии в файле, который трогает активные
турниры/карты/валюту игроков. Реестр предназначен для НОВЫХ структурных изменений
(начиная с этой сессии) и даёт видимость в /diagnostics и /version, что именно было
применено и когда — раньше такой видимости не было вообще.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable


def ensure_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS database_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def has_run(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM database_migrations WHERE name = ?", (name,)
    ).fetchone()
    return row is not None


def mark_run(connection: sqlite3.Connection, name: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO database_migrations (name) VALUES (?)", (name,)
    )


def run_once(
    connection: sqlite3.Connection,
    name: str,
    migration: Callable[[sqlite3.Connection], None],
) -> bool:
    """Выполняет migration(connection) один раз — только если `name` ещё не в реестре.

    Возвращает True, если миграция реально выполнилась в этом вызове (для логирования).
    """
    if has_run(connection, name):
        return False
    migration(connection)
    mark_run(connection, name)
    return True


def list_applied(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            "SELECT name, applied_at FROM database_migrations ORDER BY applied_at"
        ).fetchall()
    )
