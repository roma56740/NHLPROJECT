"""Quick Sell — быстрая продажа карт за Coins по базовому OVR.

Цена считается ТОЛЬКО по базовому OVR карты. Бонусы/штрафы химии на цену не влияют.
"""

from dataclasses import dataclass

from app.database.db import get_connection
from app.services.rewards import grant_currency

# OVR -> Coins. Ниже 70 — фиксировано 100.
QUICK_SELL_PRICES = {
    70: 100, 71: 120, 72: 140, 73: 160, 74: 180, 75: 220, 76: 260, 77: 320,
    78: 400, 79: 500, 80: 650, 81: 850, 82: 1100, 83: 1400, 84: 1800, 85: 2300,
    86: 3000, 87: 4000, 88: 5500, 89: 7500, 90: 10000, 91: 13000, 92: 17000,
    93: 22000, 94: 28000, 95: 35000, 96: 50000, 97: 75000, 98: 120000, 99: 250000,
}

VALUABLE_RARITIES = {"Epic", "Legendary", "Icon", "Event"}


@dataclass(frozen=True)
class QuickSellResult:
    ok: bool
    title: str
    description: str
    coins_earned: int = 0
    new_balance: int | None = None


@dataclass(frozen=True)
class BulkSellResult:
    ok: bool
    sold_count: int
    coins_earned: int
    skipped_count: int
    new_balance: int | None


def quick_sell_price(overall: int) -> int | None:
    """Цена продажи по базовому OVR. None — если OVR вне таблицы (>99)."""
    if overall > 99:
        return None
    if overall < 70:
        return 100
    return QUICK_SELL_PRICES.get(overall)


def coins_balance(connection, user_id: int) -> int:
    row = connection.execute(
        "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = 'coins'",
        (user_id,),
    ).fetchone()
    return int(row["amount"]) if row else 0


async def get_sell_preview(user_id: int, user_card_id: int) -> tuple[dict | None, str | None]:
    """Возвращает данные для экрана подтверждения продажи одной карты."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT uc.id, uc.is_in_lineup, uc.trade_locked, c.name, c.overall, c.rarity, c.position
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE uc.id = ? AND uc.user_id = ?
            """,
            (user_card_id, user_id),
        ).fetchone()

    if row is None:
        return None, "Карточка не найдена."
    if int(row["is_in_lineup"]):
        return None, "Эта карта стоит в активном составе. Сначала замени её."
    if int(row["trade_locked"]):
        return None, "Карта заблокирована (Lock Card). Сначала разблокируй её."

    price = quick_sell_price(int(row["overall"]))
    if price is None:
        return None, "Для этого OVR не задана цена продажи. Обратись к администрации."

    return {
        "name": row["name"],
        "overall": int(row["overall"]),
        "rarity": row["rarity"],
        "price": price,
        "valuable": row["rarity"] in VALUABLE_RARITIES,
    }, None


