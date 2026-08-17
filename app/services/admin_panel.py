from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from app.database.db import DATABASE_PATH, get_connection
from app.texts.admin_panel import AdminListItem, AdminSummary
from app.services import audit_log
from app.services.admin_permissions import ADMIN_ROLE_OWNER, ADMIN_ROLE_SENIOR, ADMIN_ROLE_CONTENT, get_admin_role_title, normalize_admin_role
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
        AdminListItem(
            telegram_id=telegram_id,
            source="main",
            active=True,
            role=ADMIN_ROLE_OWNER,
            role_title=get_admin_role_title(ADMIN_ROLE_OWNER),
        )
        for telegram_id in sorted(main_admin_ids)
    ]

    with get_connection() as connection:
        if not _table_exists(connection, "bot_admins"):
            return admins

        rows = connection.execute(
            """
            SELECT telegram_id, active, role, created_at
            FROM bot_admins
            WHERE active = 1
            ORDER BY created_at DESC, telegram_id ASC
            """
        ).fetchall()

    for row in rows:
        telegram_id = int(row["telegram_id"])
        if telegram_id in main_admin_ids:
            continue
        role = normalize_admin_role(row["role"] if "role" in row.keys() else ADMIN_ROLE_SENIOR)
        admins.append(
            AdminListItem(
                telegram_id=telegram_id,
                source="panel",
                active=bool(row["active"]),
                role=role,
                role_title=get_admin_role_title(role),
                added_at=row["created_at"],
            )
        )

    return admins


async def add_admin(telegram_id: int, added_by_telegram_id: int | None, role: str = ADMIN_ROLE_CONTENT) -> None:
    role = normalize_admin_role(role)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO bot_admins (telegram_id, added_by_telegram_id, role, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                active = 1,
                role = excluded.role,
                added_by_telegram_id = excluded.added_by_telegram_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, added_by_telegram_id, role),
        )
        audit_log.record(connection, added_by_telegram_id, 'admin_added', 'bot_admin', telegram_id, {'role': role})
        connection.commit()


