"""Проверки безопасности: IDOR, подмена данных, ролевой доступ, инъекции, лимиты.

Сервер — единственный источник истины (см. THE_STRONGHOLD_SPEC.md, раздел 10): ни один
тест здесь не проверяет "фронтенд", так как его нет — все проверки идут напрямую в
сервисный слой, который и есть граница доверия в Telegram-боте (все данные, кроме
идентификаторов из callback_data, вычисляются на сервере).
"""

import pytest

from app.database.db import get_connection
from app.services import stronghold_admin_content as content
from app.services.admin_permissions import (
    ADMIN_ROLE_ECONOMY,
    ADMIN_ROLE_MODERATOR,
    ADMIN_ROLE_OWNER,
    PERMISSION_STRONGHOLD,
    ROLE_PERMISSIONS,
)
from app.services.stronghold_common import StrongholdError
from app.services.stronghold_missions import claim_mission, list_missions
from app.services.stronghold_upgrade import confirm_upgrade
from app.services.stronghold_wallet import credit
from app.services.stronghold_wallet import debit as wallet_debit
from tests.conftest import build_full_stronghold_lineup, create_test_user, get_balance, grant_balance


# ---------------------------------------------------------------------------
# IDOR / broken access control
# ---------------------------------------------------------------------------

async def test_cannot_upgrade_another_users_card(active_event):
    owner_id = await create_test_user("card-owner")
    attacker_id = await create_test_user("card-attacker")
    owner_card_id = await build_full_stronghold_lineup(owner_id)
    grant_balance(owner_id, "fortress_token", 100)
    grant_balance(owner_id, "coins", 1_000_000)

    with pytest.raises(StrongholdError) as exc_info:
        await confirm_upgrade(attacker_id, owner_card_id, request_id="idor-attempt")
    assert exc_info.value.code == "CARD_NOT_OWNED"

    # баланс и карта владельца не пострадали
    assert get_balance(owner_id, "fortress_token") == 100
    with get_connection() as connection:
        row = connection.execute("SELECT card_id FROM user_cards WHERE id = ?", (owner_card_id,)).fetchone()
        card_overall = connection.execute("SELECT overall FROM cards WHERE id = ?", (row["card_id"],)).fetchone()
    assert card_overall["overall"] == 92


async def test_cannot_claim_another_users_mission_progress(active_event):
    from app.services.stronghold_missions import apply_stronghold_progress

    victim_id = await create_test_user("mission-victim")
    attacker_id = await create_test_user("mission-attacker")

    await apply_stronghold_progress(victim_id, "win_matches", 1)
    victim_missions = await list_missions(victim_id, "DAILY")
    win_mission = next(m for m in victim_missions if m.condition_type == "win_matches")

    # у атакующего прогресса по этому же mission_id нет вообще
    with pytest.raises(StrongholdError) as exc_info:
        await claim_mission(attacker_id, win_mission.id)
    assert exc_info.value.code == "MISSION_NOT_COMPLETED"
    assert get_balance(attacker_id, "fortress_token") == 0


# ---------------------------------------------------------------------------
# Подмена цены/награды — сервер никогда не берёт эти числа у клиента
# ---------------------------------------------------------------------------

