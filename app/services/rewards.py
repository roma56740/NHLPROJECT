"""Общие помощники для выдачи наград (валюта, паки).

Функции работают внутри переданного соединения, чтобы вызывающая сторона
могла включить выдачу в свою транзакцию (важно для защиты от дублей).
"""


def grant_currency(connection, user_id: int, currency_code: str, amount: int) -> None:
    if amount <= 0 or not currency_code:
        return
    connection.execute(
        """
        INSERT INTO currency_balances (user_id, currency_code, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, currency_code) DO UPDATE SET
            amount = amount + excluded.amount,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, currency_code, amount),
    )


def grant_pack(connection, user_id: int, pack_id: int, quantity: int = 1) -> bool:
    if pack_id is None or quantity <= 0:
        return False
    exists = connection.execute("SELECT id FROM packs WHERE id = ?", (pack_id,)).fetchone()
    if exists is None:
        return False
    connection.execute(
        """
        INSERT INTO user_packs (user_id, pack_id, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, pack_id) DO UPDATE SET
            quantity = quantity + excluded.quantity,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, pack_id, quantity),
    )
    return True
