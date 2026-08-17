from app.database.db import get_connection
from app.services.stronghold_common import STRONGHOLD_SLUG
from app.services.stronghold_conversion import convert_archived_event_balances
from tests.conftest import create_test_user, get_balance, grant_balance


async def _archive_event() -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM stronghold_events WHERE slug = ?", (STRONGHOLD_SLUG,)).fetchone()
        event_id = int(row["id"])
        connection.execute("UPDATE stronghold_events SET status = 'ARCHIVED' WHERE id = ?", (event_id,))
        connection.commit()
    return event_id


async def test_conversion_grants_coins_and_zeroes_ft(active_event):
    user_id = await create_test_user("conversion-user")
    grant_balance(user_id, "fortress_token", 12)
    event_id = await _archive_event()

    processed = await convert_archived_event_balances(event_id, ft_conversion_rate=5000)
    assert processed == 1
    assert get_balance(user_id, "fortress_token") == 0
    assert get_balance(user_id, "coins") == 60_000


async def test_conversion_is_idempotent(active_event):
    user_id = await create_test_user("conversion-repeat-user")
    grant_balance(user_id, "fortress_token", 10)
    event_id = await _archive_event()

    await convert_archived_event_balances(event_id, ft_conversion_rate=5000)
    coins_after_first = get_balance(user_id, "coins")

    processed_again = await convert_archived_event_balances(event_id, ft_conversion_rate=5000)
    assert processed_again == 0
    assert get_balance(user_id, "coins") == coins_after_first
    assert get_balance(user_id, "fortress_token") == 0


async def test_users_without_ft_are_not_converted(active_event):
    user_id = await create_test_user("no-ft-user")
    event_id = await _archive_event()

    processed = await convert_archived_event_balances(event_id, ft_conversion_rate=5000)
    assert processed == 0
    assert get_balance(user_id, "coins") == 0
