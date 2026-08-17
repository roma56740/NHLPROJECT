import asyncio

import pytest

from app.database.db import get_connection
from app.services.stronghold_common import StrongholdError
from app.services.stronghold_upgrade import confirm_upgrade, preview_upgrade
from tests.conftest import build_full_stronghold_lineup, create_test_user, get_balance, grant_balance

UPGRADE_STEPS = [
    (92, 93, 20, 150_000),
    (93, 94, 30, 250_000),
    (94, 95, 40, 400_000),
    (95, 96, 50, 550_000),
    (96, 97, 65, 700_000),
    (97, 98, 75, 900_000),
    (98, 99, 95, 1_100_000),
]


async def _grant_enough_for_full_chain(user_id: int) -> None:
    grant_balance(user_id, "fortress_token", sum(step[2] for step in UPGRADE_STEPS))
    grant_balance(user_id, "coins", sum(step[3] for step in UPGRADE_STEPS))


def _current_overall(user_card_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT cards.overall FROM user_cards JOIN cards ON cards.id = user_cards.card_id WHERE user_cards.id = ?",
            (user_card_id,),
        ).fetchone()
    return int(row["overall"])


async def test_full_upgrade_chain_92_to_99(active_event):
    user_id = await create_test_user("chain-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    await _grant_enough_for_full_chain(user_id)

    assert _current_overall(user_card_id) == 92

    for index in range(7):
        result = await confirm_upgrade(user_id, user_card_id, request_id=f"chain-step-{index}")
        assert result.success

    assert _current_overall(user_card_id) == 99
    assert get_balance(user_id, "fortress_token") == 0
    assert get_balance(user_id, "coins") == 0


async def test_upgrade_preview_does_not_charge(active_event):
    user_id = await create_test_user("preview-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    await _grant_enough_for_full_chain(user_id)

    preview = await preview_upgrade(user_id, user_card_id)
    assert preview.blocking_reason is None
    assert preview.ft_cost == 20
    assert preview.coins_cost == 150_000
    assert _current_overall(user_card_id) == 92
    assert get_balance(user_id, "fortress_token") == sum(step[2] for step in UPGRADE_STEPS)


async def test_insufficient_coins_blocks_upgrade(active_event):
    user_id = await create_test_user("poor-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    grant_balance(user_id, "fortress_token", 100)
    # без Coins

    with pytest.raises(StrongholdError) as exc_info:
        await confirm_upgrade(user_id, user_card_id, request_id="poor-1")
    assert exc_info.value.code == "INSUFFICIENT_COINS"
    assert _current_overall(user_card_id) == 92


async def test_insufficient_ft_blocks_upgrade(active_event):
    user_id = await create_test_user("poor-ft-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    grant_balance(user_id, "coins", 10_000_000)
    # без FT

    with pytest.raises(StrongholdError) as exc_info:
        await confirm_upgrade(user_id, user_card_id, request_id="poor-ft-1")
    assert exc_info.value.code == "INSUFFICIENT_FORTRESS_TOKENS"


async def test_duplicate_request_id_does_not_double_charge(active_event):
    user_id = await create_test_user("dup-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    await _grant_enough_for_full_chain(user_id)

    result1 = await confirm_upgrade(user_id, user_card_id, request_id="same-request")
    balance_ft_after_first = get_balance(user_id, "fortress_token")
    balance_coins_after_first = get_balance(user_id, "coins")

    result2 = await confirm_upgrade(user_id, user_card_id, request_id="same-request")

    assert result2.replayed is True
    assert result1.to_card_id == result2.to_card_id
    assert get_balance(user_id, "fortress_token") == balance_ft_after_first
    assert get_balance(user_id, "coins") == balance_coins_after_first
    assert _current_overall(user_card_id) == 93  # только один шаг применился


async def test_concurrent_confirm_only_one_succeeds(active_event):
    user_id = await create_test_user("concurrent-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    grant_balance(user_id, "fortress_token", 20)
    grant_balance(user_id, "coins", 150_000)

    results = await asyncio.gather(
        confirm_upgrade(user_id, user_card_id, request_id="race-a"),
        confirm_upgrade(user_id, user_card_id, request_id="race-b"),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], StrongholdError)
    assert get_balance(user_id, "fortress_token") == 0
    assert get_balance(user_id, "coins") == 0
    assert _current_overall(user_card_id) == 93


async def test_max_level_card_cannot_be_upgraded_further(active_event):
    user_id = await create_test_user("maxed-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    await _grant_enough_for_full_chain(user_id)

    for index in range(7):
        await confirm_upgrade(user_id, user_card_id, request_id=f"max-step-{index}")

    with pytest.raises(StrongholdError) as exc_info:
        await preview_upgrade(user_id, user_card_id)
    assert exc_info.value.code == "CARD_ALREADY_MAX_LEVEL"


async def test_upgrade_blocked_after_grace_period_ends(active_event):
    from app.services.stronghold_common import STRONGHOLD_SLUG

    user_id = await create_test_user("archived-user")
    user_card_id = await build_full_stronghold_lineup(user_id)
    await _grant_enough_for_full_chain(user_id)

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events WHERE slug = ?", (STRONGHOLD_SLUG,)).fetchone()
        connection.execute(
            """
            UPDATE stronghold_events
            SET status = 'ACTIVE', starts_at = datetime('now', '-40 days'),
                ends_at = datetime('now', '-10 days'), grace_ends_at = datetime('now', '-3 days')
            WHERE id = ?
            """,
            (event_row["id"],),
        )
        connection.commit()

    with pytest.raises(StrongholdError) as exc_info:
        await confirm_upgrade(user_id, user_card_id, request_id="archived-1")
    assert exc_info.value.code == "UPGRADE_GRACE_PERIOD_ENDED"
