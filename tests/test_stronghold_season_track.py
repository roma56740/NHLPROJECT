import pytest

from app.services.stronghold_common import StrongholdError
from app.services.stronghold_season_track import add_event_xp, claim_level, get_track
from tests.conftest import create_test_user, get_balance


async def test_levels_unlock_as_xp_grows(active_event):
    user_id = await create_test_user("season-user")
    track = await get_track(user_id)
    assert track.levels[0].status == "LOCKED"

    await add_event_xp(user_id, 100)
    track = await get_track(user_id)
    assert track.levels[0].status == "AVAILABLE"
    assert track.levels[1].status == "LOCKED"


async def test_claim_grants_reward_and_blocks_double_claim(active_event):
    user_id = await create_test_user("season-claim-user")
    await add_event_xp(user_id, 250)

    track = await get_track(user_id)
    level2 = track.levels[1]
    assert level2.status == "AVAILABLE"
    assert level2.reward_ft == 5

    result = await claim_level(user_id, level2.id)
    assert result.reward_ft == 5
    assert get_balance(user_id, "fortress_token") == 5

    with pytest.raises(StrongholdError) as exc_info:
        await claim_level(user_id, level2.id)
    assert exc_info.value.code == "SEASON_REWARD_ALREADY_CLAIMED"


async def test_claim_locked_level_is_rejected(active_event):
    user_id = await create_test_user("season-locked-user")
    track = await get_track(user_id)
    locked_level = track.levels[-1]

    with pytest.raises(StrongholdError) as exc_info:
        await claim_level(user_id, locked_level.id)
    assert exc_info.value.code == "SEASON_LEVEL_LOCKED"


async def test_season_track_total_ft_matches_spec(active_event):
    user_id = await create_test_user("season-total-user")
    await add_event_xp(user_id, 100_000)

    track = await get_track(user_id)
    total_ft = 0
    for level in track.levels:
        result = await claim_level(user_id, level.id)
        total_ft += result.reward_ft

    assert total_ft == 50
    assert get_balance(user_id, "fortress_token") == 50
