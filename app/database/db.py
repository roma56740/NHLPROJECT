import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.database.schema import (
    DEFAULT_COLLECTIONS,
    DEFAULT_DAILY_LOGIN_LADDER,
    DEFAULT_SEASON_REWARD_TIERS,
    DEFAULT_CURRENCIES,
    DEFAULT_GAME_SETTINGS,
    LEGACY_DEMO_COLLECTION_CODES,
    LEGACY_DEMO_PACK_CODES,
    SCHEMA_QUERIES,
)
from config import settings


DATABASE_PATH: Path = settings.database_path


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


async def init_database() -> None:
    with get_connection() as connection:
        for query in SCHEMA_QUERIES:
            try:
                connection.execute(query)
            except sqlite3.OperationalError as error:
                message = str(error).lower()

                if "target_user_id" in message and "no such column" in message:
                    continue

                raise

        run_migrations(connection)
        seed_main_admins(connection)
        seed_default_game_settings(connection)
        seed_default_currencies(connection)
        seed_default_collections(connection)
        seed_default_daily_login_rewards(connection)
        seed_default_season_reward_tiers(connection)
        cleanup_legacy_demo_content(connection)
        connection.commit()


def run_migrations(connection: sqlite3.Connection) -> None:
    ensure_column(
        connection=connection,
        table_name="cards",
        column_name="salary",
        column_sql="salary INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(connection=connection, table_name="users", column_name="is_creator", column_sql="is_creator INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="users", column_name="creator_level", column_sql="creator_level INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="users", column_name="creator_channel", column_sql="creator_channel TEXT")
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
    ensure_column(
        connection=connection,
        table_name="users",
        column_name="trade_blocked",
        column_sql="trade_blocked INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        connection=connection,
        table_name="trade_offers",
        column_name="target_user_id",
        column_sql="target_user_id INTEGER",
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_target ON trade_offers(target_user_id, status)"
    )


def build_placeholders(values: Sequence[str]) -> str:
    return ", ".join("?" for _ in values)


def cleanup_legacy_demo_content(connection: sqlite3.Connection) -> None:
    """Remove old demo packs/cards that were created by early project versions."""

    if LEGACY_DEMO_PACK_CODES:
        pack_placeholders = build_placeholders(LEGACY_DEMO_PACK_CODES)
        pack_params = list(LEGACY_DEMO_PACK_CODES)

        connection.execute(
            f"""
            DELETE FROM pack_opening_rewards
            WHERE opening_id IN (
                SELECT pack_openings.id
                FROM pack_openings
                JOIN packs ON packs.id = pack_openings.pack_id
                WHERE packs.code IN ({pack_placeholders})
            )
            """,
            pack_params,
        )
        connection.execute(
            f"""
            DELETE FROM pack_openings
            WHERE pack_id IN (SELECT id FROM packs WHERE code IN ({pack_placeholders}))
            """,
            pack_params,
        )
        connection.execute(
            f"DELETE FROM shop_purchases WHERE pack_id IN (SELECT id FROM packs WHERE code IN ({pack_placeholders}))",
            pack_params,
        )
        connection.execute(
            f"DELETE FROM user_packs WHERE pack_id IN (SELECT id FROM packs WHERE code IN ({pack_placeholders}))",
            pack_params,
        )
        connection.execute(
            f"DELETE FROM pack_cards WHERE pack_id IN (SELECT id FROM packs WHERE code IN ({pack_placeholders}))",
            pack_params,
        )
        connection.execute(
            f"DELETE FROM pack_slots WHERE pack_id IN (SELECT id FROM packs WHERE code IN ({pack_placeholders}))",
            pack_params,
        )
        connection.execute(
            f"DELETE FROM packs WHERE code IN ({pack_placeholders})",
            pack_params,
        )

    if LEGACY_DEMO_COLLECTION_CODES:
        collection_placeholders = build_placeholders(LEGACY_DEMO_COLLECTION_CODES)
        collection_params = list(LEGACY_DEMO_COLLECTION_CODES)

        connection.execute(
            f"""
            DELETE FROM cards
            WHERE collection_id IN (SELECT id FROM collections WHERE code IN ({collection_placeholders}))
              AND id NOT IN (SELECT card_id FROM user_cards)
            """,
            collection_params,
        )
        connection.execute(
            f"""
            DELETE FROM collections
            WHERE code IN ({collection_placeholders})
              AND id NOT IN (SELECT collection_id FROM cards)
            """,
            collection_params,
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


def seed_default_season_reward_tiers(connection: sqlite3.Connection) -> None:
    for tier_key, coins, rubles, pack_id in DEFAULT_SEASON_REWARD_TIERS:
        connection.execute(
            "INSERT INTO season_reward_tiers (tier_key, coins, rubles, pack_id) VALUES (?, ?, ?, ?) ON CONFLICT(tier_key) DO NOTHING",
            (tier_key, coins, rubles, pack_id),
        )


def seed_default_daily_login_rewards(connection: sqlite3.Connection) -> None:
    for day, coins, rubles, pack_id in DEFAULT_DAILY_LOGIN_LADDER:
        connection.execute(
            """
            INSERT INTO daily_login_rewards (day, coins, rubles, pack_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(day) DO NOTHING
            """,
            (day, coins, rubles, pack_id),
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
