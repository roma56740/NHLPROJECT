"""Админ-слой BLACK MARKET: master pool CRUD, поиск игрока, просмотр/правка чужой
витрины, ручное обновление (одного игрока / всех), сид дефолтов при первой миграции.

Каждое изменение пишет запись в black_market_admin_audit (см. `_audit`, тот же
паттерн, что app/services/stronghold_admin_content.py:_audit — before/after JSON-снапшоты).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.black_market_common import RARITIES, BlackMarketError, business_date
from app.services.black_market_generation import RotationInfo, get_active_rotation
from app.services.black_market_store import invalidate_user_cache

DEFAULT_RARITY_WEIGHTS: dict[str, int] = {
    "Common": 50,
    "Rare": 25,
    "Epic": 15,
    "Legendary": 7,
    "Event": 2,
    "Icon": 1,
}

_EDITABLE_POOL_ITEM_FIELDS = {
    "title",
    "description",
    "rarity",
    "price_currency_code",
    "price_mode",
    "price_amount",
    "price_min_amount",
    "price_max_amount",
    "max_stock_per_rotation",
    "stock_min",
    "stock_max",
    "personal_purchase_limit",
    "available_from",
    "available_until",
    "allow_repeat_in_rotation",
    "selection_weight",
    "amount",
}

_EDITABLE_ROTATION_SETTINGS_FIELDS = {"slots_count", "stock_mode", "allow_duplicate_slots"}


def seed_black_market_defaults(connection: sqlite3.Connection) -> None:
    """Вызывается один раз через run_once("0003_black_market_seed_defaults", ...)."""
    connection.execute("INSERT OR IGNORE INTO black_market_settings (id) VALUES (1)")
    for rarity, weight in DEFAULT_RARITY_WEIGHTS.items():
        connection.execute(
            "INSERT OR IGNORE INTO black_market_rarity_weights (rarity, weight) VALUES (?, ?)",
            (rarity, weight),
        )


def seed_black_market_notification_baseline(connection: sqlite3.Connection) -> None:
    """Вызывается один раз через run_once("0004_black_market_notification_baseline", ...).

    Инициализирует last_notified_business_date сегодняшним днём, чтобы фоновый цикл
    уведомлений (app.services.black_market_notifications.black_market_notification_loop)
    не разослал "ассортимент обновлён" всем сразу же при первом деплое этой миграции —
    уведомление должно приходить только при РЕАЛЬНОЙ смене business_date после этого."""
    connection.execute(
        "UPDATE black_market_settings SET last_notified_business_date = ? WHERE id = 1 AND last_notified_business_date IS NULL",
        (business_date(),),
    )


def _validate_price_fields(
    *, price_mode: str, price_amount: int, price_min_amount: int | None, price_max_amount: int | None
) -> None:
    if price_mode not in ("FIXED", "RANDOM_RANGE"):
        raise BlackMarketError("INVALID_PRICE_MODE", "price_mode должен быть FIXED или RANDOM_RANGE.")
    if price_mode == "RANDOM_RANGE":
        if price_min_amount is None or price_max_amount is None:
            raise BlackMarketError("PRICE_RANGE_INVALID", "Для RANDOM_RANGE нужны min и max цена.")
        if int(price_min_amount) < 0 or int(price_max_amount) < 0:
            raise BlackMarketError("PRICE_RANGE_INVALID", "Цена не может быть отрицательной.")
        if int(price_min_amount) > int(price_max_amount):
            raise BlackMarketError("PRICE_RANGE_INVALID", "min_price должен быть <= max_price.")
    elif price_amount < 0:
        raise BlackMarketError("PRICE_RANGE_INVALID", "Цена не может быть отрицательной.")


def _validate_rarity_weights(merged: dict[str, int]) -> None:
    """Раздел 4 ТЗ аудита: каждое значение 0..100, сумма активных (>0) строго 100%,
    хотя бы одна редкость активна. Веса — целые числа (int), поэтому сумма всегда
    точна и не подвержена ошибкам округления float."""
    for rarity, weight in merged.items():
        if not (0 <= int(weight) <= 100):
            raise BlackMarketError("RARITY_WEIGHTS_INVALID", f"Вес редкости {rarity} должен быть от 0 до 100.")
    active_total = sum(int(weight) for weight in merged.values() if int(weight) > 0)
    if active_total == 0:
        raise BlackMarketError("RARITY_WEIGHTS_INVALID", "Хотя бы одна редкость должна быть активна (вес > 0).")
    if active_total != 100:
        raise BlackMarketError("RARITY_WEIGHTS_INVALID", f"Сумма активных весов должна быть 100, сейчас {active_total}.")


def _audit(
    connection: sqlite3.Connection,
    *,
    admin_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    target_user_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "admin_edit",
) -> None:
    connection.execute(
        """
        INSERT INTO black_market_admin_audit (admin_id, action, entity, entity_id, target_user_id, before, after, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_id,
            action,
            entity,
            entity_id,
            target_user_id,
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
            reason,
        ),
    )


