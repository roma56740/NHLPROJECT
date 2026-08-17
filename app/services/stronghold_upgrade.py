"""UpgradePreviewService / UpgradeExecutionService для цепочки Miro Heiskanen 92->99.

Атомарность и идемпотентность — см. docs/THE_STRONGHOLD_SPEC.md, раздел 4.3.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.match_guard import has_active_match
from app.services.salary import STRONGHOLD_SALARY_CAP
from app.services.stronghold_common import (
    COINS_CURRENCY_CODE,
    FT_CURRENCY_CODE,
    StrongholdError,
    STRONGHOLD_SLUG,
    parse_db_datetime,
    sync_event_status,
    utc_now,
)
from app.services.stronghold_wallet import debit, get_balance

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpgradePreview:
    user_card_id: int
    from_card_id: int
    from_overall: int
    to_card_id: int
    to_overall: int
    to_card_name: str
    ft_cost: int
    coins_cost: int
    ft_balance: int
    coins_balance: int
    new_salary: int
    salary_cap_warning: bool
    blocking_reason: str | None


@dataclass(frozen=True)
class UpgradeResult:
    success: bool
    user_card_id: int
    from_card_id: int
    to_card_id: int
    to_overall: int
    ft_spent: int
    coins_spent: int
    ft_balance: int
    coins_balance: int
    replayed: bool = False


def _load_event_and_card(connection: sqlite3.Connection, user_id: int, user_card_id: int):
    event_row = connection.execute(
        "SELECT * FROM stronghold_events WHERE slug = ?", (STRONGHOLD_SLUG,)
    ).fetchone()
    if event_row is None:
        raise StrongholdError("EVENT_NOT_ACTIVE", "Событие THE STRONGHOLD не найдено.")
    state = sync_event_status(connection, int(event_row["id"]))

    card_row = connection.execute(
        """
        SELECT user_cards.id, user_cards.user_id, user_cards.card_id, user_cards.is_in_lineup,
               user_cards.trade_locked, user_cards.lock_until,
               cards.overall, cards.salary
        FROM user_cards
        JOIN cards ON cards.id = user_cards.card_id
        WHERE user_cards.id = ?
        """,
        (user_card_id,),
    ).fetchone()
    if card_row is None:
        raise StrongholdError("CARD_NOT_FOUND", "Карточка не найдена.")
    if int(card_row["user_id"]) != user_id:
        raise StrongholdError("CARD_NOT_OWNED", "Эта карточка вам не принадлежит.")

    step_row = connection.execute(
        "SELECT * FROM stronghold_upgrade_steps WHERE event_id = ? AND from_card_id = ?",
        (state.id, card_row["card_id"]),
    ).fetchone()
    if step_row is None:
        max_step = connection.execute(
            "SELECT to_card_id FROM stronghold_upgrade_steps WHERE event_id = ? ORDER BY step_order DESC LIMIT 1",
            (state.id,),
        ).fetchone()
        if max_step is not None and int(max_step["to_card_id"]) == int(card_row["card_id"]):
            raise StrongholdError("CARD_ALREADY_MAX_LEVEL", "Карта уже достигла максимального уровня (99).")
        raise StrongholdError("CARD_NOT_IN_UPGRADE_CHAIN", "Эта карта не участвует в Upgrade Chain THE STRONGHOLD.")

    to_card_row = connection.execute(
        "SELECT id, name, overall, salary FROM cards WHERE id = ?", (step_row["to_card_id"],)
    ).fetchone()
    if to_card_row is None:
        raise StrongholdError("UPGRADE_STEP_NOT_FOUND", "Следующий шаг апгрейда не настроен.")

    return state, card_row, step_row, to_card_row


def _lineup_lock_reason(connection: sqlite3.Connection, user_id: int, user_card_id: int, card_row: sqlite3.Row) -> str | None:
    if bool(card_row["trade_locked"]):
        return "CARD_LOCKED"
    lock_until = parse_db_datetime(card_row["lock_until"])
    if lock_until and lock_until > utc_now():
        return "CARD_LOCKED"

    pending_trade = connection.execute(
        """
        SELECT 1 FROM trade_offer_cards toc
        JOIN trade_offers t ON t.id = toc.offer_id
        WHERE toc.user_card_id = ? AND t.status = 'pending'
        LIMIT 1
        """,
        (user_card_id,),
    ).fetchone()
    if pending_trade is not None:
        return "CARD_IN_PENDING_TRADE"

    return None


def _projected_lineup_salary(connection: sqlite3.Connection, user_id: int, card_row: sqlite3.Row, new_salary: int) -> int | None:
    if not bool(card_row["is_in_lineup"]):
        return None
    total_row = connection.execute(
        """
        SELECT COALESCE(SUM(cards.salary), 0) AS total
        FROM user_cards
        JOIN cards ON cards.id = user_cards.card_id
        WHERE user_cards.user_id = ? AND user_cards.is_in_lineup = 1
        """,
        (user_id,),
    ).fetchone()
    current_total = int(total_row["total"])
    return current_total - int(card_row["salary"]) + new_salary


async def ensure_starter_card(user_id: int) -> None:
    """Выдаёт стартовую Miro Heiskanen 92, если у игрока ещё нет ни одной карты цепочки.

    Именно с этой карты начинается участие в Upgrade Chain THE STRONGHOLD; спека описывает
    только сам апгрейд 92->99, старт цепочки выдаётся один раз при первом визите в событие.
    """
    from app.services.stronghold_common import get_active_event

    event = await get_active_event()
    if event is None or event.status not in ("ACTIVE", "GRACE_PERIOD"):
        return

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        first_step = connection.execute(
            "SELECT from_card_id FROM stronghold_upgrade_steps WHERE event_id = ? ORDER BY step_order ASC LIMIT 1",
            (event.id,),
        ).fetchone()
        if first_step is None:
            connection.rollback()
            return

        chain_card_ids = [
            int(row["from_card_id"]) for row in connection.execute(
                "SELECT from_card_id FROM stronghold_upgrade_steps WHERE event_id = ?", (event.id,)
            ).fetchall()
        ] + [
            int(row["to_card_id"]) for row in connection.execute(
                "SELECT to_card_id FROM stronghold_upgrade_steps WHERE event_id = ?", (event.id,)
            ).fetchall()
        ]
        placeholders = ",".join("?" for _ in chain_card_ids)
        existing = connection.execute(
            f"SELECT 1 FROM user_cards WHERE user_id = ? AND card_id IN ({placeholders}) LIMIT 1",
            (user_id, *chain_card_ids),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            return

        connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked) VALUES (?, ?, 'stronghold_starter', 0, 0)",
            (user_id, int(first_step["from_card_id"])),
        )
        connection.commit()


async def preview_upgrade(user_id: int, user_card_id: int) -> UpgradePreview:
    with get_connection() as connection:
        state, card_row, step_row, to_card_row = _load_event_and_card(connection, user_id, user_card_id)

        blocking_reason: str | None = None
        if state.status in ("DRAFT", "SCHEDULED"):
            blocking_reason = "EVENT_NOT_ACTIVE"
        elif state.status == "ARCHIVED":
            blocking_reason = "UPGRADE_GRACE_PERIOD_ENDED"

        if blocking_reason is None:
            blocking_reason = _lineup_lock_reason(connection, user_id, user_card_id, card_row)

        if blocking_reason is None and await has_active_match(user_id):
            blocking_reason = "CARD_IN_ACTIVE_MATCH"

        ft_cost = int(step_row["ft_cost"])
        coins_cost = int(step_row["coins_cost"])
        coins_balance = get_balance(connection, user_id, COINS_CURRENCY_CODE)
        ft_balance = get_balance(connection, user_id, FT_CURRENCY_CODE)

        if blocking_reason is None and coins_balance < coins_cost:
            blocking_reason = "INSUFFICIENT_COINS"
        if blocking_reason is None and ft_balance < ft_cost:
            blocking_reason = "INSUFFICIENT_FORTRESS_TOKENS"

        new_salary = int(to_card_row["salary"])
        projected_salary = _projected_lineup_salary(connection, user_id, card_row, new_salary)
        salary_cap_warning = projected_salary is not None and projected_salary > STRONGHOLD_SALARY_CAP
        if blocking_reason is None and salary_cap_warning:
            blocking_reason = "SALARY_CAP_EXCEEDED"

    return UpgradePreview(
        user_card_id=user_card_id,
        from_card_id=int(card_row["card_id"]),
        from_overall=int(card_row["overall"]),
        to_card_id=int(to_card_row["id"]),
        to_overall=int(to_card_row["overall"]),
        to_card_name=to_card_row["name"],
        ft_cost=ft_cost,
        coins_cost=coins_cost,
        ft_balance=ft_balance,
        coins_balance=coins_balance,
        new_salary=new_salary,
        salary_cap_warning=salary_cap_warning,
        blocking_reason=blocking_reason,
    )


async def confirm_upgrade(user_id: int, user_card_id: int, request_id: str) -> UpgradeResult:
    """Публичная обёртка: измеряет длительность и пишет структурированный лог
    (см. `stronghold_common.log_stronghold_operation`) вокруг `_confirm_upgrade_impl`."""
    from app.services.stronghold_common import OperationTimer, log_stronghold_operation

    with OperationTimer() as timer:
        try:
            result = await _confirm_upgrade_impl(user_id, user_card_id, request_id)
        except StrongholdError as error:
            log_stronghold_operation(
                "upgrade_confirm", user_id=user_id, result="error",
                duration_ms=timer.duration_ms, error_code=error.code,
            )
            raise
    log_stronghold_operation(
        "upgrade_confirm", user_id=user_id, result="success", duration_ms=timer.duration_ms,
        to_overall=result.to_overall, replayed=result.replayed, ft_spent=result.ft_spent, coins_spent=result.coins_spent,
    )
    return result


async def _confirm_upgrade_impl(user_id: int, user_card_id: int, request_id: str) -> UpgradeResult:
    request_id = (request_id or "").strip()
    if not request_id:
        raise StrongholdError("REQUEST_ID_CONFLICT", "request_id обязателен для подтверждения апгрейда.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing_tx = connection.execute(
            "SELECT * FROM stronghold_upgrade_transactions WHERE user_id = ? AND request_id = ?",
            (user_id, request_id),
        ).fetchone()
        if existing_tx is not None:
            connection.rollback()
            if int(existing_tx["user_card_id"]) != user_card_id:
                raise StrongholdError("REQUEST_ID_CONFLICT", "request_id уже использован для другой операции.")
            if str(existing_tx["status"]) != "success":
                raise StrongholdError("UPGRADE_ALREADY_PROCESSED", "Операция уже обрабатывается.")
            with get_connection() as read_connection:
                coins_balance = get_balance(read_connection, user_id, COINS_CURRENCY_CODE)
                ft_balance = get_balance(read_connection, user_id, FT_CURRENCY_CODE)
            return UpgradeResult(
                success=True,
                user_card_id=user_card_id,
                from_card_id=int(existing_tx["from_card_id"]),
                to_card_id=int(existing_tx["to_card_id"]),
                to_overall=0,
                ft_spent=int(existing_tx["ft_spent"]),
                coins_spent=int(existing_tx["coins_spent"]),
                ft_balance=ft_balance,
                coins_balance=coins_balance,
                replayed=True,
            )

        state, card_row, step_row, to_card_row = _load_event_and_card(connection, user_id, user_card_id)

        if state.status in ("DRAFT", "SCHEDULED"):
            raise StrongholdError("EVENT_NOT_ACTIVE", "Событие THE STRONGHOLD ещё не началось.")
        if state.status == "ARCHIVED":
            raise StrongholdError("UPGRADE_GRACE_PERIOD_ENDED", "Grace Period завершён, апгрейды закрыты.")

        lock_reason = _lineup_lock_reason(connection, user_id, user_card_id, card_row)
        if lock_reason:
            raise StrongholdError(lock_reason, "Карта временно недоступна для апгрейда.")

        if await has_active_match(user_id):
            raise StrongholdError("CARD_IN_ACTIVE_MATCH", "Дождитесь завершения текущего матча.")

        ft_cost = int(step_row["ft_cost"])
        coins_cost = int(step_row["coins_cost"])
        coins_balance = get_balance(connection, user_id, COINS_CURRENCY_CODE)
        ft_balance = get_balance(connection, user_id, FT_CURRENCY_CODE)
        if coins_balance < coins_cost:
            raise StrongholdError("INSUFFICIENT_COINS", "Недостаточно Coins для апгрейда.")
        if ft_balance < ft_cost:
            raise StrongholdError("INSUFFICIENT_FORTRESS_TOKENS", "Недостаточно Fortress Tokens для апгрейда.")

        new_salary = int(to_card_row["salary"])
        projected_salary = _projected_lineup_salary(connection, user_id, card_row, new_salary)
        if projected_salary is not None and projected_salary > STRONGHOLD_SALARY_CAP:
            raise StrongholdError("SALARY_CAP_EXCEEDED", "Апгрейд превысит зарплатный потолок THE STRONGHOLD.")

        from_card_id = int(card_row["card_id"])
        to_card_id = int(to_card_row["id"])

        if coins_cost > 0:
            debit(
                connection,
                user_id=user_id,
                event_id=state.id,
                currency_code=COINS_CURRENCY_CODE,
                amount=coins_cost,
                reason="upgrade_spend",
                reference_type="upgrade_step",
                reference_id=int(step_row["id"]),
                insufficient_error_code="INSUFFICIENT_COINS",
            )
        if ft_cost > 0:
            debit(
                connection,
                user_id=user_id,
                event_id=state.id,
                currency_code=FT_CURRENCY_CODE,
                amount=ft_cost,
                reason="upgrade_spend",
                reference_type="upgrade_step",
                reference_id=int(step_row["id"]),
                insufficient_error_code="INSUFFICIENT_FORTRESS_TOKENS",
            )

        connection.execute(
            "UPDATE user_cards SET card_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (to_card_id, user_card_id),
        )

        cursor = connection.execute(
            """
            INSERT INTO stronghold_upgrade_transactions (
                user_id, event_id, user_card_id, step_id, request_id, status,
                from_card_id, to_card_id, ft_spent, coins_spent
            ) VALUES (?, ?, ?, ?, ?, 'success', ?, ?, ?, ?)
            """,
            (user_id, state.id, user_card_id, int(step_row["id"]), request_id, from_card_id, to_card_id, ft_cost, coins_cost),
        )
        tx_id = int(cursor.lastrowid)

        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, before, after, reason, request_id)
            VALUES (?, NULL, 'upgrade_confirm', 'user_cards', ?, ?, ?, 'user_action', ?)
            """,
            (
                state.id,
                user_card_id,
                json.dumps({"card_id": from_card_id}),
                json.dumps({"card_id": to_card_id, "tx_id": tx_id}),
                request_id,
            ),
        )

        new_coins_balance = get_balance(connection, user_id, COINS_CURRENCY_CODE)
        new_ft_balance = get_balance(connection, user_id, FT_CURRENCY_CODE)

        connection.commit()

    try:
        from app.services.stronghold_missions import apply_stronghold_progress

        await apply_stronghold_progress(user_id, "upgrade_heiskanen", 1)
    except Exception:
        logger.exception("stronghold mission progress hook failed after upgrade")

    return UpgradeResult(
        success=True,
        user_card_id=user_card_id,
        from_card_id=from_card_id,
        to_card_id=to_card_id,
        to_overall=int(to_card_row["overall"]),
        ft_spent=ft_cost,
        coins_spent=coins_cost,
        ft_balance=new_ft_balance,
        coins_balance=new_coins_balance,
        replayed=False,
    )
