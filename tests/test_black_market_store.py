import uuid

import pytest

from app.database.db import get_connection
from app.services.black_market_common import BlackMarketError
from app.services.black_market_generation import get_or_create_rotation
from app.services.black_market_store import invalidate_user_cache, list_storefront, purchase
from tests.conftest import business_date_today, create_test_user, get_balance, grant_balance


def _item_by_type(rotation, item_type: str):
    return next(item for item in rotation.items if item.item_type == item_type)


@pytest.mark.parametrize("item_type", ["currency", "pack", "card", "cosmetic"])
async def test_purchase_debits_and_grants_item(black_market_pool, item_type):
    user_id = await create_test_user(f"bm-buyer-{item_type}")
    grant_balance(user_id, "coins", 1000)

    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, item_type)

    result = await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert result.success

    with get_connection() as connection:
        if item_type == "currency":
            # Награда — тоже 'coins' (100 шт., см. black_market_pool в conftest.py), поэтому
            # баланс net-эффект = -цена +100, а не просто -цена.
            granted_amount = connection.execute(
                "SELECT amount FROM black_market_pool_items WHERE id = ?", (item.pool_item_id,)
            ).fetchone()["amount"]
            assert get_balance(user_id, "coins") == 1000 - item.price_amount + int(granted_amount)
        else:
            assert get_balance(user_id, "coins") == 1000 - item.price_amount

        if item_type == "pack":
            row = connection.execute(
                "SELECT quantity FROM user_packs WHERE user_id = ? AND pack_id = ?",
                (user_id, item.item_reference_id),
            ).fetchone()
            assert row is not None and int(row["quantity"]) >= 1
        elif item_type == "card":
            row = connection.execute(
                "SELECT 1 FROM user_cards WHERE user_id = ? AND card_id = ?",
                (user_id, item.item_reference_id),
            ).fetchone()
            assert row is not None
        elif item_type == "cosmetic":
            row = connection.execute(
                "SELECT 1 FROM user_cosmetic_items WHERE owner_id = ? AND cosmetic_item_id = ?",
                (user_id, item.item_reference_id),
            ).fetchone()
            assert row is not None


async def test_purchase_insufficient_currency_blocks(black_market_pool):
    user_id = await create_test_user("bm-poor-buyer")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")

    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "INSUFFICIENT_CURRENCY"

    with get_connection() as connection:
        stock_row = connection.execute(
            "SELECT remaining_personal_stock FROM black_market_user_rotation_items WHERE id = ?", (item.id,)
        ).fetchone()
    assert int(stock_row["remaining_personal_stock"]) == item.remaining_personal_stock


async def test_purchase_decrements_personal_stock_and_blocks_at_zero(black_market_pool):
    user_id = await create_test_user("bm-stock-buyer")
    grant_balance(user_id, "coins", 10_000)

    with get_connection() as connection:
        connection.execute(
            "UPDATE black_market_pool_items SET max_stock_per_rotation = 1 WHERE item_type = 'currency'"
        )
        connection.commit()

    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")
    assert item.remaining_personal_stock == 1

    result = await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert result.new_remaining_stock == 0

    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "OUT_OF_STOCK"


async def test_duplicate_request_id_does_not_double_charge(black_market_pool):
    user_id = await create_test_user("bm-dup-buyer")
    grant_balance(user_id, "coins", 1000)

    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")
    request_id = str(uuid.uuid4())

    result1 = await purchase(user_id, item.id, request_id=request_id)
    balance_after_first = get_balance(user_id, "coins")
    assert result1.replayed is False

    result2 = await purchase(user_id, item.id, request_id=request_id)
    assert result2.replayed is True
    assert get_balance(user_id, "coins") == balance_after_first


async def test_cannot_buy_another_users_item(black_market_pool):
    user1 = await create_test_user("bm-owner")
    user2 = await create_test_user("bm-intruder")
    grant_balance(user2, "coins", 1000)

    rotation = await get_or_create_rotation(user1, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")

    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user2, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "ITEM_NOT_OWNED"


async def test_rollback_restores_stock_and_balance_on_grant_failure(black_market_pool):
    user_id = await create_test_user("bm-broken-grant")
    grant_balance(user_id, "coins", 1000)

    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "card")

    with get_connection() as connection:
        connection.execute("DELETE FROM cards WHERE id = ?", (item.item_reference_id,))
        connection.commit()

    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "INVALID_ITEM_CONFIGURATION"

    assert get_balance(user_id, "coins") == 1000
    with get_connection() as connection:
        stock_row = connection.execute(
            "SELECT remaining_personal_stock FROM black_market_user_rotation_items WHERE id = ?", (item.id,)
        ).fetchone()
    assert int(stock_row["remaining_personal_stock"]) == item.remaining_personal_stock


async def test_storefront_cache_does_not_mix_users(black_market_pool):
    user1 = await create_test_user("bm-cache-1")
    user2 = await create_test_user("bm-cache-2")

    rotation1 = await list_storefront(user1)
    rotation2 = await list_storefront(user2)

    assert rotation1.user_id == user1
    assert rotation2.user_id == user2
    assert rotation1.id != rotation2.id


async def test_purchase_invalidates_cache(black_market_pool):
    user_id = await create_test_user("bm-cache-invalidate")
    grant_balance(user_id, "coins", 1000)

    rotation = await list_storefront(user_id)
    item = _item_by_type(rotation, "currency")

    await purchase(user_id, item.id, request_id=str(uuid.uuid4()))

    refreshed = await list_storefront(user_id)
    refreshed_item = _item_by_type(refreshed, "currency")
    assert refreshed_item.remaining_personal_stock == item.remaining_personal_stock - 1

    invalidate_user_cache(user_id)


async def test_purchase_runs_transaction_off_event_loop_and_commits(black_market_pool):
    """Regression: the public async purchase wrapper must still commit/grant while
    running the blocking SQLite transaction via asyncio.to_thread."""
    user_id = await create_test_user("bm-threaded-purchase")
    grant_balance(user_id, "coins", 1000)
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "card")

    before = get_balance(user_id, "coins")
    result = await purchase(user_id, item.id, request_id=str(uuid.uuid4()))

    assert result.success is True
    assert get_balance(user_id, "coins") == before - item.price_amount
    with get_connection() as connection:
        owned = connection.execute(
            "SELECT 1 FROM user_cards WHERE user_id = ? AND card_id = ?",
            (user_id, item.item_reference_id),
        ).fetchone()
        log_row = connection.execute(
            "SELECT status FROM black_market_purchases WHERE user_id = ? AND rotation_item_id = ? ORDER BY id DESC LIMIT 1",
            (user_id, item.id),
        ).fetchone()
    assert owned is not None
    assert log_row is not None and log_row["status"] == "success"