@dataclass(frozen=True)
class PoolItemInfo:
    id: int
    item_type: str
    currency_code: str | None
    amount: int
    pack_id: int | None
    card_id: int | None
    cosmetic_item_id: int | None
    rarity: str
    title: str
    description: str
    price_currency_code: str
    price_mode: str
    price_amount: int
    price_min_amount: int | None
    price_max_amount: int | None
    max_stock_per_rotation: int
    stock_min: int | None
    stock_max: int | None
    personal_purchase_limit: int
    available_from: str | None
    available_until: str | None
    allow_repeat_in_rotation: bool
    selection_weight: int
    active: bool


def _row_to_pool_item(row: sqlite3.Row) -> PoolItemInfo:
    return PoolItemInfo(
        id=int(row["id"]),
        item_type=row["item_type"],
        currency_code=row["currency_code"],
        amount=int(row["amount"]),
        pack_id=row["pack_id"],
        card_id=row["card_id"],
        cosmetic_item_id=row["cosmetic_item_id"],
        rarity=row["rarity"],
        title=row["title"] or "",
        description=row["description"] or "",
        price_currency_code=row["price_currency_code"],
        price_mode=row["price_mode"],
        price_amount=int(row["price_amount"]),
        price_min_amount=row["price_min_amount"],
        price_max_amount=row["price_max_amount"],
        max_stock_per_rotation=int(row["max_stock_per_rotation"]),
        stock_min=row["stock_min"],
        stock_max=row["stock_max"],
        personal_purchase_limit=int(row["personal_purchase_limit"]),
        available_from=row["available_from"],
        available_until=row["available_until"],
        allow_repeat_in_rotation=bool(row["allow_repeat_in_rotation"]),
        selection_weight=int(row["selection_weight"]),
        active=bool(row["active"]),
    )


async def list_pool_items(*, rarity: str | None = None, item_type: str | None = None) -> list[PoolItemInfo]:
    query = "SELECT * FROM black_market_pool_items"
    clauses: list[str] = []
    params: list[object] = []
    if rarity:
        clauses.append("rarity = ?")
        params.append(rarity)
    if item_type:
        clauses.append("item_type = ?")
        params.append(item_type)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_to_pool_item(row) for row in rows]


async def create_pool_item(
    admin_id: int,
    *,
    item_type: str,
    rarity: str,
    price_currency_code: str,
    title: str = "",
    description: str = "",
    currency_code: str | None = None,
    amount: int = 1,
    pack_id: int | None = None,
    card_id: int | None = None,
    cosmetic_item_id: int | None = None,
    price_mode: str = "FIXED",
    price_amount: int = 0,
    price_min_amount: int | None = None,
    price_max_amount: int | None = None,
    max_stock_per_rotation: int = 1,
    stock_min: int | None = None,
    stock_max: int | None = None,
    personal_purchase_limit: int = 0,
    available_from: str | None = None,
    available_until: str | None = None,
    allow_repeat_in_rotation: bool = False,
    selection_weight: int = 1,
) -> PoolItemInfo:
    if item_type not in ("currency", "pack", "card", "cosmetic"):
        raise BlackMarketError("INVALID_ITEM_TYPE", "Неизвестный тип предмета.")
    if rarity not in RARITIES:
        raise BlackMarketError("INVALID_RARITY", "Неизвестная редкость.")
    _validate_price_fields(
        price_mode=price_mode, price_amount=price_amount, price_min_amount=price_min_amount, price_max_amount=price_max_amount
    )

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            INSERT INTO black_market_pool_items (
                item_type, currency_code, amount, pack_id, card_id, cosmetic_item_id, rarity,
                title, description, price_currency_code, price_mode, price_amount,
                price_min_amount, price_max_amount, max_stock_per_rotation, stock_min, stock_max,
                personal_purchase_limit, available_from, available_until, allow_repeat_in_rotation, selection_weight
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_type, currency_code, amount, pack_id, card_id, cosmetic_item_id, rarity,
                title, description, price_currency_code, price_mode, price_amount,
                price_min_amount, price_max_amount, max_stock_per_rotation, stock_min, stock_max,
                personal_purchase_limit, available_from, available_until, 1 if allow_repeat_in_rotation else 0, selection_weight,
            ),
        )
        item_id = int(cursor.lastrowid)
        after_row = connection.execute("SELECT * FROM black_market_pool_items WHERE id = ?", (item_id,)).fetchone()
        _audit(connection, admin_id=admin_id, action="pool_item_create", entity="black_market_pool_items", entity_id=item_id, before={}, after=dict(after_row))
        connection.commit()
    return _row_to_pool_item(after_row)


