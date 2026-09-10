from __future__ import annotations

import pytest

from app.database.db import get_connection
from app.services.lineup import LineupCard
from app.services.mastery import (
    MASTERY_MAX_POINTS,
    award_mastery_for_match,
    claim_mastery_reward,
    get_mastery_progress,
)
from app.services.xfactor_battle import get_lineup_battle_modifiers
from app.services.xfactors import (
    get_installed_xfactors,
    get_user_xfactor_quantity,
    grant_xfactor,
    install_xfactor,
    quicksell_xfactor,
    remove_installed_xfactor,
)
from tests.conftest import create_test_user, get_balance


def _create_owned_card(user_id: int, *, name: str, player_key: str, position: str, slot: str | None = None) -> tuple[int, int]:
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections ORDER BY id LIMIT 1").fetchone()
        card_id = int(
            connection.execute(
                """
                INSERT INTO cards(name, player_key, position, overall, team, country, collection_id, rarity, image_path, active)
                VALUES (?, ?, ?, 99, 'Test', 'Test', ?, 'Legendary', 'assets/uploads/test.png', 1)
                """,
                (name, player_key, position, int(collection["id"])),
            ).lastrowid
        )
        user_card_id = int(
            connection.execute(
                """
                INSERT INTO user_cards(user_id, card_id, is_in_lineup, lineup_slot, obtained_from)
                VALUES (?, ?, ?, ?, 'test')
                """,
                (user_id, card_id, 1 if slot else 0, slot),
            ).lastrowid
        )
        connection.commit()
    return card_id, user_card_id


def _lineup_card(card_id: int, user_card_id: int, name: str, player_key: str, position: str, slot: str) -> LineupCard:
    return LineupCard(
        user_card_id=user_card_id,
        card_id=card_id,
        name=name,
        player_key=player_key,
        position=position,
        overall=99,
        team="Test",
        country="Test",
        collection_name="Test",
        rarity="Legendary",
        image_path="assets/uploads/test.png",
        lineup_slot=slot,
        collection_code="test",
        salary=0,
    )


@pytest.mark.asyncio
async def test_xfactor_catalog_and_inventory_lifecycle(stronghold_db):
    user_id = await create_test_user("xf-lifecycle")
    _, user_card_id = _create_owned_card(user_id, name="Sidney Crosby", player_key="sidney_crosby", position="F")

    with get_connection() as connection:
        counts = connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN is_mastery=0 THEN 1 ELSE 0 END) AS regular, SUM(CASE WHEN is_mastery=1 THEN 1 ELSE 0 END) AS mastery FROM xfactors"
        ).fetchone()
    assert int(counts["total"]) == 37
    assert int(counts["regular"]) == 27
    assert int(counts["mastery"]) == 10

    grant_xfactor(user_id, "wheels", 2)
    assert install_xfactor(user_id, user_card_id, "wheels").success
    assert get_user_xfactor_quantity(user_id, "wheels") == 1
    assert [item.xfactor.code for item in get_installed_xfactors(user_card_id)] == ["wheels"]

    coins_before = get_balance(user_id, "coins")
    assert quicksell_xfactor(user_id, "wheels").success
    assert get_user_xfactor_quantity(user_id, "wheels") == 0
    assert get_balance(user_id, "coins") - coins_before == 20_000

    assert remove_installed_xfactor(user_id, user_card_id, 1).success
    assert get_installed_xfactors(user_card_id) == []
    assert get_user_xfactor_quantity(user_id, "wheels") == 0


@pytest.mark.asyncio
async def test_three_slots_and_replacement_destroy_old_factor(stronghold_db):
    user_id = await create_test_user("xf-slots")
    _, user_card_id = _create_owned_card(user_id, name="Pavel Datsyuk", player_key="pavel_datsyuk", position="F")
    for code in ("elite_edges", "wheels", "tape_to_tape", "unstoppable"):
        grant_xfactor(user_id, code)

    assert install_xfactor(user_id, user_card_id, "elite_edges").success
    assert install_xfactor(user_id, user_card_id, "wheels").success
    assert install_xfactor(user_id, user_card_id, "tape_to_tape").success
    full = install_xfactor(user_id, user_card_id, "unstoppable")
    assert not full.success

    replaced = install_xfactor(user_id, user_card_id, "unstoppable", replace_slot=2)
    assert replaced.success
    installed = {item.slot_no: item.xfactor.code for item in get_installed_xfactors(user_card_id)}
    assert installed == {1: "elite_edges", 2: "unstoppable", 3: "tape_to_tape"}
    # The replaced Wheels item is destroyed rather than returned to inventory.
    assert get_user_xfactor_quantity(user_id, "wheels") == 0


