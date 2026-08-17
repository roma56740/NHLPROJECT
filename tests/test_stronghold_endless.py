import pytest

from app.database.db import get_connection
from app.services.stronghold_common import StrongholdError
from app.services.stronghold_endless import get_status, play_wave
from tests.conftest import build_full_stronghold_lineup, create_test_user, get_balance


async def _telegram_id_for(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"])


async def _unlock_all_fortresses_for_test() -> None:
    """Этот тест-файл проверяет Endless Siege (открывается после прохождения ВСЕХ 15
    крепостей), а не глобальное расписание башен (см. app/services/stronghold_schedule.py) —
    поэтому здесь расписание принудительно "перематывается" вперёд (как ручное
    открытие администратором всех башен разом), чтобы можно было пройти все 15 за
    один тест независимо от того, сколько башен уже открыто по времени."""
    from app.services.stronghold_common import STRONGHOLD_SLUG, get_event_by_slug

    event = await get_event_by_slug(STRONGHOLD_SLUG)
    with get_connection() as connection:
        connection.execute(
            "UPDATE stronghold_events SET manual_unlock_override_count = 15 WHERE id = ?", (event.id,)
        )
        connection.commit()


async def _complete_all_fortresses(user_id: int, telegram_id: int) -> None:
    """Матч-движок содержит настоящую случайность (даже при opponent_ovr=1 есть шанс
    проигрыша в овертайме/буллитах, см. matches.py:weighted_success) — поэтому каждый
    матч переигрывается до победы, а не запускается ровно один раз."""
    from app.services.stronghold_fortress import get_fortress, list_fortresses, play_fortress_match

    await _unlock_all_fortresses_for_test()
    for _ in range(15):
        fortress_summary = next(f for f in await list_fortresses(user_id) if f.status in ("AVAILABLE", "IN_PROGRESS"))
        fortress = await get_fortress(user_id, fortress_summary.id)
        for match in fortress.matches:
            if match.status in ("WON", "COMPLETED"):
                continue
            with get_connection() as connection:
                connection.execute("UPDATE stronghold_fortress_matches SET opponent_ovr = 1 WHERE id = ?", (match.id,))
                connection.commit()
            for _attempt in range(20):
                result = await play_fortress_match(telegram_id, user_id, match.id)
                if result.is_win:
                    break


async def test_endless_locked_before_fortress_15(active_event):
    user_id = await create_test_user("endless-locked-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    status = await get_status(user_id)
    assert status.unlocked is False

    with pytest.raises(StrongholdError) as exc_info:
        await play_wave(telegram_id, user_id)
    assert exc_info.value.code == "ENDLESS_SIEGE_LOCKED"


async def test_endless_unlocks_after_fortress_15_and_awards_ft(active_event):
    user_id = await create_test_user("endless-unlocked-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    await _complete_all_fortresses(user_id, telegram_id)

    status = await get_status(user_id)
    assert status.unlocked is True
    assert status.current_wave == 1

    with get_connection() as connection:
        connection.execute(
            "UPDATE stronghold_endless_config SET base_opponent_ovr = 1, max_opponent_ovr = 1 WHERE event_id = ?",
            (active_event,),
        )
        connection.commit()

    result = await play_wave(telegram_id, user_id)
    assert result.success
    assert result.is_win
    assert result.ft_awarded == 2

    status_after = await get_status(user_id)
    assert status_after.current_wave == 2
    assert status_after.best_wave == 1
    assert status_after.weekly_ft_earned == 2


async def test_endless_weekly_ft_cap_stops_new_ft(active_event, monkeypatch):
    """Что тестируется здесь — арифметика weekly_ft_cap, а НЕ исход матча. Даже при
    opponent_ovr=1 движок симуляции (app.services.matches.build_simulation) может
    статистически проиграть регуляционное время (goal_chance по формуле в
    simulate_period клампится, не идёт к 0%/100%) — это не связано ни с одной из
    5 систем этой сессии, а с реальной случайностью самого матч-движка. Чтобы
    тест проверял именно FT-cap, а не терпел редкий проигрыш по вероятности,
    build_simulation детерминированно подменяется на гарантированную победу
    пользователя — сама симуляция матча тестируется отдельно в других местах."""
    import app.services.matches as matches_module

    def _deterministic_user_win(*, user_ovr, opponent_ovr, lineup_cards, opponent_name):
        return 5, 0, False, False, [], []

    monkeypatch.setattr(matches_module, "build_simulation", _deterministic_user_win)

    user_id = await create_test_user("endless-capped-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)
    await _complete_all_fortresses(user_id, telegram_id)
    ft_balance_before_endless = get_balance(user_id, "fortress_token")  # включает 220 FT за Fortress

    with get_connection() as connection:
        connection.execute(
            "UPDATE stronghold_endless_config SET base_opponent_ovr = 1, max_opponent_ovr = 1, weekly_ft_cap = 3, ft_per_wave = 2 WHERE event_id = ?",
            (active_event,),
        )
        connection.commit()

    r1 = await play_wave(telegram_id, user_id)  # +2 (0 -> 2)
    r2 = await play_wave(telegram_id, user_id)  # +1 (капается до 3)
    r3 = await play_wave(telegram_id, user_id)  # +0, лимит исчерпан

    assert r1.ft_awarded == 2
    assert r2.ft_awarded == 1
    assert r3.ft_awarded == 0

    status = await get_status(user_id)
    assert status.weekly_ft_earned == 3
    assert status.current_wave == 4  # волны продолжают засчитываться и без FT
    assert get_balance(user_id, "fortress_token") - ft_balance_before_endless == 3
