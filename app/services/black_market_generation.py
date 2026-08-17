"""Генерация персональной ежедневной ротации BLACK MARKET.

Ключевая идея: MASTER POOL (black_market_pool_items/black_market_rarity_weights)
общий, но каждый пользователь получает свою собственную ротацию слотов
(black_market_user_rotations/black_market_user_rotation_items), сгенерированную
лениво при первом открытии магазина за business_date, а не заранее для всех.

Детерминизм: seed = HMAC_SHA256(secret, "user_id:business_date:rotation_version"),
рандомизация идёт только через локальный `random.Random(seed)` — никогда через
глобальный модуль `random` (см. app/services/packs.py:PACK_RANDOM, который here
намеренно не переиспользуется, поскольку не детерминирован между вызовами).

Защита от гонки при одновременном первом открытии: двойная проверка внутри
`BEGIN IMMEDIATE` (SQLite не имеет `SELECT ... FOR UPDATE`, но `BEGIN IMMEDIATE`
берёт блокировку записи на всю БД раньше конкурента) + UNIQUE(user_id, business_date,
rotation_version) как страховка — если гонка всё же проскочила до захвата блокировки,
второй INSERT упадёт с IntegrityError, и мы просто читаем строку победителя.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import random
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.black_market_common import business_date as compute_business_date
from app.services.black_market_common import get_settings
from app.services.black_market_items import resolve_display

from config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RotationItemInfo:
    id: int
    slot_number: int
    pool_item_id: int
    item_type: str
    item_reference_id: int | None
    rarity: str
    name: str
    description: str
    price_currency_code: str
    price_amount: int
    initial_personal_stock: int
    remaining_personal_stock: int
    personal_purchase_limit: int
    purchased_quantity: int
    item_status: str
    preview: str | None


@dataclass(frozen=True)
class RotationInfo:
    id: int
    user_id: int
    business_date: str
    rotation_version: int
    seed_hash: str
    items: list[RotationItemInfo]


def compute_seed_digest(user_id: int, business_date_value: str, rotation_version: int, secret: str) -> bytes:
    seed_material = f"{user_id}:{business_date_value}:{rotation_version}"
    return hmac.new(secret.encode("utf-8"), seed_material.encode("utf-8"), hashlib.sha256).digest()


def seeded_rng(
    user_id: int,
    business_date_value: str,
    rotation_version: int,
    secret: str | None = None,
) -> tuple[random.Random, str]:
    digest = compute_seed_digest(user_id, business_date_value, rotation_version, secret or settings.black_market_seed_secret)
    seed = int.from_bytes(digest[:8], "big")
    return random.Random(seed), digest.hex()


def _row_to_item(row: sqlite3.Row) -> RotationItemInfo:
    return RotationItemInfo(
        id=int(row["id"]),
        slot_number=int(row["slot_number"]),
        pool_item_id=int(row["pool_item_id"]),
        item_type=row["item_type"],
        item_reference_id=int(row["item_reference_id"]) if row["item_reference_id"] is not None else None,
        rarity=row["rarity"],
        name=row["name"],
        description=row["description"] or "",
        price_currency_code=row["price_currency_code"],
        price_amount=int(row["price_amount"]),
        initial_personal_stock=int(row["initial_personal_stock"]),
        remaining_personal_stock=int(row["remaining_personal_stock"]),
        personal_purchase_limit=int(row["personal_purchase_limit"]),
        purchased_quantity=int(row["purchased_quantity"]),
        item_status=row["item_status"],
        preview=row["preview"],
    )


def _load_rotation(
    connection: sqlite3.Connection, user_id: int, business_date_value: str, rotation_version: int
) -> RotationInfo | None:
    row = connection.execute(
        """
        SELECT * FROM black_market_user_rotations
        WHERE user_id = ? AND business_date = ? AND rotation_version = ? AND status = 'ACTIVE'
        """,
        (user_id, business_date_value, rotation_version),
    ).fetchone()
    if row is None:
        return None

    item_rows = connection.execute(
        "SELECT * FROM black_market_user_rotation_items WHERE user_rotation_id = ? ORDER BY slot_number",
        (row["id"],),
    ).fetchall()
    return RotationInfo(
        id=int(row["id"]),
        user_id=user_id,
        business_date=business_date_value,
        rotation_version=rotation_version,
        seed_hash=row["seed_hash"],
        items=[_row_to_item(item_row) for item_row in item_rows],
    )


def _weighted_pick(rng: random.Random, rows: list[sqlite3.Row], weight_column: str) -> sqlite3.Row | None:
    if not rows:
        return None
    weights = [max(1, int(row[weight_column])) for row in rows]
    total = sum(weights)
    roll = rng.randint(1, total)
    cumulative = 0
    for row, weight in zip(rows, weights):
        cumulative += weight
        if roll <= cumulative:
            return row
    return rows[-1]


def _pick_rarity(rng: random.Random, weights: dict[str, int]) -> str | None:
    total = sum(weights.values())
    if total <= 0:
        return None
    roll = rng.randint(1, total)
    cumulative = 0
    for rarity, weight in weights.items():
        cumulative += weight
        if roll <= cumulative:
            return rarity
    return next(iter(weights.keys()))


_POOL_ITEM_VALIDITY_SQL = """
    SELECT bmpi.* FROM black_market_pool_items bmpi
    LEFT JOIN currencies cur ON bmpi.item_type = 'currency' AND cur.code = bmpi.currency_code
    LEFT JOIN packs p ON bmpi.item_type = 'pack' AND p.id = bmpi.pack_id
    LEFT JOIN cards c ON bmpi.item_type = 'card' AND c.id = bmpi.card_id
    LEFT JOIN war2_cosmetic_items wci ON bmpi.item_type = 'cosmetic' AND wci.id = bmpi.cosmetic_item_id
    WHERE bmpi.active = 1
      AND (bmpi.available_from IS NULL OR bmpi.available_from <= datetime('now'))
      AND (bmpi.available_until IS NULL OR bmpi.available_until >= datetime('now'))
      AND (
        (bmpi.item_type = 'currency' AND cur.code IS NOT NULL AND cur.active = 1)
        OR (bmpi.item_type = 'pack' AND p.id IS NOT NULL AND p.active = 1)
        OR (bmpi.item_type = 'card' AND c.id IS NOT NULL AND c.active = 1)
        OR (bmpi.item_type = 'cosmetic' AND wci.id IS NOT NULL AND wci.active = 1)
      )