async def test_upgrade_cost_always_comes_from_server_config_not_caller(active_event):
    """У confirm_upgrade просто нет параметра для передачи цены/награды с клиента —
    единственный источник — `stronghold_upgrade_steps`. Проверяем, что фактическое
    списание всегда равно серверной конфигурации шага, независимо от того, что было
    в преview непосредственно перед этим (preview не может быть "подделан" клиентом,
    т.к. целиком вычисляется на сервере при каждом вызове)."""
    user_id = await create_test_user("no-price-tamper-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    grant_balance(user_id, "fortress_token", 20)
    grant_balance(user_id, "coins", 150_000)

    with get_connection() as connection:
        step = connection.execute("SELECT ft_cost, coins_cost FROM stronghold_upgrade_steps WHERE step_order = 1").fetchone()
    assert (step["ft_cost"], step["coins_cost"]) == (20, 150_000)

    result = await confirm_upgrade(user_id, user_card_id, request_id="server-price-1")
    assert result.ft_spent == 20
    assert result.coins_spent == 150_000
    assert get_balance(user_id, "fortress_token") == 0
    assert get_balance(user_id, "coins") == 0


# ---------------------------------------------------------------------------
# Ролевой доступ (admin permission model)
# ---------------------------------------------------------------------------

def test_only_stronghold_roles_have_permission():
    assert PERMISSION_STRONGHOLD in ROLE_PERMISSIONS[ADMIN_ROLE_OWNER]
    assert PERMISSION_STRONGHOLD in ROLE_PERMISSIONS[ADMIN_ROLE_ECONOMY]
    assert PERMISSION_STRONGHOLD not in ROLE_PERMISSIONS[ADMIN_ROLE_MODERATOR]


# ---------------------------------------------------------------------------
# Целостность / анти-чит: ledger vs balance
# ---------------------------------------------------------------------------

async def test_ledger_reconciles_with_wallet_after_normal_operations(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    user_id = await create_test_user("reconcile-user")
    user_card_id = await build_full_stronghold_lineup(user_id)

    # баланс выдаём через credit() (реальный путь начисления FT игроку в проде),
    # а не через тестовый grant_balance() (прямой INSERT в обход ledger) — иначе
    # сверка закономерно найдёт "расхождение", которое на самом деле лишь артефакт
    # тестового хелпера, а не реальной проблемы.
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        credit(connection, user_id=user_id, event_id=event_row["id"], currency_code="fortress_token", amount=20, reason="test_setup")
        connection.commit()
    grant_balance(user_id, "coins", 150_000)

    await confirm_upgrade(user_id, user_card_id, request_id="reconcile-1")

    mismatches = await content.reconcile_ledger_vs_balance(event_row["id"])
    assert mismatches == []


async def test_reconcile_detects_direct_db_tampering(active_event):
    """Если баланс изменили в обход сервисного слоя (например прямым UPDATE) —
    сверка должна это заметить (полезно для healthcheck/анти-чит мониторинга)."""
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    user_id = await create_test_user("tampered-user")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        credit(connection, user_id=user_id, event_id=event_row["id"], currency_code="fortress_token", amount=10, reason="test")
        connection.commit()

    # прямая манипуляция в обход wallet.credit/debit — ledger теперь не совпадает с балансом
    with get_connection() as connection:
        connection.execute("UPDATE currency_balances SET amount = amount + 500 WHERE user_id = ? AND currency_code = 'fortress_token'", (user_id,))
        connection.commit()

    mismatches = await content.reconcile_ledger_vs_balance(event_row["id"])
    assert len(mismatches) == 1
    assert mismatches[0].user_id == user_id
    assert mismatches[0].wallet_balance == 510
    assert mismatches[0].ledger_sum == 10


# ---------------------------------------------------------------------------
# Отрицательные/некорректные значения не создают дыр
# ---------------------------------------------------------------------------

async def test_negative_credit_amount_is_ignored(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    user_id = await create_test_user("negative-credit-user")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        credit(connection, user_id=user_id, event_id=event_row["id"], currency_code="coins", amount=-1000, reason="malicious")
        connection.commit()

    assert get_balance(user_id, "coins") == 0


async def test_debit_more_than_balance_raises_and_does_not_go_negative(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    user_id = await create_test_user("overdraft-user")
    grant_balance(user_id, "coins", 100)

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(StrongholdError):
            wallet_debit(connection, user_id=user_id, event_id=event_row["id"], currency_code="coins", amount=1000, reason="overdraft-attempt")
        connection.rollback()

    assert get_balance(user_id, "coins") == 100


# ---------------------------------------------------------------------------
# SQL injection safety (параметризованные запросы)
# ---------------------------------------------------------------------------

async def test_malicious_strings_in_admin_inputs_are_stored_literally(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    malicious_title = "'; DROP TABLE stronghold_missions; --"
    mission_id = await content.create_mission(
        event_row["id"], type="DAILY", title=malicious_title, condition_type="play_matches",
        target_value=1, reward_ft=0, reward_coins=0, reward_xp=0, admin_id=1,
    )

    missions = await content.list_missions_admin(event_row["id"])
    created = next(m for m in missions if m.id == mission_id)
    assert created.title == malicious_title  # сохранено буквально, не выполнено как SQL

    with get_connection() as connection:
        still_exists = connection.execute("SELECT COUNT(*) AS c FROM stronghold_missions").fetchone()["c"]
    assert still_exists >= 1  # таблица не была дропнута


# ---------------------------------------------------------------------------
# Пагинация: некорректная страница не роняет и не выходит за диапазон
# ---------------------------------------------------------------------------

async def test_currency_history_pagination_clamped(active_event):
    from app.services.stronghold_wallet import get_currency_history

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    user_id = await create_test_user("pagination-user")
    grant_balance(user_id, "coins", 100)

    page = await get_currency_history(user_id, event_row["id"], page=999_999)
    assert page.page == page.pages_count
    assert page.page >= 1

    page_zero = await get_currency_history(user_id, event_row["id"], page=0)
    assert page_zero.page == 1

    page_negative = await get_currency_history(user_id, event_row["id"], page=-50)
    assert page_negative.page == 1
