import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.database.schema import (
    DEFAULT_COLLECTIONS,
    DEFAULT_CURRENCIES,
    DEFAULT_GAME_SETTINGS,
    SCHEMA_QUERIES,
)
from config import settings


DATABASE_PATH: Path = settings.database_path


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


async def init_database() -> None:
    with get_connection() as connection:
        for query in SCHEMA_QUERIES:
            connection.execute(query)

        run_migrations(connection)
        seed_main_admins(connection)
        seed_default_game_settings(connection)
        seed_default_currencies(connection)
        seed_default_collections(connection)
        connection.commit()


def run_migrations(connection: sqlite3.Connection) -> None:
    ensure_column(
        connection=connection,
        table_name="pack_slots",
        column_name="rarity_chances",
        column_sql="rarity_chances TEXT",
    )
    ensure_column(
        connection=connection,
        table_name="match_queue",
        column_name="bot_fallback_at",
        column_sql="bot_fallback_at TEXT",
    )


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    cursor = connection.execute(f"PRAGMA table_info({table_name})")
    columns = {row["name"] for row in cursor.fetchall()}

    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")



def seed_default_game_settings(connection: sqlite3.Connection) -> None:
    for item in DEFAULT_GAME_SETTINGS:
        connection.execute(
            """
            INSERT INTO game_settings (key, value, title, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                title = excluded.title,
                description = excluded.description
            """,
            (
                item["key"],
                item["value"],
                item["title"],
                item["description"],
            ),
        )


def seed_main_admins(connection: sqlite3.Connection) -> None:
    for telegram_id in settings.admin_ids:
        connection.execute(
            """
            INSERT INTO bot_admins (telegram_id, active)
            VALUES (?, 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id,),
        )


def seed_default_currencies(connection: sqlite3.Connection) -> None:
    for currency in DEFAULT_CURRENCIES:
        connection.execute(
            """
            INSERT INTO currencies (code, name, icon, description, active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                icon = excluded.icon,
                description = excluded.description,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                currency["code"],
                currency["name"],
                currency["icon"],
                currency["description"],
            ),
        )


def seed_default_collections(connection: sqlite3.Connection) -> None:
    for collection in DEFAULT_COLLECTIONS:
        connection.execute(
            """
            INSERT INTO collections (code, name, description, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                collection["code"],
                collection["name"],
                collection["description"],
            ),
        )


async def fetch_one(query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    with get_connection() as connection:
        cursor = connection.execute(query, params)
        return cursor.fetchone()


async def fetch_all(query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    with get_connection() as connection:
        cursor = connection.execute(query, params)
        return list(cursor.fetchall())


async def execute(query: str, params: Sequence[Any] = ()) -> None:
    with get_connection() as connection:
        connection.execute(query, params)
        connection.commit()


async def execute_many(query: str, params: Iterable[Sequence[Any]]) -> None:
    with get_connection() as connection:
        connection.executemany(query, params)
        connection.commit()
