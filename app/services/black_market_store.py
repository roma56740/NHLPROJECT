"""Пользовательский Чёрный рынок: чтение текущей персональной витрины и покупка.

Покупка — атомарная транзакция (см. app/services/stronghold_store.py:_purchase_impl):
идемпотентность по request_id, guarded UPDATE для списания валюты и для личного
стока (без ledger-таблицы, аналогично app/services/shop.py:purchase_shop_pack — Чёрный
рынок не привязан к событию THE STRONGHOLD, поэтому stronghold_wallet тут не подходит).

Кэш витрины — простой process-local dict, ключ (user_id, business_date,
rotation_version). Инвалидируется точечно после покупки/регенерации/бампа версии
(бамп версии сам "гасит" старые записи, т.к. ключ меняется).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.black_market_common import BlackMarketError, business_date, get_settings
from app.services.black_market_generation import RotationInfo, get_or_create_rotation
from app.services.black_market_items import grant_item
from app.services import error_log


@dataclass(frozen=True)
class PurchaseResult:
    success: bool
    rotation_item_id: int
    item_type: str
    name: str
    price_currency_code: str
    price_amount: int
    new_balance: int
    new_remaining_stock: int
    replayed: bool = False


logger = logging.getLogger(__name__)

_storefront_cache: dict[tuple[int, str, int], RotationInfo] = {}


def invalidate_user_cache(user_id: int) -> None:
    for key in [key for key in _storefront_cache if key[0] == user_id]:
        _storefront_cache.pop(key, None)


async def list_storefront(user_id: int) -> RotationInfo:
    target_date = business_date()
    with get_connection() as connection:
        settings_row = get_settings(connection)
        if not bool(settings_row["shop_enabled"]):
            raise BlackMarketError("SHOP_DISABLED", "Чёрный рынок временно закрыт администрацией.")
        version = int(settings_row["global_rotation_version"])

    key = (user_id, target_date, version)
    cached = _storefront_cache.get(key)
    if cached is not None:
        return cached

    rotation = await get_or_create_rotation(user_id, business_date_value=target_date, reason="lazy_open")
    _storefront_cache[key] = rotation
    return rotation


def _get_balance(connection: sqlite3.Connection, user_id: int, currency_code: str) -> int:
    row = connection.execute(
        "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
        (user_id, currency_code),
    ).fetchone()
    return int(row["amount"]) if row else 0


async def purchase(user_id: int, rotation_item_id: int, request_id: str) -> PurchaseResult:
    """Execute the SQLite purchase outside the bot event loop.

    Black Market purchase uses BEGIN IMMEDIATE and may briefly wait for another writer.
    Running that synchronous transaction directly in an aiogram callback used to freeze
    callback processing, so Telegram showed an endless spinner and the user received no
    useful feedback. A dedicated worker thread keeps the bot responsive while preserving
    the exact same atomic SQLite transaction and request-id idempotency.
    """
    try:
        return await asyncio.to_thread(_purchase_impl_sync, user_id, rotation_item_id, request_id)
    except BlackMarketError:
        raise
    except sqlite3.Error as error:
        logger.exception(
            "Black Market purchase DB error: user_id=%s rotation_item_id=%s",
            user_id,
            rotation_item_id,
        )
        error_log.record_error(
            "black_market.purchase",
            error,
            context=f"user_id={user_id} rotation_item_id={rotation_item_id}",
        )
        raise BlackMarketError(
            "PURCHASE_FAILED",
            "Не удалось завершить покупку. Попробуйте ещё раз.",
        ) from error


def _purchase_impl_sync(user_id: int, rotation_item_id: int, request_id: str) -> PurchaseResult:
    request_id = (request_id or "").strip()
    if not request_id:
        raise BlackMarketError("REQUEST_ID_REQUIRED", "request_id обязателен для покупки.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        settings_row = get_settings(connection)
        if not bool(settings_row["shop_enabled"]):
            raise BlackMarketError("SHOP_DISABLED", "Чёрный рынок временно закрыт администрацией.")

        # 3. Идемпотентность: повторный клик с тем же request_id не должен списать дважды.
        existing = connection.execute(
            "SELECT * FROM black_market_purchases WHERE user_id = ? AND request_id = ?",
            (user_id, request_id),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            if int(existing["rotation_item_id"]) != rotation_item_id:
                raise BlackMarketError("REQUEST_ID_CONFLICT", "request_id уже использован для другой покупки.")
            with get_connection() as read_connection:
                balance = _get_balance(read_connection, user_id, existing["price_currency_code"])
                replayed_item = read_connection.execute(
                    "SELECT item_type, name FROM black_market_user_rotation_items WHERE id = ?",
                    (rotation_item_id,),
                ).fetchone()
            return PurchaseResult(
                success=True,
                rotation_item_id=rotation_item_id,
                item_type=replayed_item["item_type"] if replayed_item else "",
                name=replayed_item["name"] if replayed_item else "",
                price_currency_code=existing["price_currency_code"],
                price_amount=int(existing["price_amount"]),
                new_balance=balance,
                new_remaining_stock=-1,
                replayed=True,
            )

        # 3-4. rotation_item существует и принадлежит вызывающему пользователю.
        item_row = connection.execute(
            "SELECT * FROM black_market_user_rotation_items WHERE id = ?", (rotation_item_id,)
        ).fetchone()
        if item_row is None:
            raise BlackMarketError("ITEM_NOT_FOUND", "Товар не найден.")

        rotation_row = connection.execute(
            "SELECT * FROM black_market_user_rotations WHERE id = ?", (item_row["user_rotation_id"],)
        ).fetchone()
        if rotation_row is None or int(rotation_row["user_id"]) != user_id:
            raise BlackMarketError("ITEM_NOT_OWNED", "Этот товар не принадлежит вашей витрине.")

        # 2. business_date и статус ротации — старая/чужая витрина не покупается.
        current_version = int(settings_row["global_rotation_version"])
        today = business_date()
        if (
            rotation_row["status"] != "ACTIVE"
            or str(rotation_row["business_date"]) != today
            or int(rotation_row["rotation_version"]) != current_version
        ):
            raise BlackMarketError("ROTATION_EXPIRED", "Витрина устарела, откройте Чёрный рынок заново.")

        # Проверяем сначала специфичную причину недоступности: SOLD_OUT/нулевой сток —
        # это OUT_OF_STOCK, а не общий ITEM_UNAVAILABLE (важно для UX и для тестов).
        if item_row["item_status"] == "SOLD_OUT" or int(item_row["remaining_personal_stock"]) <= 0:
            raise BlackMarketError("OUT_OF_STOCK", "Товар распродан.")
        if item_row["item_status"] != "AVAILABLE":
            raise BlackMarketError("ITEM_UNAVAILABLE", "Товар больше недоступен.")

        pool_row = connection.execute(
            "SELECT * FROM black_market_pool_items WHERE id = ?", (item_row["pool_item_id"],)
        ).fetchone()
        if pool_row is None or not bool(pool_row["active"]):
            raise BlackMarketError("ITEM_UNAVAILABLE", "Товар больше недоступен.")

        # 6. Личный лимит покупок (сток уже проверен выше).

        limit = int(item_row["personal_purchase_limit"])
        if limit > 0 and int(item_row["purchased_quantity"]) >= limit:
            raise BlackMarketError("PURCHASE_LIMIT_REACHED", "Лимит покупок этого товара исчерпан.")

        price_currency_code = item_row["price_currency_code"]
        price_amount = int(item_row["price_amount"])

        # 7-8. Цена — снапшот на момент генерации (не зависит от последующих правок пула).
        if price_amount > 0:
            deduct_cursor = connection.execute(
                """
                UPDATE currency_balances
                SET amount = amount - ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND currency_code = ? AND amount >= ?
                """,
                (price_amount, user_id, price_currency_code, price_amount),
            )
            if deduct_cursor.rowcount != 1:
                raise BlackMarketError("INSUFFICIENT_CURRENCY", "Недостаточно средств для покупки.")

        # 9. Выдача предмета.
        grant_item(connection, user_id, item_row)

        # 10-11. Личный сток (PERSONAL stock_mode — не трогает витрины других игроков).
        stock_cursor = connection.execute(
            """
            UPDATE black_market_user_rotation_items
            SET remaining_personal_stock = remaining_personal_stock - 1,
                purchased_quantity = purchased_quantity + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND remaining_personal_stock > 0
            """,
            (rotation_item_id,),
        )
        if stock_cursor.rowcount != 1:
            raise BlackMarketError("OUT_OF_STOCK", "Товар распродан.")

        new_remaining = int(item_row["remaining_personal_stock"]) - 1
        if new_remaining <= 0:
            connection.execute(
                "UPDATE black_market_user_rotation_items SET item_status = 'SOLD_OUT' WHERE id = ?",
                (rotation_item_id,),
            )

        # 12-13. Лог покупки + аудит.
        connection.execute(
            """
            INSERT INTO black_market_purchases
                (user_id, user_rotation_id, rotation_item_id, request_id, price_currency_code, price_amount, status)
            VALUES (?, ?, ?, ?, ?, ?, 'success')
            """,
            (user_id, rotation_row["id"], rotation_item_id, request_id, price_currency_code, price_amount),
        )

        new_balance = _get_balance(connection, user_id, price_currency_code)
        connection.commit()

    invalidate_user_cache(user_id)

    return PurchaseResult(
        success=True,
        rotation_item_id=rotation_item_id,
        item_type=item_row["item_type"],
        name=item_row["name"],
        price_currency_code=price_currency_code,
        price_amount=price_amount,
        new_balance=new_balance,
        new_remaining_stock=max(0, new_remaining),
    )
