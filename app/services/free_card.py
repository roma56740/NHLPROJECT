from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.database.db import get_connection

FREE_CARD_COLLECTION_SETTING_KEY = "free_card_collection_code"  # legacy, kept for old DBs
FREE_CARD_COLLECTIONS_SETTING_KEY = "free_card_collection_codes"
FREE_CARD_COOLDOWN_SETTING_KEY = "free_card_cooldown_hours"
FREE_CARD_DEFAULT_COLLECTION_CODE = "free-cards"
FREE_CARD_DEFAULT_COOLDOWN_HOURS = 6
FREE_CARD_NOTIFICATION_LIMIT = 50
FREE_CARD_NOTIFICATION_SLEEP_SECONDS = 300


@dataclass(frozen=True)
class FreeCardCollection:
    id: int
    code: str
    name: str
    description: str
    active: bool
    active_cards_count: int


@dataclass(frozen=True)
class FreeCardStatus:
    collection: FreeCardCollection | None
    cooldown_hours: int
    is_ready: bool
    remaining_seconds: int
    last_claimed_at: str | None
    collections: list[FreeCardCollection] = field(default_factory=list)


@dataclass(frozen=True)
class FreeCardReward:
    user_card_id: int
    card_id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    image_path: str
    next_ready_at: str


@dataclass(frozen=True)
class FreeCardNotificationTarget:
    user_id: int
    telegram_id: int


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def normalize_collection_query(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def normalize_collection_codes(value: str | None) -> list[str]:
    parts = str(value or "").replace(";", ",").replace("\n", ",").split(",")
    result: list[str] = []
    for part in parts:
        code = part.strip()
        if code and code not in result:
            result.append(code)
    return result


def encode_collection_codes(codes: list[str]) -> str:
    return ",".join(dict.fromkeys(code.strip() for code in codes if code and code.strip()))


def clamp_cooldown_hours(value: object | None) -> int:
    try:
        hours = int(str(value or "").strip())
    except ValueError:
        return FREE_CARD_DEFAULT_COOLDOWN_HOURS
    if hours < 1:
        return FREE_CARD_DEFAULT_COOLDOWN_HOURS
    if hours > 168:
        return 168
    return hours


def row_to_collection(row) -> FreeCardCollection | None:
    if row is None:
        return None
    return FreeCardCollection(
        id=int(row["id"]),
        code=str(row["code"]),
        name=str(row["name"]),
        description=str(row["description"] or ""),
        active=bool(row["active"]),
        active_cards_count=int(row["active_cards_count"] or 0),
    )


def get_setting_value(connection, key: str, default: str) -> str:
    cursor = connection.execute("SELECT value FROM game_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row is None:
        return default
    value = str(row["value"] or "").strip()
    return value or default


def set_setting_value(connection, key: str, value: str, title: str, description: str) -> None:
    connection.execute(
        """
        INSERT INTO game_settings (key, value, title, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            title = excluded.title,
            description = excluded.description,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value, title, description),
    )


def set_configured_codes(connection, codes: list[str]) -> None:
    encoded = encode_collection_codes(codes)
    set_setting_value(
        connection,
        FREE_CARD_COLLECTIONS_SETTING_KEY,
        encoded,
        "Коллекции бесплатной карточки",
        "Список кодов коллекций через запятую. Бесплатная карточка выбирается случайно из всех указанных активных коллекций.",
    )
    # legacy setting points to the first collection so old code/settings screens stay readable
    first = codes[0] if codes else ""
    set_setting_value(
        connection,
        FREE_CARD_COLLECTION_SETTING_KEY,
        first,
        "Коллекция бесплатной карточки",
        "Устаревшая настройка. Основной список хранится в free_card_collection_codes.",
    )


def get_configured_codes(connection) -> list[str]:
    row = connection.execute("SELECT value FROM game_settings WHERE key = ?", (FREE_CARD_COLLECTIONS_SETTING_KEY,)).fetchone()
    if row is not None:
        # В этой настройке пустое значение означает: коллекции специально не выбраны.
        return normalize_collection_codes(row["value"])

    legacy = get_setting_value(connection, FREE_CARD_COLLECTION_SETTING_KEY, FREE_CARD_DEFAULT_COLLECTION_CODE)
    return normalize_collection_codes(legacy) or [FREE_CARD_DEFAULT_COLLECTION_CODE]


def get_collection_by_code(connection, code: str) -> FreeCardCollection | None:
    cursor = connection.execute(
        """
        SELECT collections.id, collections.code, collections.name, collections.description, collections.active,
               COUNT(cards.id) AS active_cards_count
        FROM collections
        LEFT JOIN cards ON cards.collection_id = collections.id AND cards.active = 1
        WHERE collections.code = ?
        GROUP BY collections.id
        """,
        (code,),
    )
    return row_to_collection(cursor.fetchone())


def get_collections_by_codes(connection, codes: list[str]) -> list[FreeCardCollection]:
    result: list[FreeCardCollection] = []
    for code in codes:
        collection = get_collection_by_code(connection, code)
        if collection is not None:
            result.append(collection)
    return result


def find_collection(connection, query: str) -> FreeCardCollection | None:
    clean_query = normalize_collection_query(query)
    if not clean_query:
        return None
    cursor = connection.execute(
        """
        SELECT collections.id, collections.code, collections.name, collections.description, collections.active,
               COUNT(cards.id) AS active_cards_count
        FROM collections
        LEFT JOIN cards ON cards.collection_id = collections.id AND cards.active = 1
        WHERE collections.code = ? COLLATE NOCASE
           OR collections.name = ? COLLATE NOCASE
           OR CAST(collections.id AS TEXT) = ?
        GROUP BY collections.id
        LIMIT 1
        """,
        (clean_query, clean_query, clean_query),
    )
    row = cursor.fetchone()
    if row is not None:
        return row_to_collection(row)
    cursor = connection.execute(
        """
        SELECT collections.id, collections.code, collections.name, collections.description, collections.active,
               COUNT(cards.id) AS active_cards_count
        FROM collections
        LEFT JOIN cards ON cards.collection_id = collections.id AND cards.active = 1
        WHERE collections.code LIKE ? OR collections.name LIKE ?
        GROUP BY collections.id
        ORDER BY collections.active DESC, collections.id DESC
        LIMIT 1
        """,
        (f"%{clean_query}%", f"%{clean_query}%"),
    )
    return row_to_collection(cursor.fetchone())


async def get_configured_collection() -> FreeCardCollection | None:
    collections = await get_configured_collections()
    return collections[0] if collections else None


async def get_configured_collections() -> list[FreeCardCollection]:
    with get_connection() as connection:
        return get_collections_by_codes(connection, get_configured_codes(connection))


async def get_configured_cooldown_hours() -> int:
    with get_connection() as connection:
        value = get_setting_value(connection, FREE_CARD_COOLDOWN_SETTING_KEY, str(FREE_CARD_DEFAULT_COOLDOWN_HOURS))
    return clamp_cooldown_hours(value)


def build_status(collections: list[FreeCardCollection], cooldown_hours: int, is_ready: bool, remaining_seconds: int, last_claimed_at: str | None) -> FreeCardStatus:
    return FreeCardStatus(
        collection=collections[0] if collections else None,
        collections=collections,
        cooldown_hours=cooldown_hours,
        is_ready=is_ready,
        remaining_seconds=remaining_seconds,
        last_claimed_at=last_claimed_at,
    )


async def get_free_card_status(user_id: int) -> FreeCardStatus:
    now = utc_now()
    with get_connection() as connection:
        cooldown_hours = clamp_cooldown_hours(get_setting_value(connection, FREE_CARD_COOLDOWN_SETTING_KEY, str(FREE_CARD_DEFAULT_COOLDOWN_HOURS)))
        collections = get_collections_by_codes(connection, get_configured_codes(connection))
        claim_row = connection.execute("SELECT last_claimed_at FROM free_card_claims WHERE user_id = ?", (user_id,)).fetchone()

    last_claimed_at = claim_row["last_claimed_at"] if claim_row else None
    last_dt = parse_dt(last_claimed_at)
    has_cards = any(collection.active and collection.active_cards_count > 0 for collection in collections)
    if not collections or not has_cards:
        return build_status(collections, cooldown_hours, False, 0, last_claimed_at)
    if last_dt is None:
        return build_status(collections, cooldown_hours, True, 0, last_claimed_at)
    next_ready = last_dt + timedelta(hours=cooldown_hours)
    remaining_seconds = max(0, int((next_ready - now).total_seconds()))
    return build_status(collections, cooldown_hours, remaining_seconds <= 0, remaining_seconds, last_claimed_at)


async def set_free_card_collection(query: str) -> FreeCardCollection | None:
    """Legacy-compatible action: replace the list with one collection."""
    with get_connection() as connection:
        collection = find_collection(connection, query)
        if collection is None:
            return None
        set_configured_codes(connection, [collection.code])
        connection.commit()
        return collection


async def add_free_card_collection(query: str) -> FreeCardCollection | None:
    with get_connection() as connection:
        collection = find_collection(connection, query)
        if collection is None:
            return None
        codes = get_configured_codes(connection)
        if collection.code not in codes:
            codes.append(collection.code)
        set_configured_codes(connection, codes)
        connection.commit()
        return collection


async def remove_free_card_collection(query: str) -> FreeCardCollection | None:
    with get_connection() as connection:
        collection = find_collection(connection, query)
        if collection is None:
            return None
        codes = [code for code in get_configured_codes(connection) if code != collection.code]
        set_configured_codes(connection, codes)
        connection.commit()
        return collection


async def get_free_card_admin_status() -> FreeCardStatus:
    with get_connection() as connection:
        cooldown_hours = clamp_cooldown_hours(get_setting_value(connection, FREE_CARD_COOLDOWN_SETTING_KEY, str(FREE_CARD_DEFAULT_COOLDOWN_HOURS)))
        collections = get_collections_by_codes(connection, get_configured_codes(connection))
    return build_status(
        collections,
        cooldown_hours,
        any(collection.active and collection.active_cards_count > 0 for collection in collections),
        0,
        None,
    )


async def claim_free_card(user_id: int) -> tuple[FreeCardReward | None, FreeCardStatus]:
    now = utc_now()
    with get_connection() as connection:
        cooldown_hours = clamp_cooldown_hours(get_setting_value(connection, FREE_CARD_COOLDOWN_SETTING_KEY, str(FREE_CARD_DEFAULT_COOLDOWN_HOURS)))
        collections = get_collections_by_codes(connection, get_configured_codes(connection))
        active_collection_ids = [collection.id for collection in collections if collection.active and collection.active_cards_count > 0]
        claim_row = connection.execute("SELECT last_claimed_at FROM free_card_claims WHERE user_id = ?", (user_id,)).fetchone()
        last_claimed_at = claim_row["last_claimed_at"] if claim_row else None
        last_dt = parse_dt(last_claimed_at)

        if not active_collection_ids:
            return None, build_status(collections, cooldown_hours, False, 0, last_claimed_at)

        remaining_seconds = 0
        if last_dt is not None:
            next_ready = last_dt + timedelta(hours=cooldown_hours)
            remaining_seconds = max(0, int((next_ready - now).total_seconds()))
        if remaining_seconds > 0:
            return None, build_status(collections, cooldown_hours, False, remaining_seconds, last_claimed_at)

        placeholders = ",".join("?" for _ in active_collection_ids)
        card_row = connection.execute(
            f"""
            SELECT cards.id, cards.name, cards.position, cards.overall, cards.team, cards.country,
                   cards.rarity, cards.image_path, collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1 AND collections.id IN ({placeholders})
              AND LOWER(TRIM(collections.name)) != 'leaders'
              AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders'
            ORDER BY RANDOM()
            LIMIT 1
            """,
            active_collection_ids,
        ).fetchone()

        if card_row is None:
            return None, build_status(collections, cooldown_hours, False, 0, last_claimed_at)

        user_card_cursor = connection.execute(
            """
            INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked)
            VALUES (?, ?, 'free_card', 0, 0)
            """,
            (user_id, int(card_row["id"])),
        )
        user_card_id = int(user_card_cursor.lastrowid)
        claimed_at = format_dt(now)
        connection.execute(
            """
            INSERT INTO free_card_claims (user_id, last_claimed_at, last_notified_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_claimed_at = excluded.last_claimed_at,
                last_notified_at = excluded.last_notified_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, claimed_at, claimed_at),
        )
        connection.commit()

    next_ready_at = format_dt(now + timedelta(hours=cooldown_hours))
    reward = FreeCardReward(
        user_card_id=user_card_id,
        card_id=int(card_row["id"]),
        name=str(card_row["name"]),
        position=str(card_row["position"]),
        overall=int(card_row["overall"]),
        team=str(card_row["team"]),
        country=str(card_row["country"]),
        collection_name=str(card_row["collection_name"]),
        rarity=str(card_row["rarity"]),
        image_path=str(card_row["image_path"]),
        next_ready_at=next_ready_at,
    )
    return reward, build_status(collections, cooldown_hours, False, cooldown_hours * 3600, claimed_at)


async def get_free_card_notification_targets() -> list[FreeCardNotificationTarget]:
    now = utc_now()
    with get_connection() as connection:
        cooldown_hours = clamp_cooldown_hours(get_setting_value(connection, FREE_CARD_COOLDOWN_SETTING_KEY, str(FREE_CARD_DEFAULT_COOLDOWN_HOURS)))
        collections = get_collections_by_codes(connection, get_configured_codes(connection))
        if not any(collection.active and collection.active_cards_count > 0 for collection in collections):
            return []
        ready_before = format_dt(now - timedelta(hours=cooldown_hours))
        notify_before = ready_before
        rows = connection.execute(
            """
            SELECT users.id AS user_id, users.telegram_id
            FROM users
            LEFT JOIN free_card_claims ON free_card_claims.user_id = users.id
            WHERE users.is_banned = 0
              AND (free_card_claims.last_claimed_at IS NULL OR free_card_claims.last_claimed_at <= ?)
              AND (free_card_claims.last_notified_at IS NULL OR free_card_claims.last_notified_at <= ?)
            ORDER BY users.id ASC
            LIMIT ?
            """,
            (ready_before, notify_before, FREE_CARD_NOTIFICATION_LIMIT),
        ).fetchall()
    return [FreeCardNotificationTarget(user_id=int(row["user_id"]), telegram_id=int(row["telegram_id"])) for row in rows]


async def mark_free_card_notified(user_id: int) -> None:
    notified_at = format_dt(utc_now())
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO free_card_claims (user_id, last_notified_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_notified_at = excluded.last_notified_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, notified_at),
        )
        connection.commit()


async def free_card_notification_loop(bot: Bot) -> None:
    from app.keyboards.free_card import build_free_card_ready_keyboard
    from app.texts.free_card import FREE_CARD_NOTIFICATION_TEXT

    while True:
        try:
            targets = await get_free_card_notification_targets()
            for target in targets:
                try:
                    await bot.send_message(
                        chat_id=target.telegram_id,
                        text=FREE_CARD_NOTIFICATION_TEXT,
                        reply_markup=build_free_card_ready_keyboard(),
                    )
                    await mark_free_card_notified(target.user_id)
                except TelegramRetryAfter as error:
                    await asyncio.sleep(error.retry_after + 1)
                    continue
                except (TelegramBadRequest, TelegramForbiddenError):
                    await mark_free_card_notified(target.user_id)
                except Exception:
                    continue
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(FREE_CARD_NOTIFICATION_SLEEP_SECONDS)
