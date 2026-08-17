import pytest

from app.database.db import get_connection
from app.services.stronghold_common import STRONGHOLD_SLUG, StrongholdError
from app.services.stronghold_store import list_products, purchase
from tests.conftest import create_test_user, get_balance, grant_balance


async def test_purchase_debits_and_grants_contents(active_event):
    user_id = await create_test_user("store-user")
    grant_balance(user_id, "fortress_token", 100)

    products = await list_products(user_id, "Featured")
    product = products[0]
    assert product.available

    result = await purchase(user_id, product.id, request_id="buy-1")
    assert result.success
    assert get_balance(user_id, "fortress_token") == 100 - product.price_amount
    assert get_balance(user_id, "coins") == 60_000  # featured_coin_cache contents


async def test_insufficient_currency_blocks_purchase(active_event):
    user_id = await create_test_user("poor-store-user")
    products = await list_products(user_id, "Featured")
    product = products[0]

    with pytest.raises(StrongholdError) as exc_info:
        await purchase(user_id, product.id, request_id="buy-poor")
    assert exc_info.value.code == "INSUFFICIENT_CURRENCY"


async def test_purchase_limit_is_enforced(active_event):
    user_id = await create_test_user("limit-user")
    grant_balance(user_id, "fortress_token", 1000)

    products = await list_products(user_id, "Cards")
    product = next(p for p in products if p.purchase_limit == 1)

    result1 = await purchase(user_id, product.id, request_id="limit-1")
    assert result1.success

    with pytest.raises(StrongholdError) as exc_info:
        await purchase(user_id, product.id, request_id="limit-2")
    assert exc_info.value.code == "PURCHASE_LIMIT_REACHED"


async def test_duplicate_request_id_does_not_double_charge(active_event):
    user_id = await create_test_user("dup-store-user")
    grant_balance(user_id, "fortress_token", 100)

    products = await list_products(user_id, "Featured")
    product = products[0]

    result1 = await purchase(user_id, product.id, request_id="same-purchase")
    balance_after_first = get_balance(user_id, "fortress_token")

    result2 = await purchase(user_id, product.id, request_id="same-purchase")
    assert result2.replayed is True
    assert get_balance(user_id, "fortress_token") == balance_after_first


async def test_purchase_blocked_after_archive(active_event):
    user_id = await create_test_user("archived-store-user")
    grant_balance(user_id, "fortress_token", 100)
    products = await list_products(user_id, "Featured")
    product = products[0]

    with get_connection() as connection:
        connection.execute(
            "UPDATE stronghold_events SET status = 'ARCHIVED' WHERE slug = ?", (STRONGHOLD_SLUG,)
        )
        connection.commit()

    with pytest.raises(StrongholdError) as exc_info:
        await purchase(user_id, product.id, request_id="archived-buy")
    assert exc_info.value.code == "EVENT_ARCHIVED"
