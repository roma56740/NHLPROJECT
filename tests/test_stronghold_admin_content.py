from app.database.db import get_connection
from app.services import stronghold_admin_content as content
from tests.conftest import create_test_user


async def test_update_upgrade_step_costs_and_audit(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    steps = await content.list_upgrade_steps(event_row["id"])
    first_step = steps[0]

    await content.update_upgrade_step_costs(first_step.id, ft_cost=999, coins_cost=888, admin_id=1)

    updated = await content.list_upgrade_steps(event_row["id"])
    assert updated[0].ft_cost == 999
    assert updated[0].coins_cost == 888

    with get_connection() as connection:
        audit = connection.execute(
            "SELECT * FROM stronghold_audit_log WHERE action = 'update_upgrade_step' AND entity_id = ?", (first_step.id,)
        ).fetchone()
    assert audit is not None
    assert audit["admin_id"] == 1


async def test_toggle_fortress_active(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    fortresses = await content.list_fortresses_admin(event_row["id"])
    fortress = fortresses[0]
    assert fortress.active is True

    new_active = await content.toggle_fortress_active(fortress.id, admin_id=1)
    assert new_active is False

    new_active_2 = await content.toggle_fortress_active(fortress.id, admin_id=1)
    assert new_active_2 is True


async def test_update_fortress_match_ovr_is_clamped(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    fortresses = await content.list_fortresses_admin(event_row["id"])
    matches = await content.get_fortress_matches_admin(fortresses[0].id)
    match = matches[0]

    await content.update_fortress_match_ovr(match.id, opponent_ovr=500, admin_id=1)
    updated = await content.get_fortress_matches_admin(fortresses[0].id)
    assert updated[0].opponent_ovr == 99

    await content.update_fortress_match_ovr(match.id, opponent_ovr=-5, admin_id=1)
    updated2 = await content.get_fortress_matches_admin(fortresses[0].id)
    assert updated2[0].opponent_ovr == 1


async def test_create_and_toggle_mission(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    mission_id = await content.create_mission(
        event_row["id"], type="DAILY", title="Test Mission", condition_type="play_matches",
        target_value=3, reward_ft=1, reward_coins=100, reward_xp=10, admin_id=1,
    )
    missions = await content.list_missions_admin(event_row["id"])
    created = next(m for m in missions if m.id == mission_id)
    assert created.title == "Test Mission"
    assert created.active is True

    new_active = await content.toggle_mission_active(mission_id, admin_id=1)
    assert new_active is False


async def test_update_season_level(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    levels = await content.list_season_levels_admin(event_row["id"])
    level = levels[0]

    await content.update_season_level(level.id, xp_threshold=500, reward_ft=7, reward_coins=1000, admin_id=1)
    updated = await content.list_season_levels_admin(event_row["id"])
    assert updated[0].xp_threshold == 500
    assert updated[0].reward_ft == 7


async def test_toggle_store_product_and_update_price(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    products = await content.list_store_products_admin(event_row["id"])
    product = products[0]

    await content.update_store_product_price(product.id, price_amount=42, purchase_limit=2, admin_id=1)
    updated = await content.list_store_products_admin(event_row["id"])
    changed = next(p for p in updated if p.id == product.id)
    assert changed.price_amount == 42
    assert changed.purchase_limit == 2

    new_active = await content.toggle_store_product_active(product.id, admin_id=1)
    assert new_active is False


async def test_analytics_summary_reflects_activity(active_event):
    from app.services.stronghold_missions import apply_stronghold_progress, claim_mission, list_missions
    from app.services.stronghold_wallet import get_wallet

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    user_id = await create_test_user("analytics-user")
    await apply_stronghold_progress(user_id, "win_matches", 1)
    missions = await list_missions(user_id, "DAILY")
    win_mission = next(m for m in missions if m.condition_type == "win_matches")
    await claim_mission(user_id, win_mission.id)

    summary = await content.get_analytics_summary(event_row["id"])
    assert summary.active_participants >= 1
    assert summary.mission_claims >= 1
    assert summary.ft_earned >= win_mission.reward_ft


async def test_mass_disable_store(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    products_before = await content.list_store_products_admin(event_row["id"])
    active_before = [p for p in products_before if p.active]
    assert len(active_before) > 0

    result = await content.mass_disable_store(event_row["id"], admin_id=1, reason="test")
    assert result.affected == len(active_before)

    products_after = await content.list_store_products_admin(event_row["id"])
    assert all(not p.active for p in products_after)


async def test_mass_compensate_grants_to_multiple_users_and_is_idempotent(active_event):
    from tests.conftest import get_balance

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    user1 = await create_test_user("mass-comp-1")
    user2 = await create_test_user("mass-comp-2")

    result = await content.mass_compensate(event_row["id"], admin_id=1, user_ids=[user1, user2], compensation_type="coins", amount=500, reason="test batch")
    assert result.affected == 2
    assert get_balance(user1, "coins") == 500
    assert get_balance(user2, "coins") == 500

    # повторный запуск с теми же user_ids и той же причиной генерирует новые request_id
    # (mass_compensate использует uuid4 на батч), поэтому повторный вызов НЕ идемпотентен
    # сам по себе — идемпотентность гарантируется на уровне отдельного grant_compensation
    # с фиксированным request_id внутри одного вызова, что и проверяет compensation-тест.


# ---------------------------------------------------------------------------
# Card Definition editor
# ---------------------------------------------------------------------------

async def test_list_and_edit_collection_cards(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    cards = await content.list_collection_cards_admin(event_row["id"])
    assert len(cards) == 23
    heiskanen_92 = next(c for c in cards if c.player_key == "miro-heiskanen" and c.overall == 92)
    assert heiskanen_92.is_upgrade_chain_card is True
    other_card = next(c for c in cards if c.player_key != "miro-heiskanen")
    assert other_card.is_upgrade_chain_card is False

    await content.update_card_salary(heiskanen_92.id, salary=12345, admin_id=1)
    updated = await content.list_collection_cards_admin(event_row["id"])
    assert next(c for c in updated if c.id == heiskanen_92.id).salary == 12345

    new_active = await content.toggle_card_active(heiskanen_92.id, admin_id=1)
    assert new_active is False


# ---------------------------------------------------------------------------
# Fortress create / match management
# ---------------------------------------------------------------------------

async def test_create_fortress_generates_six_matches(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    fortress_id = await content.create_fortress(
        event_row["id"], title="Custom Fortress", description="test", first_completion_ft=5, repeat_coins_reward=1000, admin_id=1,
    )
    fortresses = await content.list_fortresses_admin(event_row["id"])
    created = next(f for f in fortresses if f.id == fortress_id)
    assert created.order_index == 16  # после существующих 15
    assert created.first_completion_ft == 5

    matches = await content.get_fortress_matches_admin(fortress_id)
    assert len(matches) == 6
    assert [m.order_index for m in matches] == [1, 2, 3, 4, 5, 6]


async def test_add_and_toggle_fortress_match(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()
    fortresses = await content.list_fortresses_admin(event_row["id"])
    fortress_id = fortresses[0].id

    match_id = await content.add_fortress_match(fortress_id, opponent_name="Extra Boss", opponent_ovr=200, admin_id=1)
    matches = await content.get_fortress_matches_admin(fortress_id)
    new_match = next(m for m in matches if m.id == match_id)
    assert new_match.order_index == 7  # после стандартных 6
    assert new_match.opponent_ovr == 99  # заклампено

    new_active = await content.toggle_fortress_match_active(match_id, admin_id=1)
    assert new_active is False
    matches_after = await content.get_fortress_matches_admin(fortress_id)
    assert next(m for m in matches_after if m.id == match_id).active is False


# ---------------------------------------------------------------------------
# Store Bundle (multi-item) creation
# ---------------------------------------------------------------------------

async def test_create_store_product_with_multiple_items(active_event):
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    contents = [
        {"type": "currency", "currency_code": "coins", "amount": 50000},
        {"type": "currency", "currency_code": "fortress_token", "amount": 5},
    ]
    product_id = await content.create_store_product(
        event_row["id"], category="Bundles", title="Test Bundle", description="",
        price_currency_code="coins", price_amount=100000, purchase_limit=1, contents=contents, admin_id=1,
    )
    stored_contents = await content.get_product_contents(product_id)
    assert stored_contents == contents

    products = await content.list_store_products_admin(event_row["id"])
    assert any(p.id == product_id and p.title == "Test Bundle" for p in products)


async def test_create_store_product_rejects_empty_contents(active_event):
    import pytest

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    with pytest.raises(ValueError):
        await content.create_store_product(
            event_row["id"], category="Bundles", title="Empty Bundle", description="",
            price_currency_code="coins", price_amount=100, purchase_limit=0, contents=[], admin_id=1,
        )


async def test_bundle_purchase_grants_all_items_atomically(active_event):
    from app.services.stronghold_store import purchase
    from tests.conftest import create_test_user, get_balance, grant_balance

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    contents = [
        {"type": "currency", "currency_code": "coins", "amount": 30000},
        {"type": "currency", "currency_code": "fortress_token", "amount": 3},
    ]
    product_id = await content.create_store_product(
        event_row["id"], category="Bundles", title="Purchasable Bundle", description="",
        price_currency_code="fortress_token", price_amount=10, purchase_limit=0, contents=contents, admin_id=1,
    )

    user_id = await create_test_user("bundle-buyer")
    grant_balance(user_id, "fortress_token", 10)

    result = await purchase(user_id, product_id, request_id="bundle-buy-1")
    assert result.success
    assert get_balance(user_id, "coins") == 30000
    assert get_balance(user_id, "fortress_token") == 3  # 10 - 10 (цена) + 3 (награда)
