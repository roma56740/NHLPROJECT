import pytest

from app.database.db import get_connection
from app.services.stronghold_common import StrongholdError
from app.services.stronghold_missions import apply_stronghold_progress, claim_mission, list_missions
from tests.conftest import create_test_user, get_balance


async def test_progress_accumulates_and_completes_mission(active_event):
    user_id = await create_test_user("mission-user")

    missions = await list_missions(user_id, "DAILY")
    play_mission = next(m for m in missions if m.condition_type == "play_matches")
    assert play_mission.status == "ACTIVE"
    assert play_mission.progress == 0

    await apply_stronghold_progress(user_id, "play_matches", 1)
    missions = await list_missions(user_id, "DAILY")
    play_mission = next(m for m in missions if m.condition_type == "play_matches")
    assert play_mission.progress == 1
    assert play_mission.status == "ACTIVE"

    await apply_stronghold_progress(user_id, "play_matches", 1)
    missions = await list_missions(user_id, "DAILY")
    play_mission = next(m for m in missions if m.condition_type == "play_matches")
    assert play_mission.progress == 2
    assert play_mission.status == "COMPLETED"


async def test_claim_grants_reward_and_blocks_double_claim(active_event):
    user_id = await create_test_user("claim-user")
    await apply_stronghold_progress(user_id, "win_matches", 1)

    missions = await list_missions(user_id, "DAILY")
    win_mission = next(m for m in missions if m.condition_type == "win_matches")
    assert win_mission.status == "COMPLETED"

    result = await claim_mission(user_id, win_mission.id)
    assert result.reward_ft == win_mission.reward_ft
    assert result.reward_coins == win_mission.reward_coins
    assert get_balance(user_id, "fortress_token") == win_mission.reward_ft
    assert get_balance(user_id, "coins") == win_mission.reward_coins

    with pytest.raises(StrongholdError) as exc_info:
        await claim_mission(user_id, win_mission.id)
    assert exc_info.value.code == "MISSION_ALREADY_CLAIMED"


async def test_claim_before_completion_is_rejected(active_event):
    user_id = await create_test_user("early-claim-user")
    missions = await list_missions(user_id, "DAILY")
    mission = missions[0]

    with pytest.raises(StrongholdError) as exc_info:
        await claim_mission(user_id, mission.id)
    assert exc_info.value.code == "MISSION_NOT_COMPLETED"


async def test_daily_progress_isolated_per_day(active_event):
    user_id = await create_test_user("daily-reset-user")
    await apply_stronghold_progress(user_id, "win_matches", 1)

    missions = await list_missions(user_id, "DAILY")
    win_mission = next(m for m in missions if m.condition_type == "win_matches")
    await claim_mission(user_id, win_mission.id)

    with get_connection() as connection:
        connection.execute(
            "UPDATE stronghold_user_mission_progress SET period_key = '2000-01-01' WHERE user_id = ? AND mission_id = ?",
            (user_id, win_mission.id),
        )
        connection.commit()

    missions_today = await list_missions(user_id, "DAILY")
    win_mission_today = next(m for m in missions_today if m.condition_type == "win_matches")
    assert win_mission_today.progress == 0
    assert win_mission_today.status == "ACTIVE"


async def test_seasonal_mission_ft_not_double_counted_in_daily_weekly_budget(active_event):
    with get_connection() as connection:
        daily = connection.execute("SELECT SUM(reward_ft) AS t FROM stronghold_missions WHERE type='DAILY'").fetchone()["t"]
        weekly = connection.execute("SELECT SUM(reward_ft) AS t FROM stronghold_missions WHERE type='WEEKLY'").fetchone()["t"]
    assert daily == 4
    assert weekly == 20
