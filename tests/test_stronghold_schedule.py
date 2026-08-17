"""Глобальное расписание открытия башен THE STRONGHOLD: единое для всех, не
зависит от личного прогресса, восстанавливает состояние на середине сезона,
ручное открытие администратором с записью в аудит-лог. См.
app/services/stronghold_schedule.py.
"""

from datetime import timedelta

from app.database.db import get_connection
from app.services.stronghold_common import STRONGHOLD_SLUG, get_event_by_slug, utc_now
from app.services.stronghold_fortress import get_fortress, list_fortresses, play_fortress_match
from app.services.stronghold_schedule import (
    get_schedule_status,
    list_manual_unlock_history,
    manual_unlock_next,
    manual_unlock_specific,
    set_schedule_settings,
)
from tests.conftest import build_full_stronghold_lineup, create_test_user


async def _event_id() -> int:
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    return event.id


async def _set_schedule_start(days_ago: float) -> None:
    event_id = await _event_id()
    start = utc_now() - timedelta(days=days_ago)
    with get_connection() as connection:
        connection.execute(
            "UPDATE stronghold_events SET fortress_unlock_started_at = ?, fortress_unlock_interval_seconds = 86400 WHERE id = ?",
            (start.strftime("%Y-%m-%d %H:%M:%S"), event_id),
        )
        connection.commit()


