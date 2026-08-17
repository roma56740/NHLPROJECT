"""Проверяет, что добавление THE STRONGHOLD не сломало существующие системы проекта."""

from app.database.db import get_connection
from app.services.lineup import get_lineup_overview
from app.services.matches import play_quick_match
from app.services.shop import get_shop_packs_page
from tests.conftest import create_test_user


async def test_router_setup_still_works(stronghold_db, app_router):
    assert app_router is not None


async def test_existing_user_registration_and_starter_kit_unaffected(stronghold_db):
    user_id = await create_test_user("regression-user")
    with get_connection() as connection:
        user_row = connection.execute("SELECT league, nickname FROM users WHERE id = ?", (user_id,)).fetchone()
    assert user_row["league"] == "NCAA"
    assert user_row["nickname"]


async def test_existing_lineup_overview_still_computes(stronghold_db):
    user_id = await create_test_user("regression-lineup-user")
    overview = await get_lineup_overview(user_id)
    assert overview.total_slots == 6
    assert overview.salary_cap > 0


async def test_existing_shop_listing_unaffected(stronghold_db):
    user_id = await create_test_user("regression-shop-user")
    page = await get_shop_packs_page(user_id=user_id, page=1)
    assert page is not None


async def test_regular_quick_match_without_stronghold_lineup(stronghold_db):
    from tests.conftest import give_and_slot_card

    user_id = await create_test_user("regression-match-user")
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])
        card_ids = {}
        for slot, position in [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]:
            cursor = connection.execute(
                """
                INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
                VALUES (?, ?, ?, 60, 'T', 'C', ?, 'Common', 'x.png', 100, 1)
                """,
                (f"Regression {slot}", f"regression-{slot.lower()}-{user_id}", position, collection_id),
            )
            card_ids[slot] = int(cursor.lastrowid)
        connection.commit()

    for slot, card_id in card_ids.items():
        await give_and_slot_card(user_id, card_id, slot)

    with get_connection() as connection:
        telegram_id = int(connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"])

    result = await play_quick_match(telegram_id)
    assert result.success
    assert result.match_id is not None
