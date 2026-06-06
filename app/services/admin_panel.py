from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from app.database.db import DATABASE_PATH, get_connection
from app.texts.admin_panel import AdminListItem, AdminSummary
from config import settings

EXPORTS_DIR = Path("data/exports")
UPLOADS_DIR = Path("assets/uploads")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _count_rows(connection: sqlite3.Connection, table_name: str, where: str = "", params: tuple = ()) -> int:
    if not _table_exists(connection, table_name):
        return 0

    query = f"SELECT COUNT(*) AS count FROM {table_name}"
    if where:
        query += f" WHERE {where}"

    row = connection.execute(query, params).fetchone()
    return int(row["count"] if row else 0)


async def get_admin_summary() -> AdminSummary:
    with get_connection() as connection:
        return AdminSummary(
            users_count=_count_rows(connection, "users"),
            cards_count=_count_rows(connection, "cards"),
            packs_count=_count_rows(connection, "packs"),
            matches_count=_count_rows(connection, "matches"),
            open_trades_count=_count_rows(connection, "trade_offers", "status = ?", ("open",)),
            clans_count=_count_rows(connection, "clans", "active = 1"),
            active_quests_count=_count_rows(connection, "quests", "active = 1"),
            active_passes_count=_count_rows(connection, "hockey_passes", "active = 1"),
            active_admins_count=len(await list_active_admins()),
        )


async def list_active_admins() -> list[AdminListItem]:
    main_admin_ids = set(settings.admin_ids)
    admins: list[AdminListItem] = [
        AdminListItem(telegram_id=telegram_id, source="main", active=True)
        for telegram_id in sorted(main_admin_ids)
    ]

    with get_connection() as connection:
        if not _table_exists(connection, "bot_admins"):
            return admins

        rows = connection.execute(
            """
            SELECT telegram_id, active, created_at
            FROM bot_admins
            WHERE active = 1
            ORDER BY created_at DESC, telegram_id ASC
            """
        ).fetchall()

    for row in rows:
        telegram_id = int(row["telegram_id"])
        if telegram_id in main_admin_ids:
            continue
        admins.append(
            AdminListItem(
                telegram_id=telegram_id,
                source="panel",
                active=bool(row["active"]),
                added_at=row["created_at"],
            )
        )

    return admins


async def add_admin(telegram_id: int, added_by_telegram_id: int | None) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO bot_admins (telegram_id, added_by_telegram_id, active)
            VALUES (?, ?, 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                active = 1,
                added_by_telegram_id = excluded.added_by_telegram_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, added_by_telegram_id),
        )
        connection.commit()


async def remove_admin(telegram_id: int) -> bool:
    if telegram_id in set(settings.admin_ids):
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE bot_admins
            SET active = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ? AND active = 1
            """,
            (telegram_id,),
        )
        connection.commit()
        return cursor.rowcount > 0


def is_main_admin(telegram_id: int) -> bool:
    return telegram_id in set(settings.admin_ids)


def create_database_backup_file() -> Path | None:
    if not DATABASE_PATH.exists():
        return None

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = EXPORTS_DIR / f"nhl_bot_database_{timestamp}.sqlite3"

    source = sqlite3.connect(DATABASE_PATH)
    try:
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    return backup_path


def create_uploads_archive() -> Path | None:
    if not UPLOADS_DIR.exists():
        return None

    files = [path for path in UPLOADS_DIR.rglob("*") if path.is_file()]
    if not files:
        return None

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = EXPORTS_DIR / f"nhl_bot_uploads_{timestamp}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, file_path.as_posix())

    return archive_path


def cleanup_export_file(path: Path | None) -> None:
    if path is None:
        return

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_old_exports(keep_latest: int = 10) -> None:
    if not EXPORTS_DIR.exists():
        return

    files = sorted(
        [path for path in EXPORTS_DIR.iterdir() if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for file_path in files[keep_latest:]:
        cleanup_export_file(file_path)
