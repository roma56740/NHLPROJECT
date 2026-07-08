from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.currencies import ensure_user_balances


@dataclass(frozen=True)
class ShopPackItem:
    id: int
    code: str
    name: str
    description: str
    image_path: str | None
    price_currency_code: str | None
    price_currency_name: str | None
    price_currency_icon: str | None
    price_amount: int
    cards_count: int
    selected_cards_count: int
    user_quantity: int


@dataclass(frozen=True)
class ShopPacksPage:
    packs: list[ShopPackItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class ShopPurchaseItem:
    id: int
    pack_name: str
    currency_code: str | None
    currency_name: str | None
    currency_icon: str | None
    amount: int
    created_at: str


@dataclass(frozen=True)
class ShopHistoryPage:
    purchases: list[ShopPurchaseItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class ShopPurchaseResult:
    pack_id: int
    pack_name: str
    quantity: int
    price_currency_code: str | None
    price_currency_name: str | None
    price_currency_icon: str | None
    price_amount: int
    balance_after: int | None


def row_to_shop_pack(row) -> ShopPackItem:
    return ShopPackItem(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        description=row["description"],
        image_path=row["image_path"],
        price_currency_code=row["price_currency_code"],
        price_currency_name=row["price_currency_name"],
        price_currency_icon=row["price_currency_icon"],
        price_amount=row["price_amount"],
        cards_count=row["cards_count"],
        selected_cards_count=row["selected_cards_count"],
        user_quantity=row["user_quantity"],
    )


async def get_shop_packs_page(user_id: int, page: int = 1, per_page: int = 5) -> ShopPacksPage:
    with get_connection() as connection:
        count_cursor = connection.execute(
            """
            SELECT COUNT(*) AS total_count
            FROM packs
            WHERE active = 1 AND is_shop_available = 1
            """
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                packs.id,
                packs.code,
                packs.name,
                packs.description,
                packs.image_path,
                packs.price_currency_code,
                packs.price_amount,
                currencies.name AS price_currency_name,
                currencies.icon AS price_currency_icon,
                COUNT(DISTINCT pack_slots.id) AS cards_count,
                COUNT(DISTINCT pack_cards.card_id) AS selected_cards_count,
                COALESCE(user_packs.quantity, 0) AS user_quantity
            FROM packs
            LEFT JOIN currencies ON currencies.code = packs.price_currency_code
            LEFT JOIN pack_slots ON pack_slots.pack_id = packs.id AND pack_slots.active = 1
            LEFT JOIN pack_cards ON pack_cards.pack_id = packs.id
            LEFT JOIN user_packs ON user_packs.pack_id = packs.id AND user_packs.user_id = ?
            WHERE packs.active = 1 AND packs.is_shop_available = 1
            GROUP BY packs.id
            ORDER BY packs.sort_order, packs.id
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, offset),
        )
        rows = cursor.fetchall()

    return ShopPacksPage(
        packs=[row_to_shop_pack(row) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )


async def get_shop_pack_details(user_id: int, pack_id: int) -> ShopPackItem | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                packs.id,
                packs.code,
                packs.name,
                packs.description,
                packs.image_path,
                packs.price_currency_code,
                packs.price_amount,
                currencies.name AS price_currency_name,
                currencies.icon AS price_currency_icon,
                COUNT(DISTINCT pack_slots.id) AS cards_count,
                COUNT(DISTINCT pack_cards.card_id) AS selected_cards_count,
                COALESCE(user_packs.quantity, 0) AS user_quantity
            FROM packs
            LEFT JOIN currencies ON currencies.code = packs.price_currency_code
            LEFT JOIN pack_slots ON pack_slots.pack_id = packs.id AND pack_slots.active = 1
            LEFT JOIN pack_cards ON pack_cards.pack_id = packs.id
            LEFT JOIN user_packs ON user_packs.pack_id = packs.id AND user_packs.user_id = ?
            WHERE packs.id = ? AND packs.active = 1 AND packs.is_shop_available = 1
            GROUP BY packs.id
            """,
            (user_id, pack_id),
        )
        row = cursor.fetchone()

    return row_to_shop_pack(row) if row else None


async def purchase_shop_pack(user_id: int, pack_id: int) -> tuple[ShopPurchaseResult | None, str | None]:
    await ensure_user_balances(user_id, is_new_player=False)

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        pack_cursor = connection.execute(
            """
            SELECT
                packs.id,
                packs.name,
                packs.price_currency_code,
                packs.price_amount,
                currencies.name AS price_currency_name,
                currencies.icon AS price_currency_icon,
                COUNT(DISTINCT pack_cards.card_id) AS selected_cards_count
            FROM packs
            LEFT JOIN currencies ON currencies.code = packs.price_currency_code
            LEFT JOIN pack_cards ON pack_cards.pack_id = packs.id
            WHERE packs.id = ? AND packs.active = 1 AND packs.is_shop_available = 1
            GROUP BY packs.id
            """,
            (pack_id,),
        )
        pack_row = pack_cursor.fetchone()

        if pack_row is None:
            connection.rollback()
            return None, "Пак уже недоступен в магазине."

        if int(pack_row["selected_cards_count"] or 0) <= 0:
            connection.rollback()
            return None, "Пак скоро появится. Состав наград ещё готовится."

        price_amount = int(pack_row["price_amount"] or 0)
        currency_code = pack_row["price_currency_code"]
        balance_after: int | None = None

        try:
            if price_amount <= 0 or currency_code is None:
                owned_cursor = connection.execute(
                    """
                    SELECT quantity
                    FROM user_packs
                    WHERE user_id = ? AND pack_id = ?
                    """,
                    (user_id, pack_id),
                )
                owned_row = owned_cursor.fetchone()
                opening_cursor = connection.execute(
                    """
                    SELECT id
                    FROM pack_openings
                    WHERE user_id = ? AND pack_id = ?
                    LIMIT 1
                    """,
                    (user_id, pack_id),
                )

                if owned_row is not None and int(owned_row["quantity"] or 0) > 0:
                    connection.rollback()
                    return None, "Подарочный пак уже ждёт открытия."

                if opening_cursor.fetchone() is not None:
                    connection.rollback()
                    return None, "Подарочный пак уже был получен. Такой бонус доступен один раз."
            else:
                balance_cursor = connection.execute(
                    """
                    SELECT amount
                    FROM currency_balances
                    WHERE user_id = ? AND currency_code = ?
                    """,
                    (user_id, currency_code),
                )
                balance_row = balance_cursor.fetchone()
                current_balance = int(balance_row["amount"] if balance_row else 0)

                if current_balance < price_amount:
                    connection.rollback()
                    return None, "Недостаточно средств для покупки."

                balance_after = current_balance - price_amount
                deduct_cursor = connection.execute(
                    """
                    UPDATE currency_balances
                    SET amount = amount - ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND currency_code = ? AND amount >= ?
                    """,
                    (price_amount, user_id, currency_code, price_amount),
                )

                if deduct_cursor.rowcount != 1:
                    connection.rollback()
                    return None, "Недостаточно средств для покупки."

            connection.execute(
                """
                INSERT INTO user_packs (user_id, pack_id, quantity)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, pack_id) DO UPDATE SET
                    quantity = user_packs.quantity + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, pack_id),
            )
            connection.execute(
                """
                INSERT INTO shop_purchases (user_id, pack_id, currency_code, amount)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, pack_id, currency_code, price_amount),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return ShopPurchaseResult(
        pack_id=pack_row["id"],
        pack_name=pack_row["name"],
        quantity=1,
        price_currency_code=currency_code,
        price_currency_name=pack_row["price_currency_name"],
        price_currency_icon=pack_row["price_currency_icon"],
        price_amount=price_amount,
        balance_after=balance_after,
    ), None


async def get_shop_history_page(user_id: int, page: int = 1, per_page: int = 5) -> ShopHistoryPage:
    with get_connection() as connection:
        count_cursor = connection.execute(
            "SELECT COUNT(*) AS total_count FROM shop_purchases WHERE user_id = ?",
            (user_id,),
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                shop_purchases.id,
                packs.name AS pack_name,
                shop_purchases.currency_code,
                shop_purchases.amount,
                shop_purchases.created_at,
                currencies.name AS currency_name,
                currencies.icon AS currency_icon
            FROM shop_purchases
            JOIN packs ON packs.id = shop_purchases.pack_id
            LEFT JOIN currencies ON currencies.code = shop_purchases.currency_code
            WHERE shop_purchases.user_id = ?
            ORDER BY shop_purchases.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, offset),
        )
        rows = cursor.fetchall()

    return ShopHistoryPage(
        purchases=[
            ShopPurchaseItem(
                id=row["id"],
                pack_name=row["pack_name"],
                currency_code=row["currency_code"],
                currency_name=row["currency_name"],
                currency_icon=row["currency_icon"],
                amount=row["amount"],
                created_at=row["created_at"],
            )
            for row in rows
        ],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )
