"""Event Store THE STRONGHOLD: Featured/Packs/Cards/Resources/Bundles.

Покупка — атомарная транзакция (см. `shop.py:purchase_shop_pack`), для Bundle все
элементы выдаются одной транзакцией или откатываются полностью.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.card_distribution_policy import is_admin_only_card
from app.services.rewards import grant_currency, grant_pack
from app.services.stronghold_common import StrongholdError, get_active_event, parse_db_datetime, utc_now
from app.services.stronghold_wallet import debit, get_balance

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoreProductInfo:
    id: int
    code: str
    category: str
    title: str
    description: str
    image_path: str | None
    price_currency_code: str
    price_amount: int
    purchase_limit: int
    purchased_count: int
    available: bool
    contents: list[dict]


@dataclass(frozen=True)
class PurchaseResult:
    success: bool
    product_id: int
    price_currency_code: str
    price_amount: int
    new_balance: int
    replayed: bool = False


def _product_available(row, now) -> bool:
    if not bool(row["active"]):
        return False
    starts_at = parse_db_datetime(row["starts_at"])
    ends_at = parse_db_datetime(row["ends_at"])
    if starts_at and now < starts_at:
        return False
    if ends_at and now >= ends_at:
        return False
    return True


async def list_products(user_id: int, category: str | None = None) -> list[StoreProductInfo]:
    event = await get_active_event()
    if event is None or not event.allows_store:
        return []

    now = utc_now()
    with get_connection() as connection:
        query = "SELECT * FROM stronghold_store_products WHERE event_id = ?"
        params: list[object] = [event.id]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY sort_order, id"
        products = connection.execute(query, params).fetchall()

        result: list[StoreProductInfo] = []
        for product in products:
            purchased_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS c FROM stronghold_store_purchases WHERE user_id = ? AND product_id = ? AND status = 'success'",
                    (user_id, product["id"]),
                ).fetchone()["c"]
            )
            limit = int(product["purchase_limit"])
            within_limit = limit <= 0 or purchased_count < limit
            result.append(
                StoreProductInfo(
                    id=int(product["id"]),
                    code=product["code"],
                    category=product["category"],
                    title=product["title"],
                    description=product["description"] or "",
                    image_path=product["image_path"],
                    price_currency_code=product["price_currency_code"],
                    price_amount=int(product["price_amount"]),
                    purchase_limit=limit,
                    purchased_count=purchased_count,
                    available=_product_available(product, now) and within_limit,
                    contents=json.loads(product["contents"] or "[]"),
                )
            )
    return result


async def purchase(user_id: int, product_id: int, request_id: str) -> PurchaseResult:
    """Публичная обёртка с структурированным логированием (см. stronghold_common.log_stronghold_operation)."""
    from app.services.stronghold_common import OperationTimer, log_stronghold_operation

    with OperationTimer() as timer:
        try:
            result = await _purchase_impl(user_id, product_id, request_id)
        except StrongholdError as error:
            log_stronghold_operation(
                "store_purchase", user_id=user_id, result="error",
                duration_ms=timer.duration_ms, error_code=error.code, product_id=product_id,
            )
            raise
    log_stronghold_operation(
        "store_purchase", user_id=user_id, result="success", duration_ms=timer.duration_ms,
        product_id=product_id, price_amount=result.price_amount, replayed=result.replayed,
    )
    return result


async def _purchase_impl(user_id: int, product_id: int, request_id: str) -> PurchaseResult:
    request_id = (request_id or "").strip()
    if not request_id:
        raise StrongholdError("REQUEST_ID_CONFLICT", "request_id обязателен для покупки.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            "SELECT * FROM stronghold_store_purchases WHERE user_id = ? AND request_id = ?",
            (user_id, request_id),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            if int(existing["product_id"]) != product_id:
                raise StrongholdError("REQUEST_ID_CONFLICT", "request_id уже использован для другой покупки.")
            if str(existing["status"]) != "success":
                raise StrongholdError("PURCHASE_ALREADY_PROCESSED", "Покупка уже обрабатывается.")
            with get_connection() as read_connection:
                balance = get_balance(read_connection, user_id, existing["price_currency_code"])
            return PurchaseResult(
                success=True,
                product_id=product_id,
                price_currency_code=existing["price_currency_code"],
                price_amount=int(existing["price_amount"]),
                new_balance=balance,
                replayed=True,
            )

        event_row = connection.execute("SELECT * FROM stronghold_events WHERE id = (SELECT event_id FROM stronghold_store_products WHERE id = ?)", (product_id,)).fetchone()
        product = connection.execute("SELECT * FROM stronghold_store_products WHERE id = ?", (product_id,)).fetchone()
        if product is None or event_row is None:
            raise StrongholdError("PRODUCT_NOT_FOUND", "Товар не найден.")

        from app.services.stronghold_common import sync_event_status

        state = sync_event_status(connection, int(event_row["id"]))
        if state.status in ("DRAFT", "SCHEDULED"):
            raise StrongholdError("EVENT_NOT_ACTIVE", "Событие ещё не началось.")
        if state.status == "ARCHIVED":
            raise StrongholdError("EVENT_ARCHIVED", "Событие завершено, магазин закрыт.")
        if state.status == "GRACE_PERIOD" and not state.store_available_in_grace:
            raise StrongholdError("PRODUCT_NOT_AVAILABLE", "Магазин недоступен в Grace Period.")

        now = utc_now()
        if not _product_available(product, now):
            starts_at = parse_db_datetime(product["starts_at"])
            if starts_at and now < starts_at:
                raise StrongholdError("PRODUCT_NOT_AVAILABLE", "Товар пока недоступен.")
            raise StrongholdError("PRODUCT_EXPIRED", "Срок действия товара истёк.")

        limit = int(product["purchase_limit"])
        if limit > 0:
            purchased_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS c FROM stronghold_store_purchases WHERE user_id = ? AND product_id = ? AND status = 'success'",
                    (user_id, product_id),
                ).fetchone()["c"]
            )
            if purchased_count >= limit:
                raise StrongholdError("PURCHASE_LIMIT_REACHED", "Лимит покупок этого товара исчерпан.")

        try:
            contents = json.loads(product["contents"] or "[]")
        except json.JSONDecodeError as error:
            raise StrongholdError("INVALID_PRODUCT_CONFIGURATION", "Некорректная конфигурация товара.") from error

        price_currency_code = product["price_currency_code"]
        price_amount = int(product["price_amount"])

        if price_amount > 0:
            debit(
                connection,
                user_id=user_id,
                event_id=state.id,
                currency_code=price_currency_code,
                amount=price_amount,
                reason="store_purchase",
                reference_type="store_product",
                reference_id=product_id,
                insufficient_error_code="INSUFFICIENT_CURRENCY",
            )

        for item in contents:
            item_type = item.get("type")
            if item_type == "currency":
                grant_currency(connection, user_id, item["currency_code"], int(item["amount"]))
            elif item_type == "pack":
                if not grant_pack(connection, user_id, int(item["pack_id"]), int(item.get("amount", 1))):
                    raise StrongholdError("INVALID_PRODUCT_CONFIGURATION", "Некорректный пак в составе товара.")
            elif item_type == "card":
                card_exists = connection.execute("SELECT 1 FROM cards WHERE id = ?", (item["card_id"],)).fetchone()
                if card_exists is None:
                    raise StrongholdError("INVALID_PRODUCT_CONFIGURATION", "Некорректная карта в составе товара.")
                if is_admin_only_card(connection, int(item["card_id"])):
                    raise StrongholdError("ADMIN_ONLY_COLLECTION", "Leaders выдаются только администрацией и недоступны в магазинах.")
                for _ in range(int(item.get("amount", 1))):
                    connection.execute(
                        "INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked) VALUES (?, ?, 'stronghold_store', 0, 0)",
                        (user_id, item["card_id"]),
                    )
            else:
                raise StrongholdError("INVALID_PRODUCT_CONFIGURATION", "Неизвестный тип награды в товаре.")

        connection.execute(
            """
            INSERT INTO stronghold_store_purchases (user_id, event_id, product_id, request_id, price_currency_code, price_amount, status)
            VALUES (?, ?, ?, ?, ?, ?, 'success')
            """,
            (user_id, state.id, product_id, request_id, price_currency_code, price_amount),
        )
        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, reason, request_id)
            VALUES (?, NULL, 'store_purchase', 'stronghold_store_products', ?, 'user_action', ?)
            """,
            (state.id, product_id, request_id),
        )

        new_balance = get_balance(connection, user_id, price_currency_code)
        connection.commit()

    try:
        from app.services.stronghold_missions import apply_stronghold_progress

        if price_currency_code == "coins" and price_amount > 0:
            await apply_stronghold_progress(user_id, "spend_coins", price_amount)
        elif price_currency_code == "fortress_token" and price_amount > 0:
            await apply_stronghold_progress(user_id, "spend_ft", price_amount)
    except Exception:
        logger.exception("stronghold mission progress hook failed after store purchase")

    return PurchaseResult(success=True, product_id=product_id, price_currency_code=price_currency_code, price_amount=price_amount, new_balance=new_balance)
