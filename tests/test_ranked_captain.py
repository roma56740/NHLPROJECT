"""Капитан Ranked-состава: назначение/смена/снятие, прогресс дивизиона, бонус
потолка +20 000 000 при >=5 картах дивизиона капитана, защита от подмены
callback_data, автоснятие при выпадении карты из состава, изоляция от других
режимов (Stronghold/Clan War 2/обычные матчи). См. app/services/ranked_captain.py.
"""

import inspect

import pytest

from app.database.db import get_connection
from app.services import admin_divisions, ranked_captain, ranked_core
from app.services.ranked_common import RankedError
from app.services.salary import RANKED_CAPTAIN_BONUS, RANKED_SALARY_CAP
from tests.conftest import create_test_user, give_and_slot_card

_SEQ = 0


async def _make_card(team: str, *, position: str = "F", salary: int = 1000) -> int:
    global _SEQ
    _SEQ += 1
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        key = f"captain-test-{_SEQ}"
        cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES (?, ?, ?, 70, ?, 'C', ?, 'Common', 'x.png', ?, 1)
            """,
            (key.title(), key, position, team, int(collection["id"]), salary),
        )
        connection.commit()
        return int(cursor.lastrowid)


async def _make_division(name: str, teams: list[str]) -> str:
    division, error = await admin_divisions.create_division(name)
    assert error is None, error
    for team in teams:
        await admin_divisions.toggle_team_in_division(division.id, team)
    return division.code


async def _lineup_with_division(user_id: int, division_teams: list[str], *, count: int) -> list[int]:
    """Ставит `count` карт из division_teams (по кругу) + добивает оставшиеся слоты
    нейтральными картами без дивизиона. Возвращает user_card_id карт дивизиона в
    порядке заполнения (первая — потенциальный капитан)."""
    slots = [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]
    division_user_card_ids = []
    for index, (slot_code, position) in enumerate(slots):
        if index < count:
            team = division_teams[index % len(division_teams)]
            card_id = await _make_card(team, position=position)
            user_card_id = await give_and_slot_card(user_id, card_id, slot_code)
            division_user_card_ids.append(user_card_id)
        else:
            card_id = await _make_card("Neutral Team", position=position)
            await give_and_slot_card(user_id, card_id, slot_code)
    return division_user_card_ids


async def test_assign_captain_from_active_lineup(stronghold_db):
    division_code = await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-basic")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=1)

    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.user_card_id == ids[0]
    assert status.division_code == division_code


async def test_reject_someone_elses_card(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    owner = await create_test_user("cap-owner")
    attacker = await create_test_user("cap-attacker")
    ids = await _lineup_with_division(owner, ["Boston Bruins"], count=1)

    with pytest.raises(RankedError) as exc:
        await ranked_captain.assign_captain(attacker, ids[0])
    assert exc.value.code == "CAPTAIN_CARD_NOT_IN_LINEUP"


async def test_reject_card_outside_lineup(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-outside")
    await _lineup_with_division(user_id, ["Boston Bruins"], count=1)

    card_id = await _make_card("Boston Bruins")
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup) VALUES (?, ?, 'test', 0)",
            (user_id, card_id),
        )
        connection.commit()
        not_in_lineup_id = int(cursor.lastrowid)

    with pytest.raises(RankedError) as exc:
        await ranked_captain.assign_captain(user_id, not_in_lineup_id)
    assert exc.value.code == "CAPTAIN_CARD_NOT_IN_LINEUP"


async def test_reject_nonexistent_card(stronghold_db):
    user_id = await create_test_user("cap-ghost")
    await _lineup_with_division(user_id, ["Boston Bruins"], count=0)
    with pytest.raises(RankedError) as exc:
        await ranked_captain.assign_captain(user_id, 999999)
    assert exc.value.code == "CAPTAIN_CARD_NOT_IN_LINEUP"


async def test_progress_counts_captain_itself(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-count1")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=1)
    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.division_count == 1


async def test_four_cards_no_bonus(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-four")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=4)
    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.division_count == 4
    assert status.bonus_active is False
    assert status.bonus_amount == 0
    assert status.effective_cap == RANKED_SALARY_CAP


async def test_five_cards_gives_bonus(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-five")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=5)
    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.division_count == 5
    assert status.bonus_active is True
    assert status.bonus_amount == RANKED_CAPTAIN_BONUS
    assert status.effective_cap == RANKED_SALARY_CAP + RANKED_CAPTAIN_BONUS


async def test_six_cards_do_not_double_bonus(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-six")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=6)
    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.division_count == 6
    assert status.bonus_amount == RANKED_CAPTAIN_BONUS


async def test_changing_captain_changes_active_division(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    await _make_division("Pacific", ["Vegas Golden Knights"])
    user_id = await create_test_user("cap-switch")
    slots = [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]
    atlantic_card = await _make_card("Boston Bruins", position="G")
    atlantic_id = await give_and_slot_card(user_id, atlantic_card, "G")
    pacific_card = await _make_card("Vegas Golden Knights", position="D")
    pacific_id = await give_and_slot_card(user_id, pacific_card, "D1")
    for slot_code, position in slots[2:]:
        card_id = await _make_card("Neutral", position=position)
        await give_and_slot_card(user_id, card_id, slot_code)

    status = await ranked_captain.assign_captain(user_id, atlantic_id)
    assert status.division_code is not None
    first_division = status.division_code

    status = await ranked_captain.assign_captain(user_id, pacific_id)
    assert status.division_code != first_division


async def test_remove_captain_removes_bonus(stronghold_db):
    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-remove")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=5)
    await ranked_captain.assign_captain(user_id, ids[0])
    await ranked_captain.remove_captain(user_id)
    status = await ranked_captain.get_captain_status(user_id)
    assert status.user_card_id is None
    assert status.bonus_amount == 0
    assert status.effective_cap == RANKED_SALARY_CAP


async def test_removing_captain_card_from_lineup_clears_captaincy(stronghold_db):
    from app.services.lineup import remove_lineup_slot

    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-autoclear")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=5)
    await ranked_captain.assign_captain(user_id, ids[0])

    result = await remove_lineup_slot(user_id, "G")
    assert result.success

    status = await ranked_captain.get_captain_status(user_id)
    assert status.user_card_id is None


async def test_over_cap_after_losing_bonus_blocks_ranked_match(stronghold_db):
    """5 карт дивизиона + дорогой состав ровно на грани бонуса: после снятия
    капитана состав должен превышать базовый потолок и матч должен блокироваться."""
    from tests.conftest import give_and_slot_card as _slot

    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-overcap")
    with get_connection() as connection:
        telegram_id = int(
            connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"]
        )
        connection.execute("UPDATE users SET league = 'AHL' WHERE id = ?", (user_id,))
        connection.commit()

    # Состав ровно на 60000 (> база 54000, но <= 54000+20000=74000 при бонусе).
    per_card_salary = 10000
    slots = [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]
    ids = []
    for slot_code, position in slots:
        card_id = await _make_card("Boston Bruins", position=position, salary=per_card_salary)
        user_card_id = await _slot(user_id, card_id, slot_code)
        ids.append(user_card_id)

    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.bonus_active is True
    result = await ranked_core.play_ranked_match(telegram_id)
    assert result.result in ("win", "loss")

    await ranked_captain.remove_captain(user_id)
    with pytest.raises(RankedError) as exc:
        await ranked_core.play_ranked_match(telegram_id)
    assert exc.value.code == "SALARY_CAP_EXCEEDED"


async def test_bonus_isolated_to_ranked_mode():
    """Статическая проверка: капитанский бонус нигде не подключён вне Ranked Mode —
    Stronghold/Clan War 2/обычный режим считают потолок собственными фиксированными
    константами и не импортируют app.services.ranked_captain."""
    import app.services.matches as matches
    import app.services.stronghold_fortress as stronghold_fortress
    import app.services.war2_core as war2_core

    for module in (matches, stronghold_fortress, war2_core):
        source = inspect.getsource(module)
        assert "ranked_captain" not in source, f"{module.__name__} must not use ranked_captain"


async def test_callback_data_spoof_rejected(stronghold_db):
    """Подмена callback_data ranked:captain_set:<id> на произвольный/чужой ID
    отклоняется на уровне сервиса (не только UI) — покрывает и валидность, и
    отсутствие карты вовсе."""
    await _make_division("Atlantic", ["Boston Bruins"])
    victim = await create_test_user("cap-spoof-victim")
    attacker = await create_test_user("cap-spoof-attacker")
    victim_ids = await _lineup_with_division(victim, ["Boston Bruins"], count=1)

    with pytest.raises(RankedError):
        await ranked_captain.assign_captain(attacker, victim_ids[0])
    with pytest.raises(RankedError):
        await ranked_captain.assign_captain(attacker, -1)


# ---------------------------------------------------------------------------
# UI: капитан/дивизион/прогресс X/5/бонус/итоговый потолок отображаются в тексте
# экрана — не только в CaptainStatus-объекте (регрессия на изменение формата).
# ---------------------------------------------------------------------------

async def test_ui_block_shows_captain_division_progress_bonus_cap_below_threshold(stronghold_db):
    from app.handlers.ranked import _build_captain_block

    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-ui-below")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=3)
    status = await ranked_captain.assign_captain(user_id, ids[0])

    block = await _build_captain_block(user_id)

    assert f"Капитан: {status.card_name}" in block
    assert f"Дивизион: {status.division_name}" in block
    assert "Прогресс дивизиона: 3/5" in block
    assert "Бонус потолка: не активен" in block
    assert f"Текущий потолок: {RANKED_SALARY_CAP * 1000:,}".replace(",", " ") in block


async def test_ui_block_shows_active_bonus_and_boosted_cap_at_threshold(stronghold_db):
    from app.handlers.ranked import _build_captain_block

    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-ui-active")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=5)
    status = await ranked_captain.assign_captain(user_id, ids[0])
    assert status.bonus_active is True

    block = await _build_captain_block(user_id)

    assert "Прогресс дивизиона: 5/5" in block
    boosted_cap = (RANKED_SALARY_CAP + RANKED_CAPTAIN_BONUS) * 1000
    assert f"Бонус потолка: +{RANKED_CAPTAIN_BONUS * 1000:,}".replace(",", " ") in block
    assert f"Текущий потолок: {boosted_cap:,}".replace(",", " ") in block


async def test_ui_block_shows_not_assigned_when_no_captain(stronghold_db):
    from app.handlers.ranked import _build_captain_block

    user_id = await create_test_user("cap-ui-none")
    block = await _build_captain_block(user_id)

    assert "Капитан: не назначен" in block
    assert "Бонус потолка: не активен" in block


async def test_deleting_captain_card_from_lineup_auto_clears_and_updates_ui(stronghold_db):
    """Полный сквозной сценарий: капитан назначен -> его слот в составе освобождён ->
    капитанство снимается автоматически -> UI сразу показывает "не назначен"."""
    from app.handlers.ranked import _build_captain_block
    from app.services.lineup import remove_lineup_slot

    await _make_division("Atlantic", ["Boston Bruins"])
    user_id = await create_test_user("cap-ui-autoclear")
    ids = await _lineup_with_division(user_id, ["Boston Bruins"], count=5)
    await ranked_captain.assign_captain(user_id, ids[0])

    before = await _build_captain_block(user_id)
    assert "Капитан: не назначен" not in before

    result = await remove_lineup_slot(user_id, "G")
    assert result.success

    status_after = await ranked_captain.get_captain_status(user_id)
    assert status_after.user_card_id is None
    assert status_after.bonus_amount == 0

    after = await _build_captain_block(user_id)
    assert "Капитан: не назначен" in after
    assert "Бонус потолка: не активен" in after
