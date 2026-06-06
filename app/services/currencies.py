from dataclasses import dataclass

from app.database.db import get_connection
from app.database.schema import DEFAULT_CURRENCIES
from app.services.settings import get_int_setting
from config import settings


@dataclass(frozen=True)
class CurrencyBalance:
    code: str
    name: str
    icon: str
    amount: int


START_BALANCES = {
    "coins": settings.start_coins,
    "energy": settings.start_energy,
    "rank_point": settings.start_rank_points,
}


def format_currency_amount(balance: CurrencyBalance) -> str:
    return f"{balance.icon} {balance.name}: <b>{balance.amount:,}</b>".replace(",", " ")


async def ensure_user_balances(user_id: int, is_new_player: bool) -> None:
    with get_connection() as connection:
        start_balances = {
            "coins": await get_int_setting("start_coins", settings.start_coins, minimum=0),
            "energy": await get_int_setting("start_energy", settings.start_energy, minimum=0),
            "rank_point": await get_int_setting("start_rank_points", settings.start_rank_points, minimum=0),
        }

        for currency in DEFAULT_CURRENCIES:
            code = currency["code"]
            start_amount = start_balances.get(code, 0) if is_new_player else 0

            connection.execute(
                """
                INSERT INTO currency_balances (user_id, currency_code, amount)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, currency_code) DO NOTHING
                """,
                (user_id, code, start_amount),
            )

        connection.commit()


async def get_user_balances(user_id: int) -> list[CurrencyBalance]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                c.code,
                c.name,
                c.icon,
                cb.amount
            FROM currency_balances cb
            JOIN currencies c ON c.code = cb.currency_code
            WHERE cb.user_id = ? AND c.active = 1
            ORDER BY
                CASE c.code
                    WHEN 'coins' THEN 1
                    WHEN 'energy' THEN 2
                    WHEN 'rank_point' THEN 3
                    ELSE 99
                END,
                c.name
            """,
            (user_id,),
        )
        rows = cursor.fetchall()

    return [
        CurrencyBalance(
            code=row["code"],
            name=row["name"],
            icon=row["icon"],
            amount=row["amount"],
        )
        for row in rows
    ]
