"""Журнал необработанных/критичных ошибок (раздел 19 ТЗ) — таблица application_errors.

Раньше исключения из хендлеров/фоновых циклов уходили только в logging (в консоль
Railway, откуда их никто не видит без ручного просмотра логов деплоя). Эта таблица
делает последнюю ошибку и их частоту видимой прямо в /diagnostics.

record_error() никогда не бросает исключений — ошибка логирования ошибки не должна
маскировать исходную ошибку или ронять вызывающий код.
"""

from __future__ import annotations

import logging
import sqlite3
import traceback

from app.database.db import get_connection

_logger = logging.getLogger(__name__)


def ensure_error_log_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS application_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            error_type TEXT NOT NULL,
            message TEXT NOT NULL,
            traceback TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_application_errors_created_at ON application_errors(created_at)"
    )


def record_error(source: str, error: BaseException, context: str | None = None) -> None:
    try:
        message = str(error)[:1000]
        if context:
            message = f"[{context}] {message}"[:1000]
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))[:4000]
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO application_errors (source, error_type, message, traceback) VALUES (?, ?, ?, ?)",
                (source, type(error).__name__, message, tb),
            )
            connection.commit()
    except Exception:
        _logger.exception("failed to record application error (source=%s)", source)


def get_recent_errors(limit: int = 5) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(
            connection.execute(
                "SELECT * FROM application_errors ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        )


def count_errors_since_hours(hours: int = 24) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) c FROM application_errors WHERE created_at >= datetime('now', ?)",
            (f"-{int(hours)} hours",),
        ).fetchone()
        return int(row["c"])
