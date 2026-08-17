"""Версия сборки бота (раздел 10 ТЗ по надёжности). Обновляется вручную при релизе —
отдельного механизма генерации из git нет (проект без git в этой рабочей копии)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2026.08.17-r15-render-cache-volume-fix-safe"

_STARTED_AT = datetime.now(timezone.utc)


def get_commit() -> str:
    commit = os.getenv("RAILWAY_GIT_COMMIT_SHA", "").strip()
    return commit[:7] if commit else "unknown"


def get_build_time() -> str:
    try:
        mtime = Path(__file__).stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    except OSError:
        return "unknown"


def get_started_at() -> str:
    return _STARTED_AT.strftime("%d.%m.%Y %H:%M UTC")


def get_environment() -> str:
    return (
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("ENVIRONMENT")
        or "local"
    )


def build_version_text() -> str:
    from app.database.db import DATABASE_PATH
    from app.services.backups import SCHEMA_VERSION

    lines = [
        f"Версия: {VERSION}",
        f"Commit: {get_commit()}",
        f"Build time: {get_build_time()}",
        f"Started at: {get_started_at()}",
        f"Environment: {get_environment()}",
        "Database: SQLite",
        f"Database path: {DATABASE_PATH}",
        f"Migration version: {SCHEMA_VERSION}",
        f"Volume path: {DATABASE_PATH.parent}",
    ]
    return "\n".join(lines)