async def test_collection_code_is_the_stronghold(active_event):
    """Коллекция THE STRONGHOLD ищется по нормализованному коду, не по старым ID."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT name, code FROM collections WHERE code IN ('the_stronghold', 'the-stronghold') OR lower(trim(name)) = 'the stronghold'"
        ).fetchone()
    assert row is not None
    assert row["name"].strip().lower() == "the stronghold"


async def test_tower_1_available_on_day_one(active_event):
    await _set_schedule_start(0)
    user_id = await create_test_user("sched-day1-user")
    await build_full_stronghold_lineup(user_id)
    fortresses = await list_fortresses(user_id)
    assert fortresses[0].status == "AVAILABLE"


async def test_tower_2_locked_on_day_one(active_event):
    await _set_schedule_start(0)
    user_id = await create_test_user("sched-day1-locked-user")
    await build_full_stronghold_lineup(user_id)
    fortresses = await list_fortresses(user_id)
    assert fortresses[1].status == "LOCKED"


async def test_tower_2_unlocks_next_day(active_event):
    await _set_schedule_start(1)
    user_id = await create_test_user("sched-day2-user")
    await build_full_stronghold_lineup(user_id)
    fortresses = await list_fortresses(user_id)
    assert fortresses[1].status != "LOCKED"


async def test_schedule_is_global_across_users(active_event):
    await _set_schedule_start(1)
    user_a = await create_test_user("sched-global-a")
    user_b = await create_test_user("sched-global-b")
    await build_full_stronghold_lineup(user_a)
    await build_full_stronghold_lineup(user_b)

    fortresses_a = await list_fortresses(user_a)
    fortresses_b = await list_fortresses(user_b)
    assert fortresses_a[1].status != "LOCKED"
    assert fortresses_b[1].status != "LOCKED"
    assert fortresses_a[2].status == "LOCKED"
    assert fortresses_b[2].status == "LOCKED"


async def test_new_user_sees_same_global_status(active_event):
    """Новый пользователь видит тот же прогресс расписания, что и существующий —
    ничего не зависит от даты регистрации/первого входа."""
    await _set_schedule_start(3)
    old_user = await create_test_user("sched-old-user")
    await build_full_stronghold_lineup(old_user)
    new_user = await create_test_user("sched-brand-new-user")
    await build_full_stronghold_lineup(new_user)

    old_fortresses = await list_fortresses(old_user)
    new_fortresses = await list_fortresses(new_user)
    old_statuses = [f.status != "LOCKED" for f in old_fortresses]
    new_statuses = [f.status != "LOCKED" for f in new_fortresses]
    assert old_statuses == new_statuses


async def test_locked_tower_cannot_be_played(active_event):
    await _set_schedule_start(0)
    user_id = await create_test_user("sched-cant-play-user")
    await build_full_stronghold_lineup(user_id)
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    telegram_id = int(row["telegram_id"])

    fortresses = await list_fortresses(user_id)
    fortress2 = await get_fortress(user_id, fortresses[1].id)
    from app.services.stronghold_common import StrongholdError
    import pytest

    with pytest.raises(StrongholdError) as exc_info:
        await play_fortress_match(telegram_id, user_id, fortress2.matches[0].id)
    assert exc_info.value.code == "FORTRESS_LOCKED"


async def test_locked_tower_does_not_consume_attempt_or_progress(active_event):
    await _set_schedule_start(0)
    user_id = await create_test_user("sched-no-consume-user")
    await build_full_stronghold_lineup(user_id)
    fortresses = await list_fortresses(user_id)
    fortress2 = await get_fortress(user_id, fortresses[1].id)

    with get_connection() as connection:
        before = connection.execute(
            "SELECT COUNT(*) AS n FROM stronghold_user_fortress_match_progress WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]

    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    telegram_id = int(row["telegram_id"])

    import pytest
    from app.services.stronghold_common import StrongholdError

    with pytest.raises(StrongholdError):
        await play_fortress_match(telegram_id, user_id, fortress2.matches[0].id)

    with get_connection() as connection:
        after = connection.execute(
            "SELECT COUNT(*) AS n FROM stronghold_user_fortress_match_progress WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    assert before == after


async def test_progress_persists_across_recomputation(active_event):
    """Уже пройденные башни не нужно проходить повторно — прогресс сохраняется
    независимо от расписания."""
    await _set_schedule_start(0)
    user_id = await create_test_user("sched-progress-user")
    await build_full_stronghold_lineup(user_id)
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    telegram_id = int(row["telegram_id"])

    fortresses = await list_fortresses(user_id)
    fortress1 = await get_fortress(user_id, fortresses[0].id)
    for match in fortress1.matches:
        with get_connection() as connection:
            connection.execute("UPDATE stronghold_fortress_matches SET opponent_ovr = 1 WHERE id = ?", (match.id,))
            connection.commit()
        for _ in range(20):
            result = await play_fortress_match(telegram_id, user_id, match.id)
            if result.is_win:
                break

    fortresses_after = await list_fortresses(user_id)
    assert fortresses_after[0].status == "COMPLETED"

    # Пересчёт расписания (смена интервала) не должен трогать уже сохранённый прогресс.
    await set_schedule_settings(await _event_id(), admin_id=1, interval_seconds=3600)
    fortresses_recomputed = await list_fortresses(user_id)
    assert fortresses_recomputed[0].status == "COMPLETED"


async def test_mid_season_update_computes_already_unlocked_towers(active_event):
    """Сезон уже идёт 5 дней на момент установки обновления -> должны быть открыты
    первые 6 башен (включая башню первого дня), без явной миграции/пересоздания."""
    await _set_schedule_start(5)
    status = await get_schedule_status(await _event_id())
    assert status.unlocked_count == 6


async def test_manual_unlock_next_by_admin(active_event):
    await _set_schedule_start(0)
    event_id = await _event_id()
    status_before = await get_schedule_status(event_id)
    assert status_before.unlocked_count == 1

    new_count = await manual_unlock_next(event_id, admin_id=999999999, reason="test manual unlock")
    assert new_count == 2

    status_after = await get_schedule_status(event_id)
    assert status_after.unlocked_count == 2


async def test_manual_unlock_specific_by_admin(active_event):
    await _set_schedule_start(0)
    event_id = await _event_id()
    new_count = await manual_unlock_specific(event_id, 5, admin_id=999999999, reason="test manual unlock specific")
    assert new_count == 5
    status = await get_schedule_status(event_id)
    assert status.unlocked_count == 5


async def test_manual_unlock_recorded_in_audit_log(active_event):
    await _set_schedule_start(0)
    event_id = await _event_id()
    await manual_unlock_next(event_id, admin_id=999999999, reason="audit-check")

    history = await list_manual_unlock_history(event_id)
    assert any(row["action"] == "manual_fortress_unlock" and row["reason"] == "audit-check" for row in history)


async def test_manual_unlock_does_not_relock_other_towers(active_event):
    await _set_schedule_start(3)
    event_id = await _event_id()
    status_before = await get_schedule_status(event_id)
    unlocked_before = status_before.unlocked_count

    await manual_unlock_specific(event_id, unlocked_before + 1, admin_id=999999999, reason="extend by one")
    status_after = await get_schedule_status(event_id)
    assert status_after.unlocked_count == unlocked_before + 1

    # Понижающий вызов не должен закрывать уже открытые башни (монотонность).
    await manual_unlock_specific(event_id, 1, admin_id=999999999, reason="attempt to lower")
    status_final = await get_schedule_status(event_id)
    assert status_final.unlocked_count == unlocked_before + 1