async def update_pool_item(admin_id: int, pool_item_id: int, **fields: object) -> PoolItemInfo:
    updates = {key: value for key, value in fields.items() if key in _EDITABLE_POOL_ITEM_FIELDS}
    if not updates:
        raise BlackMarketError("NO_FIELDS_TO_UPDATE", "Нет полей для обновления.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before_row = connection.execute("SELECT * FROM black_market_pool_items WHERE id = ?", (pool_item_id,)).fetchone()
        if before_row is None:
            connection.rollback()
            raise BlackMarketError("ITEM_NOT_FOUND", "Предмет пула не найден.")

        merged = {**dict(before_row), **updates}
        _validate_price_fields(
            price_mode=merged["price_mode"],
            price_amount=int(merged["price_amount"]),
            price_min_amount=merged["price_min_amount"],
            price_max_amount=merged["price_max_amount"],
        )

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        connection.execute(
            f"UPDATE black_market_pool_items SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*updates.values(), pool_item_id),
        )
        after_row = connection.execute("SELECT * FROM black_market_pool_items WHERE id = ?", (pool_item_id,)).fetchone()
        _audit(
            connection,
            admin_id=admin_id,
            action="pool_item_update",
            entity="black_market_pool_items",
            entity_id=pool_item_id,
            before=dict(before_row),
            after=dict(after_row),
        )
        connection.commit()

    from app.services.renders import invalidate_black_market_preview

    invalidate_black_market_preview(f"pool_item_{pool_item_id}")
    return _row_to_pool_item(after_row)


async def set_pool_item_active(admin_id: int, pool_item_id: int, active: bool) -> PoolItemInfo:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT active FROM black_market_pool_items WHERE id = ?", (pool_item_id,)).fetchone()
        if row is None:
            connection.rollback()
            raise BlackMarketError("ITEM_NOT_FOUND", "Предмет пула не найден.")
        old_active = bool(row["active"])
        connection.execute(
            "UPDATE black_market_pool_items SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if active else 0, pool_item_id),
        )
        after_row = connection.execute("SELECT * FROM black_market_pool_items WHERE id = ?", (pool_item_id,)).fetchone()
        _audit(
            connection,
            admin_id=admin_id,
            action="pool_item_toggle_active",
            entity="black_market_pool_items",
            entity_id=pool_item_id,
            before={"active": old_active},
            after={"active": active},
        )
        connection.commit()
    return _row_to_pool_item(after_row)


async def get_rarity_weights() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute("SELECT rarity, weight FROM black_market_rarity_weights ORDER BY rarity").fetchall()
    return {row["rarity"]: int(row["weight"]) for row in rows}


async def update_rarity_weights(admin_id: int, weights: dict[str, int]) -> None:
    invalid = set(weights) - set(RARITIES)
    if invalid:
        raise BlackMarketError("INVALID_RARITY", f"Неизвестная редкость: {', '.join(sorted(invalid))}")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before = {row["rarity"]: int(row["weight"]) for row in connection.execute("SELECT rarity, weight FROM black_market_rarity_weights").fetchall()}
        merged = {**before, **weights}
        _validate_rarity_weights(merged)
        for rarity, weight in weights.items():
            connection.execute(
                """
                INSERT INTO black_market_rarity_weights (rarity, weight) VALUES (?, ?)
                ON CONFLICT(rarity) DO UPDATE SET weight = excluded.weight, updated_at = CURRENT_TIMESTAMP
                """,
                (rarity, int(weight)),
            )
        _audit(connection, admin_id=admin_id, action="rarity_weights_update", entity="black_market_rarity_weights", before=before, after={**before, **weights})
        connection.commit()


async def find_user(query: str) -> sqlite3.Row | None:
    from app.services.admin_users import build_search_filter

    where_sql, params = build_search_filter(query)
    if not where_sql:
        return None
    with get_connection() as connection:
        row = connection.execute(f"SELECT * FROM users {where_sql} LIMIT 1", params).fetchone()
    return row


async def view_user_storefront(target_user_id: int) -> RotationInfo | None:
    """Только чтение — без ленивой генерации: спецификация запрещает молча создавать/
    трогать чужую витрину при простом просмотре из админ-панели."""
    return await get_active_rotation(target_user_id)


async def refresh_one_user(admin_id: int, target_user_id: int, reason: str = "admin_manual_refresh") -> None:
    today = business_date()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT id FROM black_market_user_rotations WHERE user_id = ? AND business_date = ? AND status = 'ACTIVE'",
            (target_user_id, today),
        ).fetchone()
        existing_id = int(existing["id"]) if existing is not None else None
        if existing_id is not None:
            connection.execute(
                "UPDATE black_market_user_rotations SET status = 'EXPIRED', invalidated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (existing_id,),
            )
        _audit(
            connection,
            admin_id=admin_id,
            action="refresh_one_user",
            entity="black_market_user_rotations",
            entity_id=existing_id,
            target_user_id=target_user_id,
            before={"had_active_rotation": existing_id is not None},
            after={"invalidated": True},
            reason=reason,
        )
        connection.commit()
    invalidate_user_cache(target_user_id)