async def quick_sell_single(user_id: int, user_card_id: int) -> QuickSellResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT uc.id, uc.is_in_lineup, uc.trade_locked, c.overall, c.name
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE uc.id = ? AND uc.user_id = ?
            """,
            (user_card_id, user_id),
        ).fetchone()

        if row is None:
            connection.rollback()
            return QuickSellResult(False, "Карта не найдена", "Возможно, она уже продана.")
        if int(row["is_in_lineup"]):
            connection.rollback()
            return QuickSellResult(False, "Нельзя продать", "Карта стоит в активном составе.")
        if int(row["trade_locked"]):
            connection.rollback()
            return QuickSellResult(False, "Нельзя продать", "Карта заблокирована (Lock Card).")

        price = quick_sell_price(int(row["overall"]))
        if price is None:
            connection.rollback()
            return QuickSellResult(False, "Нет цены", "Для этого OVR не задана цена продажи.")

        # Атомарное удаление: защита от повторной продажи при спаме кнопки.
        deleted = connection.execute(
            "DELETE FROM user_cards WHERE id = ? AND user_id = ?",
            (user_card_id, user_id),
        )
        if deleted.rowcount != 1:
            connection.rollback()
            return QuickSellResult(False, "Карта не найдена", "Возможно, она уже продана.")

        grant_currency(connection, user_id, "coins", price)
        balance = coins_balance(connection, user_id)
        connection.commit()

    return QuickSellResult(
        True,
        "Карта продана",
        f"Получено 🪙 <b>{price:,}</b> Coins.".replace(",", " "),
        coins_earned=price,
        new_balance=balance,
    )


def eligible_rows_for_bulk(connection, user_id: int):
    return connection.execute(
        """
        SELECT uc.id, uc.card_id, uc.is_in_lineup, uc.trade_locked, c.overall, c.rarity
        FROM user_cards uc
        JOIN cards c ON c.id = uc.card_id
        WHERE uc.user_id = ?
        ORDER BY uc.card_id, uc.id
        """,
        (user_id,),
    ).fetchall()


async def quick_sell_bulk(user_id: int, mode: str) -> BulkSellResult:
    if mode not in ("duplicates", "common"):
        return BulkSellResult(False, 0, 0, 0, None)

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = eligible_rows_for_bulk(connection, user_id)

        to_sell: list[tuple[int, int]] = []  # (user_card_id, price)
        skipped = 0

        if mode == "common":
            for row in rows:
                if row["rarity"] != "Common":
                    continue
                if int(row["is_in_lineup"]) or int(row["trade_locked"]):
                    skipped += 1
                    continue
                price = quick_sell_price(int(row["overall"]))
                if price is None:
                    skipped += 1
                    continue
                to_sell.append((int(row["id"]), price))

        else:  # duplicates — оставляем один экземпляр каждого card_id
            groups: dict[int, list] = {}
            for row in rows:
                groups.setdefault(int(row["card_id"]), []).append(row)

            for card_id, copies in groups.items():
                if len(copies) <= 1:
                    continue
                # копии, которые нельзя продавать (в составе/заблокированы) — остаются
                protected = [r for r in copies if int(r["is_in_lineup"]) or int(r["trade_locked"])]
                sellable = [r for r in copies if not (int(r["is_in_lineup"]) or int(r["trade_locked"]))]

                # если нет защищённых, обязаны оставить одну продаваемую копию
                keep_one = len(protected) == 0
                for index, row in enumerate(sellable):
                    if keep_one and index == 0:
                        continue
                    price = quick_sell_price(int(row["overall"]))
                    if price is None:
                        skipped += 1
                        continue
                    to_sell.append((int(row["id"]), price))

        if not to_sell:
            connection.rollback()
            return BulkSellResult(True, 0, 0, skipped, coins_balance(connection, user_id) if False else None)

        total_coins = sum(price for _, price in to_sell)
        ids = [uid for uid, _ in to_sell]
        placeholders = ",".join("?" for _ in ids)
        deleted = connection.execute(
            f"DELETE FROM user_cards WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *ids),
        )
        # Начисляем строго за фактически удалённые карты.
        if deleted.rowcount != len(ids):
            connection.rollback()
            return BulkSellResult(False, 0, 0, skipped, None)

        grant_currency(connection, user_id, "coins", total_coins)
        balance = coins_balance(connection, user_id)
        connection.commit()

    return BulkSellResult(True, len(ids), total_coins, skipped, balance)


async def toggle_card_lock(user_id: int, user_card_id: int) -> tuple[bool, str, bool]:
    """Блокирует/разблокирует карту от продажи (Lock Card). Возвращает (ok, msg, locked_now)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT trade_locked FROM user_cards WHERE id = ? AND user_id = ?",
            (user_card_id, user_id),
        ).fetchone()
        if row is None:
            connection.rollback()
            return False, "Карта не найдена.", False
        new_value = 0 if int(row["trade_locked"]) else 1
        connection.execute(
            "UPDATE user_cards SET trade_locked = ?, lock_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (new_value, "user_lock" if new_value else None, user_card_id, user_id),
        )
        connection.commit()
    if new_value:
        return True, "Карта заблокирована от продажи 🔒", True
    return True, "Карта разблокирована 🔓", False