async def update_admin_role(telegram_id: int, role: str, actor_user_id: int | None = None) -> bool:
    if telegram_id in set(settings.admin_ids):
        return False

    role = normalize_admin_role(role)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE bot_admins
            SET role = ?,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            """,
            (role, telegram_id),
        )
        if cursor.rowcount > 0:
            audit_log.record(connection, actor_user_id, 'admin_role_changed', 'bot_admin', telegram_id, {'role': role})
        connection.commit()
        return cursor.rowcount > 0


async def remove_admin(telegram_id: int, actor_user_id: int | None = None) -> bool:
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
        if cursor.rowcount > 0:
            audit_log.record(connection, actor_user_id, 'admin_removed', 'bot_admin', telegram_id)
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


def _safe_archive_part(value: str | None, fallback: str = "Без названия") -> str:
    text = (value or "").strip() or fallback
    for bad_char in '<>:"/\\|?*':
        text = text.replace(bad_char, " ")
    text = " ".join(text.replace("\n", " ").replace("\r", " ").split())
    text = text.strip(" .")
    return text or fallback


def _safe_archive_filename(value: str | None, fallback: str = "file") -> str:
    return _safe_archive_part(value, fallback=fallback).replace(" ", "_")


def _build_card_archive_path(row: sqlite3.Row, file_path: Path) -> str:
    collection = _safe_archive_part(row["collection_name"], "Без коллекции")
    position = _safe_archive_part(row["position"], "Без позиции")
    rarity = _safe_archive_part(row["rarity"], "Без редкости")
    card_name = _safe_archive_filename(row["name"], "card")
    team = _safe_archive_filename(row["team"], "team")
    country = _safe_archive_filename(row["country"], "country")
    card_id = int(row["id"])
    overall = int(row["overall"])
    suffix = file_path.suffix or ".jpg"

    file_name = f"ID_{card_id}_OVR_{overall}_{rarity}_{card_name}_{team}_{country}{suffix}"
    return f"Карты/{collection}/{position}/OVR_{overall:02d}/{file_name}"


def _load_card_image_rows() -> dict[str, list[sqlite3.Row]]:
    with get_connection() as connection:
        if not _table_exists(connection, "cards") or not _table_exists(connection, "collections"):
            return {}

        rows = connection.execute(
            """
            SELECT
                cards.id,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                collections.name AS collection_name
            FROM cards
            LEFT JOIN collections ON collections.id = cards.collection_id
            WHERE TRIM(cards.image_path) != ''
            ORDER BY
                collections.name COLLATE NOCASE ASC,
                CASE cards.position
                    WHEN 'G' THEN 1
                    WHEN 'D' THEN 2
                    WHEN 'F' THEN 3
                    ELSE 4
                END ASC,
                cards.overall DESC,
                cards.name COLLATE NOCASE ASC,
                cards.id ASC
            """
        ).fetchall()

    card_rows: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        image_path = str(row["image_path"] or "").replace("\\", "/").lstrip("/")
        if not image_path:
            continue
        card_rows.setdefault(image_path, []).append(row)
        card_rows.setdefault(Path(image_path).as_posix(), []).append(row)
        card_rows.setdefault(Path(image_path).name, []).append(row)
    return card_rows


def _find_card_rows(card_rows: dict[str, list[sqlite3.Row]], file_path: Path) -> list[sqlite3.Row]:
    normalized_path = file_path.as_posix()
    relative_upload_path = file_path.relative_to(UPLOADS_DIR).as_posix()
    candidates = (
        normalized_path,
        relative_upload_path,
        f"assets/uploads/{relative_upload_path}",
        file_path.name,
    )

    result: list[sqlite3.Row] = []
    seen_ids: set[int] = set()
    for candidate in candidates:
        for row in card_rows.get(candidate, []):
            row_id = int(row["id"])
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            result.append(row)
    return result


def _build_upload_archive_path(file_path: Path) -> str:
    relative_path = file_path.relative_to(UPLOADS_DIR)
    first_part = relative_path.parts[0] if relative_path.parts else "other"

    folder_titles = {
        "packs": "Паки",
        "team_logos": "Логотипы команд",
        "events": "События",
    }

    if first_part in folder_titles:
        rest = Path(*relative_path.parts[1:]).as_posix() if len(relative_path.parts) > 1 else file_path.name
        return f"{folder_titles[first_part]}/{rest}"

    if first_part == "cards":
        return f"Карты/Без карточки в базе/{file_path.name}"

    return f"Другие изображения/{relative_path.as_posix()}"


def create_uploads_archive() -> Path | None:
    if not UPLOADS_DIR.exists():
        return None

    files = sorted(
        [path for path in UPLOADS_DIR.rglob("*") if path.is_file()],
        key=lambda path: path.as_posix().lower(),
    )
    if not files:
        return None

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = EXPORTS_DIR / f"nhl_bot_uploads_{timestamp}.zip"
    card_rows = _load_card_image_rows()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.txt",
            "Архив изображений NHL Card Bot.\n"
            "Карты разложены по папкам: Карты / коллекция / позиция / OVR.\n"
            "Изображения паков, событий и логотипов команд лежат в отдельных папках.\n",
        )
        added_names: set[str] = {"README.txt"}

        for file_path in files:
            rows = _find_card_rows(card_rows, file_path) if "cards" in file_path.parts else []

            if rows:
                for row in rows:
                    archive_name = _build_card_archive_path(row, file_path)
                    if archive_name in added_names:
                        archive_name = f"Карты/Повторы/{int(row['id'])}_{file_path.name}"
                    archive.write(file_path, archive_name)
                    added_names.add(archive_name)
                continue

            archive_name = _build_upload_archive_path(file_path)
            if archive_name in added_names:
                archive_name = f"Другие изображения/Повторы/{file_path.name}"
            archive.write(file_path, archive_name)
            added_names.add(archive_name)

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