async def refresh_everyone(admin_id: int, reason: str = "admin_manual_refresh_all") -> int:
    """Не пересоздаёт витрины синхронно всем — просто бампает global_rotation_version.
    Каждый пользователь получит новую персональную ротацию лениво при следующем открытии."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before_row = connection.execute("SELECT global_rotation_version FROM black_market_settings WHERE id = 1").fetchone()
        old_version = int(before_row["global_rotation_version"]) if before_row else 1
        new_version = old_version + 1
        connection.execute(
            "UPDATE black_market_settings SET global_rotation_version = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (new_version,),
        )
        _audit(
            connection,
            admin_id=admin_id,
            action="refresh_everyone",
            entity="black_market_settings",
            entity_id=1,
            before={"global_rotation_version": old_version},
            after={"global_rotation_version": new_version},
            reason=reason,
        )
        connection.commit()
    return new_version


async def edit_slot(
    admin_id: int,
    rotation_item_id: int,
    *,
    new_pool_item_id: int | None = None,
    new_price_amount: int | None = None,
    remove: bool = False,
) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before_row = connection.execute(
            "SELECT * FROM black_market_user_rotation_items WHERE id = ?", (rotation_item_id,)
        ).fetchone()
        if before_row is None:
            connection.rollback()
            raise BlackMarketError("ITEM_NOT_FOUND", "Слот витрины не найден.")

        target_user_id = int(
            connection.execute(
                "SELECT user_id FROM black_market_user_rotations WHERE id = ?", (before_row["user_rotation_id"],)
            ).fetchone()["user_id"]
        )

        if remove:
            connection.execute(
                "UPDATE black_market_user_rotation_items SET item_status = 'REMOVED', remaining_personal_stock = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (rotation_item_id,),
            )
            after: dict[str, object] = {"item_status": "REMOVED"}
        else:
            updates: dict[str, object] = {}
            if new_price_amount is not None:
                updates["price_amount"] = new_price_amount
            if new_pool_item_id is not None:
                pool_row = connection.execute(
                    "SELECT * FROM black_market_pool_items WHERE id = ? AND active = 1", (new_pool_item_id,)
                ).fetchone()
                if pool_row is None:
                    connection.rollback()
                    raise BlackMarketError("ITEM_NOT_FOUND", "Новый предмет пула не найден или неактивен.")
                updates.update(
                    pool_item_id=new_pool_item_id,
                    item_type=pool_row["item_type"],
                    rarity=pool_row["rarity"],
                    name=pool_row["title"] or before_row["name"],
                    description=pool_row["description"] or before_row["description"],
                    price_currency_code=pool_row["price_currency_code"],
                )
            if not updates:
                connection.rollback()
                raise BlackMarketError("NO_FIELDS_TO_UPDATE", "Нет полей для обновления.")
            set_clause = ", ".join(f"{key} = ?" for key in updates)
            connection.execute(
                f"UPDATE black_market_user_rotation_items SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*updates.values(), rotation_item_id),
            )
            after = updates

        _audit(
            connection,
            admin_id=admin_id,
            action="edit_slot",
            entity="black_market_user_rotation_items",
            entity_id=rotation_item_id,
            target_user_id=target_user_id,
            before=dict(before_row),
            after=after,
        )
        connection.commit()
    invalidate_user_cache(target_user_id)


async def list_recent_audit(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM black_market_admin_audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(rows)


# ---------------------------------------------------------------------------
# Настройки магазина (вкл/выкл + параметры ротации)
# ---------------------------------------------------------------------------

async def get_shop_settings() -> sqlite3.Row:
    with get_connection() as connection:
        from app.services.black_market_common import get_settings

        return get_settings(connection)


async def set_shop_enabled(admin_id: int, enabled: bool) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT shop_enabled FROM black_market_settings WHERE id = 1").fetchone()
        old_enabled = bool(row["shop_enabled"]) if row else True
        connection.execute(
            "UPDATE black_market_settings SET shop_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (1 if enabled else 0,),
        )
        _audit(
            connection,
            admin_id=admin_id,
            action="shop_enabled_toggle",
            entity="black_market_settings",
            entity_id=1,
            before={"shop_enabled": old_enabled},
            after={"shop_enabled": enabled},
        )
        connection.commit()


async def update_rotation_settings(admin_id: int, **fields: object) -> None:
    updates = {key: value for key, value in fields.items() if key in _EDITABLE_ROTATION_SETTINGS_FIELDS}
    if not updates:
        raise BlackMarketError("NO_FIELDS_TO_UPDATE", "Нет полей для обновления.")
    if "stock_mode" in updates and updates["stock_mode"] not in ("PERSONAL", "GLOBAL"):
        raise BlackMarketError("INVALID_STOCK_MODE", "stock_mode должен быть PERSONAL или GLOBAL.")
    if "slots_count" in updates and int(updates["slots_count"]) <= 0:
        raise BlackMarketError("INVALID_SLOTS_COUNT", "slots_count должен быть положительным.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before_row = connection.execute("SELECT * FROM black_market_settings WHERE id = 1").fetchone()
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        connection.execute(
            f"UPDATE black_market_settings SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            tuple(updates.values()),
        )
        after_row = connection.execute("SELECT * FROM black_market_settings WHERE id = 1").fetchone()
        _audit(
            connection,
            admin_id=admin_id,
            action="rotation_settings_update",
            entity="black_market_settings",
            entity_id=1,
            before=dict(before_row),
            after=dict(after_row),
        )
        connection.commit()


# ---------------------------------------------------------------------------
# История ротаций / покупок (раздел 3 ТЗ аудита)
# ---------------------------------------------------------------------------

async def list_user_rotation_history(target_user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT ur.*, (SELECT COUNT(*) FROM black_market_user_rotation_items i WHERE i.user_rotation_id = ur.id) AS items_count
            FROM black_market_user_rotations ur
            WHERE ur.user_id = ?
            ORDER BY ur.id DESC
            LIMIT ?
            """,
            (target_user_id, limit),
        ).fetchall()
    return list(rows)


