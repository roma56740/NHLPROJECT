"""Общий журнал критичных действий (раздел 18 ТЗ по надёжности) — таблица audit_log.

Отдельно от `creator_tournament_logs` (специфичен турнирному движку, остаётся как есть) —
этот журнал общий для всего бота: выдача/снятие роли администратора, backup/очистка
кэша из /diagnostics, и (через `_log()` в creator_tournaments.py) дублирует турнирные
действия сюда же, чтобы у критичных операций был один общий след независимо от модуля.
"""

from __future__ import annotations

import json
import sqlite3

from app.database.db import get_connection


def ensure_audit_log_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_user_id)"
    )


def record(
    connection: sqlite3.Connection,
    actor_user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict | str | None = None,
) -> None:
    """Пишет строку в audit_log в РАМКАХ уже открытой транзакции `connection` —
    вызывающий код сам решает, когда коммитить (см. `_log()` в creator_tournaments.py)."""
    if isinstance(details, dict):
        details_text = json.dumps(details, ensure_ascii=False)
    else:
        details_text = details
    connection.execute(
        "INSERT INTO audit_log (actor_user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)",
        (actor_user_id, action, entity_type, entity_id, details_text),
    )


def record_committed(
    actor_user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict | str | None = None,
) -> None:
    """Удобный вариант для мест без уже открытой транзакции (например, кнопки
    /diagnostics) — открывает свою короткую транзакцию и сразу коммитит."""
    with get_connection() as connection:
        record(connection, actor_user_id, action, entity_type, entity_id, details)
        connection.commit()


def recent(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(
            connection.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        )