"""


def _fetch_valid_pool_items(
    connection: sqlite3.Connection, *, rarity: str | None, exclude_ids: set[int]
) -> list[sqlite3.Row]:
    query = _POOL_ITEM_VALIDITY_SQL
    params: list[object] = []
    if rarity is not None:
        query += " AND bmpi.rarity = ?"
        params.append(rarity)
    if exclude_ids:
        placeholders = ",".join("?" for _ in exclude_ids)
        query += f" AND bmpi.id NOT IN ({placeholders})"
        params.extend(sorted(exclude_ids))
    query += " ORDER BY bmpi.id"
    return connection.execute(query, params).fetchall()


def _pick_pool_item(
    connection: sqlite3.Connection, rng: random.Random, *, rarity: str, exclude_ids: set[int], user_id: int
) -> sqlite3.Row | None:
    rows = _fetch_valid_pool_items(connection, rarity=rarity, exclude_ids=exclude_ids)
    row = _weighted_pick(rng, rows, "selection_weight")
    if row is not None:
        return row
    # Fallback: пул нужной редкости пуст/исчерпан дублями — перевыбор среди всех редкостей,
    # чтобы слот не остался пустым только из-за исчерпания одной редкости (раздел 4 ТЗ
    # аудита: "если в выпавшей редкости нет предметов, используется безопасный fallback
    # с логированием").
    logger.warning(
        "black market generation: no valid pool items for rarity=%s (user_id=%s) — falling back across all rarities",
        rarity,
        user_id,
    )
    fallback_rows = _fetch_valid_pool_items(connection, rarity=None, exclude_ids=exclude_ids)
    fallback_row = _weighted_pick(rng, fallback_rows, "selection_weight")
    if fallback_row is None:
        logger.warning("black market generation: master pool exhausted, slot left empty (user_id=%s)", user_id)
    return fallback_row


def _resolve_price(rng: random.Random, pool_row: sqlite3.Row) -> int:
    if (
        pool_row["price_mode"] == "RANDOM_RANGE"
        and pool_row["price_min_amount"] is not None
        and pool_row["price_max_amount"] is not None
    ):
        low, high = int(pool_row["price_min_amount"]), int(pool_row["price_max_amount"])
        if low > high:
            low, high = high, low
        return rng.randint(low, high)
    return int(pool_row["price_amount"])


def _resolve_stock(rng: random.Random, pool_row: sqlite3.Row) -> int:
    if pool_row["stock_min"] is not None and pool_row["stock_max"] is not None:
        low, high = int(pool_row["stock_min"]), int(pool_row["stock_max"])
        if low > high:
            low, high = high, low
        return max(1, rng.randint(low, high))
    return max(1, int(pool_row["max_stock_per_rotation"]))


def _materialize_slot(
    connection: sqlite3.Connection,
    rotation_id: int,
    slot_number: int,
    rng: random.Random,
    pool_row: sqlite3.Row,
) -> RotationItemInfo:
    display = resolve_display(connection, pool_row)
    price_amount = _resolve_price(rng, pool_row)
    stock = _resolve_stock(rng, pool_row)
    # personal_purchase_limit=0 на предмете пула означает "по умолчанию = сток"
    # (старое поведение); положительное значение — явный лимит покупок отдельно от
    # стока, настраиваемый админом (раздел 3 ТЗ аудита).
    configured_limit = int(pool_row["personal_purchase_limit"]) if "personal_purchase_limit" in pool_row.keys() else 0
    purchase_limit = configured_limit if configured_limit > 0 else stock

    cursor = connection.execute(
        """
        INSERT INTO black_market_user_rotation_items (
            user_rotation_id, slot_number, pool_item_id, item_type, item_reference_id,
            rarity, name, description, price_currency_code, price_amount,
            initial_personal_stock, remaining_personal_stock, personal_purchase_limit, preview
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rotation_id,
            slot_number,
            int(pool_row["id"]),
            pool_row["item_type"],
            display.reference_id,
            pool_row["rarity"],
            display.name,
            display.description,
            pool_row["price_currency_code"],
            price_amount,
            stock,
            stock,
            purchase_limit,
            display.preview,
        ),
    )
    return RotationItemInfo(
        id=int(cursor.lastrowid),
        slot_number=slot_number,
        pool_item_id=int(pool_row["id"]),
        item_type=pool_row["item_type"],
        item_reference_id=display.reference_id,
        rarity=pool_row["rarity"],
        name=display.name,
        description=display.description,
        price_currency_code=pool_row["price_currency_code"],
        price_amount=price_amount,
        initial_personal_stock=stock,
        remaining_personal_stock=stock,
        personal_purchase_limit=purchase_limit,
        purchased_quantity=0,
        item_status="AVAILABLE",
        preview=display.preview,
    )


