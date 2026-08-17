"""EventWalletService / EventCurrencyLedgerService эквивалент для THE STRONGHOLD.

FT и Coins хранятся в существующей универсальной таблице `currency_balances`
(см. docs/THE_STRONGHOLD_SPEC.md, раздел 4.1) — здесь только ledger-обвязка поверх неё.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.stronghold_common import COINS_CURRENCY_CODE, FT_CURRENCY_CODE, StrongholdError


@dataclass(frozen=True)
class WalletInfo:
    coins: int
    fortress_tokens: int


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    currency_code: str
    delta: int
    balance_after: int
    reason: str
    reference_type: str | None
    reference_id: int | None
    created_at: str


@dataclass(frozen=True)
class LedgerPage:
    entries: list[LedgerEntry]
    page: int
    pages_count: int
    total_count: int


def get_balance(connection: sqlite3.Connection, user_id: int, currency_code: str) -> int:
    row = connection.execute(
        "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
        (user_id, currency_code),
    ).fetchone()
    return int(row["amount"]) if row else 0


def credit(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    event_id: int,
    currency_code: str,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
) -> int:
    """Начисляет валюту и пишет ledger-запись. Вызывать внутри открытой транзакции. Возвращает новый баланс."""
    if amount <= 0:
        return get_balance(connection, user_id, currency_code)

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
    new_balance = get_balance(connection, user_id, currency_code)
    _write_ledger(
        connection,
        user_id=user_id,
        event_id=event_id,
        currency_code=currency_code,
        delta=amount,
        balance_after=new_balance,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    return new_balance


def debit(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    event_id: int,
    currency_code: str,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
    insufficient_error_code: str = "INSUFFICIENT_CURRENCY",
) -> int:
    """Гарантированно неотрицательное списание (guarded UPDATE, как в shop.py). Кидает StrongholdError."""
    if amount <= 0:
        return get_balance(connection, user_id, currency_code)

    cursor = connection.execute(
        """
        UPDATE currency_balances
        SET amount = amount - ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND currency_code = ? AND amount >= ?
        """,
        (amount, user_id, currency_code, amount),
    )
    if cursor.rowcount != 1:
        raise StrongholdError(insufficient_error_code, "Недостаточно средств.")

    new_balance = get_balance(connection, user_id, currency_code)
    _write_ledger(
        connection,
        user_id=user_id,
        event_id=event_id,
        currency_code=currency_code,
        delta=-amount,
        balance_after=new_balance,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    return new_balance


def _write_ledger(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    event_id: int,
    currency_code: str,
    delta: int,
    balance_after: int,
    reason: str,
    reference_type: str | None,
    reference_id: int | None,
) -> None:
    connection.execute(
        """
        INSERT INTO stronghold_currency_ledger (
            user_id, event_id, currency_code, delta, balance_after, reason, reference_type, reference_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, event_id, currency_code, delta, balance_after, reason, reference_type, reference_id),
    )


async def get_wallet(user_id: int) -> WalletInfo:
    with get_connection() as connection:
        coins = get_balance(connection, user_id, COINS_CURRENCY_CODE)
        ft = get_balance(connection, user_id, FT_CURRENCY_CODE)
    return WalletInfo(coins=coins, fortress_tokens=ft)


async def get_currency_history(user_id: int, event_id: int, page: int = 1, per_page: int = 10) -> LedgerPage:
    with get_connection() as connection:
        total_count = int(
            connection.execute(
                "SELECT COUNT(*) AS c FROM stronghold_currency_ledger WHERE user_id = ? AND event_id = ?",
                (user_id, event_id),
            ).fetchone()["c"]
        )
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        rows = connection.execute(
            """
            SELECT id, currency_code, delta, balance_after, reason, reference_type, reference_id, created_at
            FROM stronghold_currency_ledger
            WHERE user_id = ? AND event_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, event_id, per_page, offset),
        ).fetchall()

    entries = [
        LedgerEntry(
            id=int(row["id"]),
            currency_code=row["currency_code"],
            delta=int(row["delta"]),
            balance_after=int(row["balance_after"]),
            reason=row["reason"],
            reference_type=row["reference_type"],
            reference_id=row["reference_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return LedgerPage(entries=entries, page=safe_page, pages_count=pages_count, total_count=total_count)
