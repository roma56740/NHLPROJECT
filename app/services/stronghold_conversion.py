"""EventConversionService: автоконвертация Fortress Tokens -> Coins после Grace Period.

Идемпотентна (UNIQUE(user_id, event_id) в stronghold_ft_conversions), работает пакетами,
безопасна для перезапуска процесса — см. docs/THE_STRONGHOLD_SPEC.md, раздел 5.6.
"""

from __future__ import annotations

import logging

from app.database.db import get_connection
from app.services.stronghold_common import COINS_CURRENCY_CODE, FT_CURRENCY_CODE
from app.services.stronghold_wallet import credit, debit

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


async def convert_archived_event_balances(event_id: int, ft_conversion_rate: int) -> int:
    """Конвертирует остатки FT в Coins для всех ещё не сконвертированных пользователей события.

    Возвращает количество обработанных пользователей в этом вызове (для логов фоновой задачи).
    """
    processed = 0
    while True:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT cb.user_id, cb.amount
                FROM currency_balances cb
                WHERE cb.currency_code = ?
                  AND cb.amount > 0
                  AND cb.user_id NOT IN (
                      SELECT user_id FROM stronghold_ft_conversions WHERE event_id = ?
                  )
                LIMIT ?
                """,
                (FT_CURRENCY_CODE, event_id, BATCH_SIZE),
            ).fetchall()

        if not rows:
            break

        for row in rows:
            user_id = int(row["user_id"])
            try:
                with get_connection() as connection:
                    connection.execute("BEGIN IMMEDIATE")

                    already = connection.execute(
                        "SELECT 1 FROM stronghold_ft_conversions WHERE user_id = ? AND event_id = ?",
                        (user_id, event_id),
                    ).fetchone()
                    if already is not None:
                        connection.rollback()
                        continue

                    balance_row = connection.execute(
                        "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
                        (user_id, FT_CURRENCY_CODE),
                    ).fetchone()
                    ft_amount = int(balance_row["amount"]) if balance_row else 0

                    if ft_amount <= 0:
                        connection.execute(
                            "INSERT INTO stronghold_ft_conversions (user_id, event_id, ft_converted, coins_granted) VALUES (?, ?, 0, 0)",
                            (user_id, event_id),
                        )
                        connection.commit()
                        processed += 1
                        continue

                    coins_amount = ft_amount * ft_conversion_rate

                    debit(
                        connection,
                        user_id=user_id,
                        event_id=event_id,
                        currency_code=FT_CURRENCY_CODE,
                        amount=ft_amount,
                        reason="ft_conversion",
                        reference_type="conversion",
                    )
                    credit(
                        connection,
                        user_id=user_id,
                        event_id=event_id,
                        currency_code=COINS_CURRENCY_CODE,
                        amount=coins_amount,
                        reason="ft_conversion",
                        reference_type="conversion",
                    )
                    connection.execute(
                        "INSERT INTO stronghold_ft_conversions (user_id, event_id, ft_converted, coins_granted) VALUES (?, ?, ?, ?)",
                        (user_id, event_id, ft_amount, coins_amount),
                    )
                    connection.execute(
                        """
                        INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, reason)
                        VALUES (?, NULL, 'ft_auto_conversion', 'users', ?, 'grace_period_ended')
                        """,
                        (event_id, user_id),
                    )
                    connection.commit()
                    processed += 1
            except Exception:
                logger.exception("stronghold FT conversion failed for user_id=%s event_id=%s", user_id, event_id)

    return processed