def _generate_rotation(
    connection: sqlite3.Connection,
    user_id: int,
    business_date_value: str,
    rotation_version: int,
    settings_row: sqlite3.Row,
    reason: str,
) -> RotationInfo:
    rng, seed_hash = seeded_rng(user_id, business_date_value, rotation_version)

    weight_rows = connection.execute(
        "SELECT rarity, weight FROM black_market_rarity_weights WHERE weight > 0 ORDER BY rarity"
    ).fetchall()
    weights = {row["rarity"]: int(row["weight"]) for row in weight_rows}

    slots_count = max(0, int(settings_row["slots_count"]))
    allow_duplicates = bool(settings_row["allow_duplicate_slots"])

    cursor = connection.execute(
        """
        INSERT INTO black_market_user_rotations (user_id, business_date, rotation_version, seed_hash, generation_reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, business_date_value, rotation_version, seed_hash, reason),
    )
    rotation_id = int(cursor.lastrowid)

    used_pool_item_ids: set[int] = set()
    items: list[RotationItemInfo] = []

    if weights:
        for slot_number in range(1, slots_count + 1):
            rarity = _pick_rarity(rng, weights)
            if rarity is None:
                continue
            exclude = set() if allow_duplicates else used_pool_item_ids
            pool_row = _pick_pool_item(connection, rng, rarity=rarity, exclude_ids=exclude, user_id=user_id)
            if pool_row is None:
                continue
            # Глобальная настройка allow_duplicate_slots — если строгая (0), но сам
            # предмет помечен allow_repeat_in_rotation=1, ему разрешено выпасть ещё
            # раз в этой же ротации (раздел 3 ТЗ аудита: "возможность повторов" как
            # настройка конкретного товара, а не только глобальный переключатель).
            item_allows_repeat = bool(pool_row["allow_repeat_in_rotation"]) if "allow_repeat_in_rotation" in pool_row.keys() else False
            if not allow_duplicates and not item_allows_repeat:
                used_pool_item_ids.add(int(pool_row["id"]))
            items.append(_materialize_slot(connection, rotation_id, slot_number, rng, pool_row))
    else:
        logger.warning("black market generation: no active rarity weights configured, rotation will be empty (user_id=%s)", user_id)

    return RotationInfo(
        id=rotation_id,
        user_id=user_id,
        business_date=business_date_value,
        rotation_version=rotation_version,
        seed_hash=seed_hash,
        items=items,
    )


async def get_active_rotation(user_id: int, *, business_date_value: str | None = None) -> RotationInfo | None:
    """Read-only чтение текущей ротации без ленивой генерации — для админ-просмотра
    чужой витрины (спецификация запрещает генерировать/трогать чужую витрину из
    админ-панели "мимоходом"; регенерация — только через явный admin refresh)."""
    target_date = business_date_value or compute_business_date()
    with get_connection() as connection:
        version = int(get_settings(connection)["global_rotation_version"])
        return _load_rotation(connection, user_id, target_date, version)


async def get_or_create_rotation(
    user_id: int,
    *,
    business_date_value: str | None = None,
    reason: str = "lazy_open",
) -> RotationInfo:
    target_date = business_date_value or compute_business_date()

    with get_connection() as connection:
        settings_row = get_settings(connection)
        version = int(settings_row["global_rotation_version"])

        existing = _load_rotation(connection, user_id, target_date, version)
        if existing is not None:
            return existing

        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = _load_rotation(connection, user_id, target_date, version)
            if existing is not None:
                connection.rollback()
                return existing

            rotation = _generate_rotation(connection, user_id, target_date, version, settings_row, reason)
            connection.commit()
            return rotation
        except sqlite3.IntegrityError:
            connection.rollback()
            existing = _load_rotation(connection, user_id, target_date, version)
            if existing is None:
                raise
            return existing
        except Exception:
            connection.rollback()
            raise
