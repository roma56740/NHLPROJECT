"""Ranked-боты по лигам: сила зависит только от Ranked-лиги (не от состава/OVR/
зарплаты пользователя), реальные карты каталога, позиционные правила, рендер
через существующий render_lineup_image(). См. app/services/ranked_bot.py.
"""

import pytest

from app.database.db import get_connection
from app.services import ranked_bot
from app.services.renders import render_lineup_image
from tests.conftest import create_test_user

_SEQ = 0


async def _seed_catalog_card(*, position: str, overall: int, team: str = "Test Team") -> int:
    global _SEQ
    _SEQ += 1
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        key = f"bot-catalog-{_SEQ}"
        cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES (?, ?, ?, ?, ?, 'C', ?, 'Common', 'x.png', 100, 1)
            """,
            (key.title(), key, position, overall, team, int(collection["id"])),
        )
        connection.commit()
        return int(cursor.lastrowid)


async def _seed_dense_catalog_for_range(low: int, high: int) -> None:
    """Много карт каждой позиции на каждый OVR в диапазоне [low, high] — гарантирует
    точное попадание в target_ovr без расширения окна поиска."""
    for overall in range(low, high + 1):
        for position in ("G", "D", "F"):
            for _ in range(3):
                await _seed_catalog_card(position=position, overall=overall)


@pytest.mark.parametrize(
    "league,low,high",
    [
        ("NCAA", 70, 80),
        ("AHL", 80, 90),
        ("NHL", 90, 95),
        ("OLYMPICS", 95, 99),
    ],
)
async def test_league_ovr_ranges_are_exact_and_inclusive(stronghold_db, league, low, high):
    assert ranked_bot.get_league_ovr_range(league) == (low, high)
    await _seed_dense_catalog_for_range(low, high)
    for _ in range(20):
        target = ranked_bot.pick_target_ovr(league)
        assert low <= target <= high


async def test_boundary_targets_are_reachable(stronghold_db):
    """Границы диапазона включительны — random.randint(low, high) может вернуть low
    и high, не только середину."""
    seen = set()
    for _ in range(500):
        seen.add(ranked_bot.pick_target_ovr("NCAA"))
    assert 70 in seen
    assert 80 in seen


async def test_bot_strength_independent_of_user_lineup(stronghold_db):
    """build_bot_lineup() принимает только код лиги — никакого способа передать
    туда состав/OVR/зарплату пользователя не существует; тот же вызов с тем же
    league всегда работает от одного и того же диапазона независимо от того, что
    происходит в лайнапах реальных пользователей."""
    await _seed_dense_catalog_for_range(80, 90)
    # Реальные пользователи с совершенно разными (гипотетическими) OVR никак не
    # участвуют в вызове — сигнатура функции физически этого не допускает.
    for _ in range(10):
        result = await ranked_bot.build_bot_lineup("AHL")
        assert 80 <= result.overview.average_overall <= 90


async def test_bot_uses_real_card_ids_and_positions(stronghold_db):
    await _seed_dense_catalog_for_range(70, 80)
    result = await ranked_bot.build_bot_lineup("NCAA")
    overview = result.overview
    assert overview.is_complete

    with get_connection() as connection:
        for slot_code, card in overview.slots.items():
            assert card is not None
            row = connection.execute("SELECT id, position FROM cards WHERE id = ?", (card.card_id,)).fetchone()
            assert row is not None, "бот должен ссылаться на существующую карту каталога"
            assert row["position"] == card.position
            from app.services.lineup import get_slot_info

            assert card.position == get_slot_info(slot_code).position


async def test_bot_does_not_create_synthetic_cards(stronghold_db):
    await _seed_dense_catalog_for_range(70, 80)
    result = await ranked_bot.build_bot_lineup("NCAA")
    forbidden_names = {"Random Player", "Bot Player", "NCAA Forward", "Generated Card", "Temporary Card"}
    for card in result.overview.slots.values():
        assert card is not None
        assert card.name not in forbidden_names
        assert card.card_id > 0


async def test_average_ovr_within_range_and_close_to_target(stronghold_db):
    await _seed_dense_catalog_for_range(80, 90)
    result = await ranked_bot.build_bot_lineup("AHL")
    assert 80 <= result.overview.average_overall <= 90
    assert abs(result.overview.average_overall - result.target_ovr) <= 2


async def test_fallback_uses_nearest_real_cards_when_range_sparse(stronghold_db):
    """В требуемом диапазоне карт нет вовсе — состав всё равно собирается из
    ближайших РЕАЛЬНЫХ карт каталога (не выдуманных)."""
    await _seed_catalog_card(position="G", overall=70)
    await _seed_catalog_card(position="D", overall=70)
    await _seed_catalog_card(position="D", overall=71)
    await _seed_catalog_card(position="F", overall=70)
    await _seed_catalog_card(position="F", overall=71)
    await _seed_catalog_card(position="F", overall=72)

    result = await ranked_bot.build_bot_lineup("OLYMPICS")  # 95-99, но каталог только ~70
    assert result.overview.filled_count == 6
    for card in result.overview.slots.values():
        assert card is not None
        assert card.card_id > 0


async def test_no_duplicate_players_in_bot_lineup(stronghold_db):
    await _seed_dense_catalog_for_range(70, 80)
    result = await ranked_bot.build_bot_lineup("NCAA")
    player_keys = [card.player_key for card in result.overview.slots.values() if card is not None]
    assert len(player_keys) == len(set(player_keys))


async def test_bot_lineup_renders_through_real_renderer(stronghold_db):
    await _seed_dense_catalog_for_range(70, 80)
    result = await ranked_bot.build_bot_lineup("NCAA")
    image_path = render_lineup_image(result.overview, 0, title="СОСТАВ СОПЕРНИКА: test-bot")
    assert image_path.exists()
    assert image_path.suffix == ".png"


async def test_diagnose_catalog_coverage_reports_all_leagues(stronghold_db):
    before = {entry["league"]: entry["counts"] for entry in await ranked_bot.diagnose_catalog_coverage()}
    await _seed_dense_catalog_for_range(70, 80)
    report = await ranked_bot.diagnose_catalog_coverage()
    leagues = {entry["league"] for entry in report}
    assert leagues == {"NCAA", "AHL", "NHL", "OLYMPICS"}

    ncaa_entry = next(e for e in report if e["league"] == "NCAA")
    assert ncaa_entry["sufficient"] is True
    # Каждая позиция NCAA получила минимум 11 OVR-уровней x 3 карты = 33 новых карты.
    for position in ("G", "D", "F"):
        assert ncaa_entry["counts"][position] >= before["NCAA"][position] + 33
