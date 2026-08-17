import logging
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


logger = logging.getLogger(__name__)

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

        from app.services.stronghold_seed import seed_stronghold_content
        seed_stronghold_content(connection)

        from app.services.war2_seed import seed_war2_content
        seed_war2_content(connection)

        from app.services.ranked_seed import seed_ranked_content
        seed_ranked_content(connection)

        from app.services.dna_crafting import seed_dna_content
        seed_dna_content(connection)

        connection.commit()


def run_migrations(connection: sqlite3.Connection) -> None:
    from app.database.migrations import ensure_migrations_table, run_once
    from app.services.audit_log import ensure_audit_log_table
    from app.services.error_log import ensure_error_log_table
    from app.services.creator_tournaments import migrate_creator_tournaments

    ensure_migrations_table(connection)
    run_once(connection, "0001_create_audit_log", ensure_audit_log_table)
    run_once(connection, "0002_create_application_errors", ensure_error_log_table)

    migrate_creator_tournaments(connection)
    ensure_column(
        connection=connection,
        table_name="cards",
        column_name="salary",
        column_sql="salary INTEGER NOT NULL DEFAULT 0",
    )
    run_once(connection, "0007_cards_allow_ovr_100", migrate_cards_allow_ovr_100)
    run_once(connection, "0008_cards_allow_ovr_110", migrate_cards_allow_ovr_110)
    run_once(connection, "0009_creator_weekly_claim_periods", migrate_creator_weekly_claim_periods)
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
    # PACK OPENING VIDEO V9: one admin-uploaded opening video per regular pack.
    # Stored under assets/uploads (Railway volume symlink), so it survives deploys.
    ensure_column(
        connection=connection,
        table_name="packs",
        column_name="animation_video_path",
        column_sql="animation_video_path TEXT",
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
    # GLOBAL COSMETICS V10.2: every owned cosmetic copy is a tradable inventory
    # instance. trade_locked is used by moderation/future operations; equipped or
    # card-bound copies are additionally excluded by transactional checks.
    ensure_column(
        connection=connection,
        table_name="user_cosmetic_items",
        column_name="trade_locked",
        column_sql="trade_locked INTEGER NOT NULL DEFAULT 0",
    )
    # Existing trade_offers.wanted_type has a legacy CHECK(cards/currency). Keep it
    # untouched for safe Railway migrations and distinguish card-vs-cosmetic wanted
    # assets with this backward-compatible discriminator.
    ensure_column(
        connection=connection,
        table_name="trade_offers",
        column_name="wanted_asset_type",
        column_sql="wanted_asset_type TEXT NOT NULL DEFAULT 'cards'",
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

    # CLAN WAR 2.0 (раздел 1.9 плана): различает BASE_COLLECTION (доступна для Draft
    # Pool/Clone War) и EXCLUSIVE_COLLECTION (паки/инвентарь/Wild Card). По умолчанию 0
    # (base) — новые коллекции без явного флага остаются доступными для дро-пула.
    ensure_column(
        connection=connection,
        table_name="collections",
        column_name="is_exclusive",
        column_sql="is_exclusive INTEGER NOT NULL DEFAULT 0",
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
    # RANKED MODE (раздел 0 плана): матчмейкинг делится на 'normal'/'ranked' в одной
    # таблице очереди — по умолчанию 'normal', существующее поведение не меняется.
    ensure_column(connection=connection, table_name="match_queue", column_name="mode", column_sql="mode TEXT NOT NULL DEFAULT 'normal'")

    # RANKED SHOOTOUT MINI-GAME V10.8: persist regulation score, the visible
    # shootout score and every 4-corner attempt. Existing rows remain ordinary
    # non-shootout matches through safe defaults.
    ensure_column(connection=connection, table_name="ranked_matches", column_name="is_shootout", column_sql="is_shootout INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="ranked_matches", column_name="regulation_user_score", column_sql="regulation_user_score INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="ranked_matches", column_name="regulation_opponent_score", column_sql="regulation_opponent_score INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="ranked_matches", column_name="shootout_user_goals", column_sql="shootout_user_goals INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="ranked_matches", column_name="shootout_opponent_goals", column_sql="shootout_opponent_goals INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="ranked_matches", column_name="shootout_log_json", column_sql="shootout_log_json TEXT NOT NULL DEFAULT '[]'")

    migrate_cosmetic_catalog_shared_types(connection)

    # BLACK MARKET: нужна общая точка активности пользователя для таргетинга
    # уведомлений "активные за последние N дней" — раньше в проекте не было
    # ни одного такого поля (каждая фича хранила свой локальный таймстамп).
    ensure_column(connection=connection, table_name="users", column_name="last_active_at", column_sql="last_active_at TEXT")

    from app.services.black_market_admin import seed_black_market_defaults
    run_once(connection, "0003_black_market_seed_defaults", seed_black_market_defaults)

    # BLACK MARKET: поля, добавленные при аудите после первого релиза (раздел 3/6/9
    # ТЗ аудита) — ensure_column, т.к. на уже развёрнутых базах CREATE TABLE IF NOT
    # EXISTS их не добавит. Значения по умолчанию сохраняют старое поведение как есть.
    ensure_column(connection=connection, table_name="black_market_settings", column_name="shop_enabled", column_sql="shop_enabled INTEGER NOT NULL DEFAULT 1")
    ensure_column(connection=connection, table_name="black_market_settings", column_name="last_notified_business_date", column_sql="last_notified_business_date TEXT")
    ensure_column(connection=connection, table_name="black_market_pool_items", column_name="personal_purchase_limit", column_sql="personal_purchase_limit INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="black_market_pool_items", column_name="available_from", column_sql="available_from TEXT")
    ensure_column(connection=connection, table_name="black_market_pool_items", column_name="available_until", column_sql="available_until TEXT")
    ensure_column(connection=connection, table_name="black_market_pool_items", column_name="allow_repeat_in_rotation", column_sql="allow_repeat_in_rotation INTEGER NOT NULL DEFAULT 0")

    from app.services.black_market_admin import seed_black_market_notification_baseline
    run_once(connection, "0004_black_market_notification_baseline", seed_black_market_notification_baseline)

    # STRONGHOLD GLOBAL TOWER SCHEDULE: единое расписание открытия крепостей (башен),
    # см. app/services/stronghold_schedule.py. fortress_unlock_started_at NULL по
    # умолчанию — компьютится как COALESCE(fortress_unlock_started_at, starts_at) на
    # каждый расчёт, поэтому уже идущий сезон автоматически "восстанавливает" сколько
    # башен должно быть открыто, без отдельного backfill UPDATE.
    ensure_column(connection=connection, table_name="stronghold_events", column_name="fortress_unlock_started_at", column_sql="fortress_unlock_started_at TEXT")
    ensure_column(connection=connection, table_name="stronghold_events", column_name="fortress_unlock_interval_seconds", column_sql="fortress_unlock_interval_seconds INTEGER NOT NULL DEFAULT 86400")
    ensure_column(connection=connection, table_name="stronghold_events", column_name="fortress_unlock_timezone", column_sql="fortress_unlock_timezone TEXT NOT NULL DEFAULT 'UTC'")
    ensure_column(connection=connection, table_name="stronghold_events", column_name="manual_unlock_override_count", column_sql="manual_unlock_override_count INTEGER NOT NULL DEFAULT 0")

    # PACK OPENING VIDEO (rework): метаданные загруженного видео + флаг включения
    # анимации на пак (см. app/services/packs.py, app/handlers/packs.py).
    ensure_column(connection=connection, table_name="packs", column_name="animation_enabled", column_sql="animation_enabled INTEGER NOT NULL DEFAULT 1")
    ensure_column(connection=connection, table_name="packs", column_name="animation_duration_seconds", column_sql="animation_duration_seconds INTEGER")
    ensure_column(connection=connection, table_name="packs", column_name="animation_file_size", column_sql="animation_file_size INTEGER")
    ensure_column(connection=connection, table_name="packs", column_name="animation_uploaded_at", column_sql="animation_uploaded_at TEXT")
    ensure_column(connection=connection, table_name="packs", column_name="animation_uploaded_by", column_sql="animation_uploaded_by INTEGER")
    ensure_column(connection=connection, table_name="packs", column_name="animation_file_id", column_sql="animation_file_id TEXT")
    ensure_column(connection=connection, table_name="packs", column_name="animation_file_unique_id", column_sql="animation_file_unique_id TEXT")


    # Current-project arena clan wars: defense, anti-monopoly and clan-season migration.
    ensure_column(connection=connection, table_name="clan_arenas", column_name="holder_captures_streak", column_sql="holder_captures_streak INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="clan_arenas", column_name="last_holder_clan_id", column_sql="last_holder_clan_id INTEGER")
    ensure_column(connection=connection, table_name="clan_arenas", column_name="protected_until", column_sql="protected_until TEXT")
    ensure_column(connection=connection, table_name="clan_arena_attacks", column_name="defense_points", column_sql="defense_points INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="clan_arena_attacks", column_name="effective_points", column_sql="effective_points INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection=connection, table_name="clan_seasons", column_name="reset_by_telegram_id", column_sql="reset_by_telegram_id INTEGER")
    connection.execute("UPDATE clan_arena_attacks SET effective_points = points WHERE effective_points = 0 AND points > 0")

    # ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: player_match_locks/partial unique index уже
    # создаются идемпотентно через SCHEMA_QUERIES (CREATE TABLE/INDEX IF NOT
    # EXISTS) выше по стеку вызовов (init_database()). Здесь — одноразовый перенос
    # уже существующих строк active_matches, см. docstring функции.
    run_once(connection, "0006_migrate_active_matches_to_player_match_locks", migrate_active_matches_to_player_match_locks)




def migrate_creator_weekly_claim_periods(connection: sqlite3.Connection) -> None:
    """Allow one automatic creator payout per payout period, forever.

    The legacy unique index used (user_id, bonus_type, level).  That made the
    second weekly payout at the same creator level fail with UNIQUE constraint,
    so automation could only work once per level.  Keep welcome bonuses unique
    per level, but key weekly claims by a stable period_key instead.
    """
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(creator_bonus_claims)").fetchall()}
    if "period_key" not in columns:
        connection.execute("ALTER TABLE creator_bonus_claims ADD COLUMN period_key TEXT NOT NULL DEFAULT ''")

    # Give legacy weekly rows distinct synthetic periods so no historical claim
    # is lost and the new weekly uniqueness constraint can be created safely.
    connection.execute(
        "UPDATE creator_bonus_claims SET period_key = 'legacy:' || id "
        "WHERE bonus_type = 'weekly' AND COALESCE(period_key, '') = ''"
    )

    connection.execute("DROP INDEX IF EXISTS idx_creator_bonus_claims_unique")
    connection.execute("DROP INDEX IF EXISTS idx_creator_bonus_claims_weekly_unique")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_bonus_claims_unique "
        "ON creator_bonus_claims(user_id, bonus_type, level) WHERE bonus_type = 'welcome'"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_bonus_claims_weekly_unique "
        "ON creator_bonus_claims(user_id, bonus_type, period_key) WHERE bonus_type = 'weekly'"
    )

def migrate_cards_allow_ovr_100(connection: sqlite3.Connection) -> None:
    """Expand cards.overall CHECK from 99 to 100 without touching card IDs.

    SQLite cannot ALTER a CHECK constraint in place.  The parent table is rebuilt
    with foreign keys temporarily disabled; child tables keep referencing the table
    name ``cards`` and all IDs/data remain unchanged.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
    ).fetchone()
    if row is None:
        return
    sql = str(row["sql"] or "")
    normalized = sql.replace(" ", "").lower()
    if "between1and100" in normalized or "between1and110" in normalized:
        return

    # PRAGMA foreign_keys can only be changed outside an active transaction.
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("DROP TABLE IF EXISTS cards__ovr100")
        connection.execute(
            """
            CREATE TABLE cards__ovr100 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                player_key TEXT NOT NULL,
                position TEXT NOT NULL CHECK(position IN ('G', 'D', 'F')),
                overall INTEGER NOT NULL CHECK(overall BETWEEN 1 AND 100),
                team TEXT NOT NULL,
                country TEXT NOT NULL,
                collection_id INTEGER NOT NULL,
                rarity TEXT NOT NULL CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')),
                image_path TEXT NOT NULL,
                salary INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE RESTRICT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cards__ovr100
                (id, name, player_key, position, overall, team, country, collection_id,
                 rarity, image_path, salary, active, created_at, updated_at)
            SELECT id, name, player_key, position, overall, team, country, collection_id,
                   rarity, image_path, salary, active, created_at, updated_at
            FROM cards
            """
        )
        connection.execute("DROP TABLE cards")
        connection.execute("ALTER TABLE cards__ovr100 RENAME TO cards")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_player_key ON cards(player_key)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_collection_id ON cards(collection_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_active ON cards(active)")
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            f"cards OVR100 migration produced foreign-key violations: {len(violations)}"
        )


def migrate_cards_allow_ovr_110(connection: sqlite3.Connection) -> None:
    """Expand cards.overall CHECK to 1..110 while preserving IDs and relations."""
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
    ).fetchone()
    if row is None:
        return
    sql = str(row["sql"] or "")
    normalized = sql.replace(" ", "").lower()
    if "between1and110" in normalized:
        return

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("DROP TABLE IF EXISTS cards__ovr110")
        connection.execute(
            """
            CREATE TABLE cards__ovr110 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                player_key TEXT NOT NULL,
                position TEXT NOT NULL CHECK(position IN ('G', 'D', 'F')),
                overall INTEGER NOT NULL CHECK(overall BETWEEN 1 AND 110),
                team TEXT NOT NULL,
                country TEXT NOT NULL,
                collection_id INTEGER NOT NULL,
                rarity TEXT NOT NULL CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')),
                image_path TEXT NOT NULL,
                salary INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE RESTRICT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cards__ovr110
                (id, name, player_key, position, overall, team, country, collection_id,
                 rarity, image_path, salary, active, created_at, updated_at)
            SELECT id, name, player_key, position, overall, team, country, collection_id,
                   rarity, image_path, salary, active, created_at, updated_at
            FROM cards
            """
        )
        connection.execute("DROP TABLE cards")
        connection.execute("ALTER TABLE cards__ovr110 RENAME TO cards")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_player_key ON cards(player_key)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_collection_id ON cards(collection_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_active ON cards(active)")
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            f"cards OVR110 migration produced foreign-key violations: {len(violations)}"
        )



def migrate_active_matches_to_player_match_locks(connection: sqlite3.Connection) -> None:
    """ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: переносит уже существующие строки старой
    `active_matches` (PRIMARY KEY user_id — максимум одна строка на пользователя,
    конфликтов по построению быть не может) в новую `player_match_locks`, откуда
    их теперь читает app.services.match_guard.

    Ничего не начисляется и не списывается — переносится только сам факт "у
    пользователя был/есть активный матч", а является ли он ещё реально активным,
    решает уже существующая логика recover_stale_matches() (вызывается при
    старте бота, см. main.py) по тем же правилам, что и для любого другого
    зависшего lock'а: сначала проверяется реальная запись матча, и только если
    она отсутствует/завершена — lock закрывается. `active_matches` НЕ удаляется
    и не изменяется (история сохраняется, раздел ТЗ "без удаления пользовательских
    данных"). Идемпотентно за счёт `run_once()`-реестра миграций — этот код
    выполнится ровно один раз для конкретной базы.
    """
    from app.services.match_guard import DEFAULT_TTL_SECONDS

    rows = connection.execute("SELECT user_id, started_at FROM active_matches").fetchall()
    migrated = 0
    skipped_conflict = 0

    for row in rows:
        user_id = int(row["user_id"])
        started_at = row["started_at"] or "1970-01-01 00:00:00"

        existing_active = connection.execute(
            """
            SELECT id FROM player_match_locks
            WHERE user_id = ? AND status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING')
            """,
            (user_id,),
        ).fetchone()
        if existing_active is not None:
            # Не должно происходить на пустой новой таблице, но если произошло —
            # не создаём конфликтующую запись вслепую, помечаем для диагностики.
            skipped_conflict += 1
            logger.warning(
                "migrate_active_matches_to_player_match_locks: user_id=%s already has an active "
                "player_match_locks row (id=%s) — skipped legacy active_matches row for manual diagnostics",
                user_id, existing_active["id"],
            )
            continue

        try:
            connection.execute(
                """
                INSERT INTO player_match_locks
                    (user_id, match_id, match_type, status, request_id, acquired_at, heartbeat_at, expires_at, release_reason)
                VALUES (?, NULL, 'legacy_migrated', 'ACTIVE', NULL, ?, ?, datetime(?, ?), NULL)
                """,
                (user_id, started_at, started_at, started_at, f"+{DEFAULT_TTL_SECONDS} seconds"),
            )
            migrated += 1
        except sqlite3.IntegrityError as error:
            skipped_conflict += 1
            logger.warning(
                "migrate_active_matches_to_player_match_locks: failed to migrate user_id=%s: %s", user_id, error
            )

    logger.warning(
        "migrate_active_matches_to_player_match_locks: report — found=%d migrated=%d skipped_for_manual_diagnostics=%d",
        len(rows), migrated, skipped_conflict,
    )


def migrate_cosmetic_catalog_shared_types(connection: sqlite3.Connection) -> None:
    """RANKED MODE: каталог косметики war2_cosmetic_items изначально создавался только
    для CLAN WAR 2.0 (CHECK type IN FRAME/BACKGROUND/NICK_BADGE). Ranked Mode добавляет
    CARD_FRAME/PROFILE_BACKGROUND/TITLE — CHECK-ограничение SQLite нельзя ALTER'ом,
    только пересозданием таблицы. Название таблицы намеренно НЕ меняется (осталось
    war2_cosmetic_items) — это избегает пересборки user_cosmetic_items.cosmetic_item_id
    FK (которая по имени ссылается на эту же таблицу и продолжает работать без
    изменений после DROP+CREATE с тем же именем). На новых базах CREATE_WAR2_COSMETIC_ITEMS_TABLE
    уже создаёт таблицу сразу с полным списком типов — эта функция реально что-то
    делает только на базах, где таблица была создана до Ranked Mode."""
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'war2_cosmetic_items'"
    ).fetchone()
    if row is None or "CARD_FRAME" in (row["sql"] or ""):
        return  # таблицы ещё нет (создастся сразу актуальной) или уже мигрирована

    connection.execute(
        """
        CREATE TABLE war2_cosmetic_items__rebuild (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('FRAME', 'BACKGROUND', 'NICK_BADGE', 'CARD_FRAME', 'PROFILE_BACKGROUND', 'TITLE')),
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            rarity TEXT NOT NULL CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')) DEFAULT 'Common',
            image_path TEXT,
            badge_text TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        "INSERT INTO war2_cosmetic_items__rebuild "
        "(id, type, code, title, description, rarity, image_path, badge_text, active, created_at, updated_at) "
        "SELECT id, type, code, title, description, rarity, image_path, badge_text, active, created_at, updated_at "
        "FROM war2_cosmetic_items"
    )
    connection.execute("DROP TABLE war2_cosmetic_items")
    connection.execute("ALTER TABLE war2_cosmetic_items__rebuild RENAME TO war2_cosmetic_items")


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
