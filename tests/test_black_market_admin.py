import uuid

import pytest

from app.database.db import get_connection
from app.services import black_market_admin
from app.services.black_market_common import BlackMarketError
from app.services.black_market_generation import get_or_create_rotation
from app.services.black_market_store import purchase
from tests.conftest import business_date_today, create_test_user, grant_balance


def _item_by_type(rotation, item_type: str):
    return next(item for item in rotation.items if item.item_type == item_type)


async def test_view_user_storefront_returns_none_without_prior_generation(black_market_pool):
    user_id = await create_test_user("bm-admin-view-none")
    rotation = await black_market_admin.view_user_storefront(user_id)
    assert rotation is None


async def test_find_user_by_telegram_id_and_nickname(black_market_pool):
    user_id = await create_test_user("bm-findme")
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id, nickname FROM users WHERE id = ?", (user_id,)).fetchone()

    found_by_id = await black_market_admin.find_user(str(row["telegram_id"]))
    assert found_by_id is not None
    assert int(found_by_id["id"]) == user_id

    found_by_nickname = await black_market_admin.find_user(row["nickname"])
    assert found_by_nickname is not None
    assert int(found_by_nickname["id"]) == user_id


async def test_refresh_one_user_only_affects_that_user(black_market_pool):
    user1 = await create_test_user("bm-refresh-target")
    user2 = await create_test_user("bm-refresh-bystander")

    rotation1_before = await get_or_create_rotation(user1, business_date_value=business_date_today())
    rotation2_before = await get_or_create_rotation(user2, business_date_value=business_date_today())

    await black_market_admin.refresh_one_user(admin_id=1, target_user_id=user1)

    with get_connection() as connection:
        user1_status = connection.execute(
            "SELECT status FROM black_market_user_rotations WHERE id = ?", (rotation1_before.id,)
        ).fetchone()["status"]
        user2_status = connection.execute(
            "SELECT status FROM black_market_user_rotations WHERE id = ?", (rotation2_before.id,)
        ).fetchone()["status"]

    assert user1_status == "EXPIRED"
    assert user2_status == "ACTIVE"

    rotation1_after = await get_or_create_rotation(user1, business_date_value=business_date_today())
    assert rotation1_after.id != rotation1_before.id


async def test_refresh_everyone_bumps_version_without_mass_generation(black_market_pool):
    user1 = await create_test_user("bm-global-refresh-1")
    user2 = await create_test_user("bm-global-refresh-2")

    await get_or_create_rotation(user1, business_date_value=business_date_today())

    with get_connection() as connection:
        before_count = connection.execute("SELECT COUNT(*) AS c FROM black_market_user_rotations").fetchone()["c"]

    new_version = await black_market_admin.refresh_everyone(admin_id=1)
    assert new_version == 2

    with get_connection() as connection:
        after_count = connection.execute("SELECT COUNT(*) AS c FROM black_market_user_rotations").fetchone()["c"]
    # Бамп версии не создаёт строк заранее — количество ротаций не изменилось.
    assert after_count == before_count

    rotation2 = await get_or_create_rotation(user2, business_date_value=business_date_today())
    assert rotation2.rotation_version == 2


async def test_old_rotation_rejected_for_purchase_after_global_refresh(black_market_pool):
    user_id = await create_test_user("bm-stale-buyer")
    grant_balance(user_id, "coins", 1000)

    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")

    await black_market_admin.refresh_everyone(admin_id=1)

    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "ROTATION_EXPIRED"


async def test_edit_slot_remove_is_audited(black_market_pool):
    user_id = await create_test_user("bm-edit-slot-user")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")

    await black_market_admin.edit_slot(admin_id=1, rotation_item_id=item.id, remove=True)

    with get_connection() as connection:
        status = connection.execute(
            "SELECT item_status FROM black_market_user_rotation_items WHERE id = ?", (item.id,)
        ).fetchone()["item_status"]
    assert status == "REMOVED"

    audit_entries = await black_market_admin.list_recent_audit(5)
    assert any(entry["action"] == "edit_slot" and int(entry["target_user_id"]) == user_id for entry in audit_entries)


async def test_pool_item_create_update_and_toggle_are_audited(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.commit()

    created = await black_market_admin.create_pool_item(
        admin_id=1,
        item_type="currency",
        rarity="Common",
        price_currency_code="coins",
        title="Admin Test Item",
        currency_code="coins",
        amount=5,
        price_amount=10,
    )
    assert created.title == "Admin Test Item"

    updated = await black_market_admin.update_pool_item(1, created.id, price_amount=25)
    assert updated.price_amount == 25

    toggled = await black_market_admin.set_pool_item_active(1, created.id, False)
    assert toggled.active is False

    audit_entries = await black_market_admin.list_recent_audit(10)
    actions = {entry["action"] for entry in audit_entries}
    assert {"pool_item_create", "pool_item_update", "pool_item_toggle_active"} <= actions


async def test_update_rarity_weights_rejects_unknown_rarity(stronghold_db):
    with pytest.raises(BlackMarketError) as exc_info:
        await black_market_admin.update_rarity_weights(1, {"NotARarity": 10})
    assert exc_info.value.code == "INVALID_RARITY"


async def test_update_rarity_weights_persists(stronghold_db):
    # Полный набор, сумма активных = 100 (15+25+15+42+2+1) — частичное обновление,
    # ломающее сумму 100%, теперь отклоняется _validate_rarity_weights (см. отдельный
    # test_update_rarity_weights_rejects_broken_sum ниже).
    await black_market_admin.update_rarity_weights(1, {"Common": 15, "Legendary": 42})
    weights = await black_market_admin.get_rarity_weights()
    assert weights["Legendary"] == 42
    assert weights["Common"] == 15
    assert sum(w for w in weights.values() if w > 0) == 100


async def test_update_rarity_weights_rejects_broken_sum(stronghold_db):
    with pytest.raises(BlackMarketError) as exc_info:
        await black_market_admin.update_rarity_weights(1, {"Legendary": 42})
    assert exc_info.value.code == "RARITY_WEIGHTS_INVALID"


async def test_update_rarity_weights_rejects_out_of_range(stronghold_db):
    with pytest.raises(BlackMarketError) as exc_info:
        await black_market_admin.update_rarity_weights(1, {"Common": 150})
    assert exc_info.value.code == "RARITY_WEIGHTS_INVALID"


async def test_update_rarity_weights_rejects_all_zero(stronghold_db):
    with pytest.raises(BlackMarketError) as exc_info:
        await black_market_admin.update_rarity_weights(
            1, {"Common": 0, "Rare": 0, "Epic": 0, "Legendary": 0, "Event": 0, "Icon": 0}
        )
    assert exc_info.value.code == "RARITY_WEIGHTS_INVALID"
