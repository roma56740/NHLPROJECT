import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.database.schema import (
    DEFAULT_COLLECTIONS,
    DEFAULT_DAILY_LOGIN_LADDER,
    DEFAULT_SEASON_REWARD_TIERS,
    DEFAULT_CLAN_SEASON_REWARD_TIERS,
    DEFAULT_CURRENCIES,
    DEFAULT_CREATOR_LEVEL_SETTINGS,
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
        seed_default_clan_season_reward_tiers(connection)
        seed_default_creator_level_settings(connection)
        migrate_creators_without_zero_level(connection)
        cleanup_legacy_demo_content(connection)
        connection.commit()


def run_migrations(connection: sqlite3.Connection) -> None:
    ensure_column(
        connection=connection,
        table_name="cards",
        column_name="salary",
        column_sql="salary INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        connection=connection,
        table_name="bot_admins",
        column_name="role",
        column_sql="role TEXT NOT NULL DEFAULT 'senior_admin'",
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

    ensure_column(connection=connection, table_name="users", column_name="creator_subscribers", column_sql="creator_subscribers INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="users", column_name="creator_chat_link_sent", column_sql="creator_chat_link_sent INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="users", column_name="creator_author_code", column_sql="creator_author_code TEXT")
    ensure_column(connection=connection, table_name="users", column_name="creator_author_code_percent_bp", column_sql="creator_author_code_percent_bp INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="creator_distributions", column_name="reward_type", column_sql="reward_type TEXT NOT NULL DEFAULT 'legacy'")
    ensure_column(connection=connection, table_name="creator_distributions", column_name="value_coins", column_sql="value_coins INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="creator_distributions", column_name="amount", column_sql="amount INTEGER NOT NULL DEFAULT 1")
    ensure_column(connection=connection, table_name="creator_distributions", column_name="source_item_id", column_sql="source_item_id INTEGER")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_creator_distributions_creator ON creator_distributions(creator_user_id, created_at)")

    ensure_column(connection=connection, table_name="team_divisions", column_name="image_path", column_sql="image_path TEXT")
    ensure_column(connection=connection, table_name="team_divisions", column_name="active", column_sql="active INTEGER NOT NULL DEFAULT 1")
    ensure_column(connection=connection, table_name="animation_assets", column_name="title", column_sql="title TEXT NOT NULL DEFAULT ''")
    ensure_column(connection=connection, table_name="animation_assets", column_name="image_path", column_sql="image_path TEXT NOT NULL DEFAULT ''")
    # legacy season reward tier rename: old 11-50 becomes 11-25
    connection.execute("UPDATE season_reward_tiers SET tier_key = 'T11_25' WHERE tier_key = 'T11_50' AND NOT EXISTS (SELECT 1 FROM season_reward_tiers WHERE tier_key = 'T11_25')")
    # clan wars defense / anti-monopoly settings and migration
    ensure_column(connection=connection, table_name="clan_arenas", column_name="holder_captures_streak", column_sql="holder_captures_streak INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="clan_arenas", column_name="last_holder_clan_id", column_sql="last_holder_clan_id INTEGER")
    ensure_column(connection=connection, table_name="clan_arenas", column_name="protected_until", column_sql="protected_until TEXT")
    ensure_column(connection=connection, table_name="clan_arena_attacks", column_name="defense_points", column_sql="defense_points INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="clan_arena_attacks", column_name="effective_points", column_sql="effective_points INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="clan_seasons", column_name="reset_by_telegram_id", column_sql="reset_by_telegram_id INTEGER")
    connection.execute("UPDATE clan_arena_attacks SET effective_points = points WHERE effective_points = 0 AND points > 0")


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
            INSERT INTO bot_admins (telegram_id, role, active)
            VALUES (?, 'owner', 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                role = 'owner',
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



def seed_default_clan_season_reward_tiers(connection: sqlite3.Connection) -> None:
    for place, coins, rubles, pack_id in DEFAULT_CLAN_SEASON_REWARD_TIERS:
        connection.execute(
            "INSERT INTO clan_season_reward_tiers (place, coins, rubles, pack_id) VALUES (?, ?, ?, ?) ON CONFLICT(place) DO NOTHING",
            (place, coins, rubles, pack_id),
        )


def seed_default_creator_level_settings(connection: sqlite3.Connection) -> None:
    for item in DEFAULT_CREATOR_LEVEL_SETTINGS:
        connection.execute(
            """
            INSERT INTO creator_level_settings (
                level,
                required_subscribers,
                required_distributed_value,
                welcome_coins,
                weekly_coins,
                weekly_elite_packs,
                weekly_legendary_packs,
                weekly_elite_pack_id,
                weekly_legendary_pack_id,
                promo_codes_weekly,
                author_code_percent_bp,
                exclusive_card_rating,
                perks_text,
                personal_rewards_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(level) DO UPDATE SET
                perks_text = CASE WHEN creator_level_settings.perks_text = '' THEN excluded.perks_text ELSE creator_level_settings.perks_text END,
                personal_rewards_text = CASE WHEN creator_level_settings.personal_rewards_text = '' THEN excluded.personal_rewards_text ELSE creator_level_settings.personal_rewards_text END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                item["level"],
                item["required_subscribers"],
                item["required_distributed_value"],
                item["welcome_coins"],
                item["weekly_coins"],
                item["weekly_elite_packs"],
                item["weekly_legendary_packs"],
                item["weekly_elite_pack_id"],
                item["weekly_legendary_pack_id"],
                item["promo_codes_weekly"],
                item["author_code_percent_bp"],
                item["exclusive_card_rating"],
                item["perks_text"],
                item["personal_rewards_text"],
            ),
        )


def migrate_creators_without_zero_level(connection: sqlite3.Connection) -> None:
    """Переводит старые записи креаторов без ранга на 1 уровень и выдаёт welcome-бонус один раз."""
    cfg = connection.execute(
        "SELECT welcome_coins FROM creator_level_settings WHERE level = 1"
    ).fetchone()
    welcome_coins = int(cfg["welcome_coins"] if cfg else 0)

    creators = connection.execute(
        "SELECT id FROM users WHERE is_creator = 1 AND creator_level < 1"
    ).fetchall()

    for creator in creators:
        user_id = int(creator["id"])
        connection.execute(
            "UPDATE users SET creator_level = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        connection.execute(
            "INSERT OR IGNORE INTO creator_inventory (user_id, coins) VALUES (?, 0)",
            (user_id,),
        )
        already_claimed = connection.execute(
            "SELECT id FROM creator_bonus_claims WHERE user_id = ? AND bonus_type = 'welcome' AND level = 1",
            (user_id,),
        ).fetchone()
        if already_claimed or welcome_coins <= 0:
            continue
        connection.execute(
            """
            INSERT INTO creator_bank_items (user_id, item_type, currency_code, quantity, value_per_unit)
            VALUES (?, 'currency', 'coins', ?, 1)
            """,
            (user_id, welcome_coins),
        )
        connection.execute(
            "INSERT OR IGNORE INTO creator_bonus_claims (user_id, bonus_type, level) VALUES (?, 'welcome', 1)",
            (user_id,),
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