async def list_user_purchase_history(target_user_id: int, limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT p.*, i.name AS item_name, i.item_type AS item_type
            FROM black_market_purchases p
            LEFT JOIN black_market_user_rotation_items i ON i.id = p.rotation_item_id
            WHERE p.user_id = ?
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (target_user_id, limit),
        ).fetchall()
    return list(rows)


async def list_recent_purchases(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT p.*, u.nickname AS buyer_nickname, i.name AS item_name
            FROM black_market_purchases p
            LEFT JOIN users u ON u.id = p.user_id
            LEFT JOIN black_market_user_rotation_items i ON i.id = p.rotation_item_id
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return list(rows)


# ---------------------------------------------------------------------------
# Хелперы выбора существующих сущностей для FSM "Добавить предмет"
# ---------------------------------------------------------------------------

async def get_card_choice(card_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT id, name, position, overall, team, rarity, image_path FROM cards WHERE id = ? AND active = 1",
            (card_id,),
        ).fetchone()


async def list_pack_choices(limit: int = 30) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(
            connection.execute(
                "SELECT id, code, name, image_path FROM packs WHERE active = 1 ORDER BY sort_order, id LIMIT ?",
                (limit,),
            ).fetchall()
        )


async def list_currency_choices() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(
            connection.execute("SELECT code, name, icon FROM currencies WHERE active = 1 ORDER BY code").fetchall()
        )


async def list_cosmetic_choices(cosmetic_type: str, limit: int = 30) -> list[sqlite3.Row]:
    aliases = {
        "CARD_FRAME": ("CARD_FRAME", "FRAME"),
        "FRAME": ("CARD_FRAME", "FRAME"),
        "PROFILE_BACKGROUND": ("PROFILE_BACKGROUND", "BACKGROUND"),
        "BACKGROUND": ("PROFILE_BACKGROUND", "BACKGROUND"),
    }.get(cosmetic_type, (cosmetic_type,))
    placeholders = ",".join("?" for _ in aliases)
    with get_connection() as connection:
        return list(
            connection.execute(
                f"SELECT id, code, title, rarity, image_path, badge_text FROM war2_cosmetic_items WHERE type IN ({placeholders}) AND active = 1 ORDER BY id LIMIT ?",
                (*aliases, limit),
            ).fetchall()
        )