@pytest.mark.asyncio
async def test_quick_draw_only_activates_in_center_slot(stronghold_db):
    user_id = await create_test_user("xf-center")
    card_id, user_card_id = _create_owned_card(user_id, name="Sidney Crosby", player_key="sidney_crosby", position="F")
    grant_xfactor(user_id, "quick_draw")
    assert install_xfactor(user_id, user_card_id, "quick_draw").success

    center = _lineup_card(card_id, user_card_id, "Sidney Crosby", "sidney_crosby", "F", "F2")
    wing = _lineup_card(card_id, user_card_id, "Sidney Crosby", "sidney_crosby", "F", "F1")
    assert "quick_draw" in get_lineup_battle_modifiers([center]).active_codes
    assert "quick_draw" not in get_lineup_battle_modifiers([wing]).active_codes


@pytest.mark.asyncio
async def test_mastery_awards_every_eligible_player_and_is_idempotent(stronghold_db):
    user_id = await create_test_user("mastery-match")
    crosby_id, crosby_uc = _create_owned_card(user_id, name="Sidney Crosby", player_key="sidney-crosby", position="F", slot="F2")
    ovechkin_id, ovechkin_uc = _create_owned_card(user_id, name="Alexander Ovechkin", player_key="alexander_ovechkin", position="F", slot="F1")
    other_id, other_uc = _create_owned_card(user_id, name="Other", player_key="other_player", position="D", slot="D1")
    lineup = [
        _lineup_card(crosby_id, crosby_uc, "Sidney Crosby", "sidney-crosby", "F", "F2"),
        _lineup_card(ovechkin_id, ovechkin_uc, "Alexander Ovechkin", "alexander_ovechkin", "F", "F1"),
        _lineup_card(other_id, other_uc, "Other", "other_player", "D", "D1"),
    ]

    with get_connection() as connection:
        match_id = int(connection.execute("INSERT INTO matches(user_id, opponent_name, result) VALUES (?, 'Bot', 'win')", (user_id,)).lastrowid)
        first = award_mastery_for_match(connection, user_id=user_id, match_id=match_id, lineup_cards=lineup, is_win=True)
        second = award_mastery_for_match(connection, user_id=user_id, match_id=match_id, lineup_cards=lineup, is_win=True)
        connection.commit()

    assert set(first) == {"sidney_crosby", "alexander_ovechkin"}
    assert second == {}
    assert get_mastery_progress(user_id, "sidney_crosby").points == 50
    assert get_mastery_progress(user_id, "alexander_ovechkin").points == 50
    assert get_mastery_progress(user_id, "other_player") is None

    with get_connection() as connection:
        loss_match_id = int(connection.execute("INSERT INTO matches(user_id, opponent_name, result) VALUES (?, 'Bot', 'loss')", (user_id,)).lastrowid)
        award_mastery_for_match(connection, user_id=user_id, match_id=loss_match_id, lineup_cards=lineup, is_win=False)
        connection.commit()
    assert get_mastery_progress(user_id, "sidney_crosby").points == 60


@pytest.mark.asyncio
async def test_manual_mastery_claims_future_slots_and_unique_lock(stronghold_db):
    user_id = await create_test_user("mastery-rewards")
    _, crosby_uc = _create_owned_card(user_id, name="Sidney Crosby", player_key="sidney-crosby", position="F")
    _, ovi_uc = _create_owned_card(user_id, name="Alexander Ovechkin", player_key="alexander_ovechkin", position="F")

    with get_connection() as connection:
        connection.execute(
            "INSERT INTO user_player_mastery(user_id, player_key, points) VALUES (?, 'sidney_crosby', 1000000)",
            (user_id,),
        )
        connection.commit()

    # 60k reward is a normal inventory item, manually claimed once.
    first = claim_mastery_reward(user_id, "sidney_crosby", 60_000)
    assert first.success
    assert get_user_xfactor_quantity(user_id, "quick_draw") == 1
    assert not claim_mastery_reward(user_id, "sidney_crosby", 60_000).success

    # Reserved future slots cannot be claimed even at max mastery.
    assert not claim_mastery_reward(user_id, "sidney_crosby", 180_000).success
    assert not claim_mastery_reward(user_id, "sidney_crosby", 700_000).success

    unique = claim_mastery_reward(user_id, "sidney_crosby", MASTERY_MAX_POINTS)
    assert unique.success
    assert get_user_xfactor_quantity(user_id, "complete_player") == 1
    assert not quicksell_xfactor(user_id, "complete_player").success
    # Canonical player-key matching accepts '-' vs '_' for the same hockey player.
    assert install_xfactor(user_id, crosby_uc, "complete_player").success

    # A mastery factor cannot be attached to any other hockey player.
    grant_xfactor(user_id, "complete_player")
    assert not install_xfactor(user_id, ovi_uc, "complete_player").success
