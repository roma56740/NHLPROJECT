import pytest

from app.database.db import get_connection
from app.services import ranked_bot, ranked_core
from tests.conftest import create_test_user

_SEQ = 90000


def _seed_exact_catalog(overall: int) -> None:
    global _SEQ
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        for position in ("F", "D", "G"):
            _SEQ += 1
            key = f"ranked-match-{overall}-{position}-{_SEQ}"
            connection.execute(
                """
                INSERT INTO cards
                    (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
                VALUES (?, ?, ?, ?, 'Bot Team', 'CA', ?, 'Common', 'x.png', 100, 1)
                """,
                (key, key, position, overall, int(collection["id"])),
            )
        connection.commit()


async def test_ranked_matchmaking_is_bot_only_even_with_other_users(stronghold_db):
    me = await create_test_user(telegram_id=880001, nickname="Me")
    other = await create_test_user(telegram_id=880002, nickname="InactiveRealUser")
    with get_connection() as connection:
        connection.execute("UPDATE users SET league = 'NHL' WHERE id IN (?, ?)", (me, other))
        connection.commit()

    _seed_exact_catalog(95)
    _seed_exact_catalog(96)

    opponent = await ranked_core.find_ranked_opponent(me, None, 95)
    assert opponent.type == "bot"
    assert opponent.user_id is None
    assert opponent.name != "InactiveRealUser"
    assert opponent.bot_overview is not None
    assert opponent.bot_overview.average_overall in {95, 96}


async def test_match_target_is_same_or_plus_one(stronghold_db):
    _seed_exact_catalog(94)
    _seed_exact_catalog(95)
    for _ in range(30):
        assert ranked_bot.pick_match_target_ovr(94) in {94, 95}


async def test_match_target_never_exceeds_99(stronghold_db):
    _seed_exact_catalog(99)
    for _ in range(10):
        assert ranked_bot.pick_match_target_ovr(99) == 99


async def test_bot_effective_match_ovr_ignores_chemistry_bonus(stronghold_db):
    _seed_exact_catalog(95)
    result = await ranked_bot.build_bot_lineup("NHL", target_ovr=95)
    assert result.overview.average_overall == 95
    opponent = ranked_core.RankedOpponent(user_id=None, name="BOT", type="bot", bot_overview=result.overview)
    assert await ranked_core._resolve_opponent_ovr(opponent, 95) == 95
