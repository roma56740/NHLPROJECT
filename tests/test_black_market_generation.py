import threading

from app.database.db import get_connection
from app.services.black_market_generation import (
    compute_seed_digest,
    get_or_create_rotation,
    seeded_rng,
)
from tests.conftest import business_date_offset, business_date_today, create_test_user

TODAY = business_date_today()
TOMORROW = business_date_offset(1)


def test_seed_digest_is_deterministic_for_same_inputs():
    digest1 = compute_seed_digest(1, TODAY, 1, "secret")
    digest2 = compute_seed_digest(1, TODAY, 1, "secret")
    assert digest1 == digest2


def test_seed_digest_differs_per_user():
    digest_user1 = compute_seed_digest(1, TODAY, 1, "secret")
    digest_user2 = compute_seed_digest(2, TODAY, 1, "secret")
    assert digest_user1 != digest_user2


def test_seed_digest_differs_per_business_date():
    digest_day1 = compute_seed_digest(1, TODAY, 1, "secret")
    digest_day2 = compute_seed_digest(1, TOMORROW, 1, "secret")
    assert digest_day1 != digest_day2


def test_seeded_rng_reproduces_same_sequence():
    rng1, hash1 = seeded_rng(1, TODAY, 1, "secret")
    rng2, hash2 = seeded_rng(1, TODAY, 1, "secret")
    assert hash1 == hash2
    assert [rng1.random() for _ in range(10)] == [rng2.random() for _ in range(10)]


async def test_lazy_generation_creates_rotation_on_first_open(black_market_pool):
    user_id = await create_test_user("bm-user-1")
    rotation = await get_or_create_rotation(user_id, business_date_value=TODAY)
    assert rotation.user_id == user_id
    assert rotation.business_date == TODAY
    assert len(rotation.items) == 4

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM black_market_user_rotations WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
    assert count == 1


async def test_reopening_same_day_returns_cached_rotation_not_regenerated(black_market_pool):
    user_id = await create_test_user("bm-user-2")
    first = await get_or_create_rotation(user_id, business_date_value=TODAY)
    second = await get_or_create_rotation(user_id, business_date_value=TODAY)
    assert first.id == second.id
    assert first.seed_hash == second.seed_hash

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM black_market_user_rotations WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
    assert count == 1


async def test_same_user_different_business_date_gets_new_rotation(black_market_pool):
    user_id = await create_test_user("bm-user-3")
    day1 = await get_or_create_rotation(user_id, business_date_value=TODAY)
    day2 = await get_or_create_rotation(user_id, business_date_value=TOMORROW)
    assert day1.id != day2.id
    assert day1.seed_hash != day2.seed_hash


async def test_different_users_get_different_seed_hashes(black_market_pool):
    user1 = await create_test_user("bm-user-4")
    user2 = await create_test_user("bm-user-5")
    rotation1 = await get_or_create_rotation(user1, business_date_value=TODAY)
    rotation2 = await get_or_create_rotation(user2, business_date_value=TODAY)
    assert rotation1.seed_hash != rotation2.seed_hash


async def test_slot_generation_skips_inactive_pool_items(black_market_pool):
    with get_connection() as connection:
        connection.execute(
            "UPDATE black_market_pool_items SET active = 0 WHERE item_type = 'card'"
        )
        connection.commit()

    user_id = await create_test_user("bm-user-6")
    rotation = await get_or_create_rotation(user_id, business_date_value=TODAY)
    assert all(item.item_type != "card" for item in rotation.items)


async def test_slot_generation_dedupes_within_rotation(stronghold_db):
    """2 предмета пула на 6 слотов без allow_duplicate_slots — итог не должен содержать дублей."""
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount, max_stock_per_rotation, selection_weight)
            VALUES ('currency', 'coins', 10, 'Common', 'Coin Pile A', 'coins', 5, 5, 1)
            """
        )
        connection.execute(
            """
            INSERT INTO black_market_pool_items (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount, max_stock_per_rotation, selection_weight)
            VALUES ('currency', 'coins', 20, 'Common', 'Coin Pile B', 'coins', 5, 5, 1)
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 6 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-user-7")
    rotation = await get_or_create_rotation(user_id, business_date_value=TODAY)

    pool_item_ids = [item.pool_item_id for item in rotation.items]
    assert len(pool_item_ids) == len(set(pool_item_ids))
    assert len(rotation.items) <= 2


async def test_concurrent_first_open_generates_rotation_exactly_once(black_market_pool):
    import asyncio

    user_id = await create_test_user("bm-race-user")

    errors: list[Exception] = []

    def _worker() -> None:
        try:
            asyncio.run(get_or_create_rotation(user_id, business_date_value=TODAY))
        except Exception as error:  # noqa: BLE001 - captured for assertion below
            errors.append(error)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"unexpected errors during concurrent generation: {errors}"

    with get_connection() as connection:
        active_count = connection.execute(
            "SELECT COUNT(*) AS c FROM black_market_user_rotations WHERE user_id = ? AND status = 'ACTIVE'",
            (user_id,),
        ).fetchone()["c"]
    assert active_count == 1
