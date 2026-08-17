import pytest

from app.database.db import get_connection
from app.services.stronghold_common import StrongholdError
from app.services.stronghold_fortress import get_fortress, list_fortresses, play_fortress_match
from tests.conftest import build_full_stronghold_lineup, create_test_user, get_balance


async def _win_match(telegram_id: int, user_id: int, fortress_match_id: int, *, force_win: bool = True):
    """Подставляет слабого соперника (opponent_ovr=1) и переигрывает до победы.

    Движок содержит настоящую случайность (даже при opponent_ovr=1 есть небольшой шанс
    проигрыша в овертайме/буллитах через weighted_success, см. matches.py) — единственная
    попытка без ретрая делает тест недетерминированным (см. test_stronghold_endless.py
    для того же паттерна)."""
    if force_win:
        with get_connection() as connection:
            connection.execute("UPDATE stronghold_fortress_matches SET opponent_ovr = 1 WHERE id = ?", (fortress_match_id,))
            connection.commit()
    for _attempt in range(20):
        result = await play_fortress_match(telegram_id, user_id, fortress_match_id)
        if result.is_win or not force_win:
            return result
    return result


async def _telegram_id_for(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"])


async def test_fortress_1_available_others_locked_initially(active_event):
    """С НОВЫМ глобальным расписанием (см. app/services/stronghold_schedule.py):
    `active_event` стартовал 1 день назад -> башня №1 доступна сразу, башня №2
    (интервал по умолчанию 1 день) тоже уже открыта по времени, а башня №3
    (открывается через 2 дня после старта) всё ещё заблокирована — расписание
    единое для всех, прогресс тут ни при чём."""
    user_id = await create_test_user("fortress-user")
    await build_full_stronghold_lineup(user_id)

    fortresses = await list_fortresses(user_id)
    assert len(fortresses) == 15
    assert fortresses[0].status == "AVAILABLE"
    assert fortresses[2].status == "LOCKED"
    assert fortresses[2].unlock_at is not None


async def test_playing_match_without_collection_card_is_blocked(active_event):
    user_id = await create_test_user("no-collection-user")
    # намеренно НЕ строим состав с картой коллекции
    from app.services.lineup import set_lineup_card
    from app.database.db import get_connection as gc

    with gc() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES ('Filler G', 'filler-g-nc', 'G', 60, 'T', 'C', ?, 'Common', 'x.png', 100, 1)
            """,
            (collection["id"],),
        )
        card_id = cursor.lastrowid
        cursor2 = connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, card_id)
        )
        connection.commit()
    result = await set_lineup_card(user_id, "G", cursor2.lastrowid)
    assert result.success

    telegram_id = await _telegram_id_for(user_id)
    fortress = await get_fortress(user_id, (await list_fortresses(user_id))[0].id)
    first_match = fortress.matches[0]

    with pytest.raises(StrongholdError) as exc_info:
        await play_fortress_match(telegram_id, user_id, first_match.id)
    assert exc_info.value.code in ("LINEUP_INCOMPLETE", "COLLECTION_CARD_REQUIRED")


async def test_full_fortress_completion_awards_ft_once(active_event):
    user_id = await create_test_user("full-fortress-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    fortress_summary = (await list_fortresses(user_id))[0]
    fortress = await get_fortress(user_id, fortress_summary.id)

    total_ft_awarded = 0
    for match in fortress.matches:
        result = await _win_match(telegram_id, user_id, match.id)
        assert result.success
        assert result.is_win
        total_ft_awarded += result.ft_awarded

    assert total_ft_awarded == fortress.first_completion_ft
    assert get_balance(user_id, "fortress_token") == fortress.first_completion_ft

    updated = await get_fortress(user_id, fortress.id)
    assert updated.status == "COMPLETED"
    assert updated.first_completion_reward_claimed is True

    fortresses = await list_fortresses(user_id)
    assert fortresses[1].status == "AVAILABLE"  # Fortress 2 разблокирована


async def test_repeat_completion_does_not_award_ft_again(active_event):
    user_id = await create_test_user("repeat-fortress-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    fortress_summary = (await list_fortresses(user_id))[0]
    fortress = await get_fortress(user_id, fortress_summary.id)
    for match in fortress.matches:
        await _win_match(telegram_id, user_id, match.id)

    balance_after_first_completion = get_balance(user_id, "fortress_token")

    # играем последний матч крепости ещё раз
    last_match = fortress.matches[-1]
    result = await _win_match(telegram_id, user_id, last_match.id)
    assert result.success
    assert result.ft_awarded == 0

    assert get_balance(user_id, "fortress_token") == balance_after_first_completion


async def test_second_match_locked_until_first_won(active_event):
    user_id = await create_test_user("sequential-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    fortress_summary = (await list_fortresses(user_id))[0]
    fortress = await get_fortress(user_id, fortress_summary.id)
    second_match = fortress.matches[1]

    with pytest.raises(StrongholdError) as exc_info:
        await play_fortress_match(telegram_id, user_id, second_match.id)
    assert exc_info.value.code == "FORTRESS_MATCH_LOCKED"


async def test_fortress_2_available_without_completing_fortress_1(active_event):
    """ТЗ "ГЛОБАЛЬНОЕ ОТКРЫТИЕ БАШЕН": доступность башни №2 определяется ТОЛЬКО
    расписанием (событие стартовало 1 день назад -> башня №2 уже открыта по
    времени), а НЕ тем, пройдена ли башня №1 — старая механика последовательного
    прогресса для этого больше не действует."""
    user_id = await create_test_user("no-progress-needed-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    fortresses = await list_fortresses(user_id)
    assert fortresses[1].status != "LOCKED"

    fortress2 = await get_fortress(user_id, fortresses[1].id)
    first_match_of_fortress2 = fortress2.matches[0]
    # Не должно бросать FORTRESS_LOCKED несмотря на то, что башня №1 не пройдена.
    result = await play_fortress_match(telegram_id, user_id, first_match_of_fortress2.id)
    assert result.success


async def test_fortress_3_locked_when_schedule_not_reached(active_event):
    """Башня №3 (открывается через 2 дня после старта) остаётся заблокированной по
    расписанию, даже если бы игрок гипотетически прошёл башню №2 (тут прогресс не
    репрезентативен, важно само наличие блокировки FORTRESS_LOCKED по времени)."""
    user_id = await create_test_user("time-locked-user")
    await build_full_stronghold_lineup(user_id)
    telegram_id = await _telegram_id_for(user_id)

    fortresses = await list_fortresses(user_id)
    fortress3 = await get_fortress(user_id, fortresses[2].id)
    first_match_of_fortress3 = fortress3.matches[0]

    with pytest.raises(StrongholdError) as exc_info:
        await play_fortress_match(telegram_id, user_id, first_match_of_fortress3.id)
    assert exc_info.value.code == "FORTRESS_LOCKED"


async def test_match_lock_rejects_second_acquire_while_held(active_event):
    """match_guard.try_acquire_match_lock — прямая проверка защиты от повторного входа.

    Все DB-операции в проекте синхронны под async def (см. docs/THE_STRONGHOLD_SPEC.md
    и аудит архитектуры): у play_fortress_match нет ни одной настоящей точки
    приостановки, поэтому asyncio.gather(...) с двумя такими вызовами исполняет их
    строго последовательно (без реального чередования) и не может продемонстрировать
    гонку. Поэтому сам лок проверяется напрямую, а не через gather().
    """
    from app.services.match_guard import release_match_lock, try_acquire_match_lock

    user_id = await create_test_user("lock-user")

    first_acquired = await try_acquire_match_lock(user_id)
    second_acquired = await try_acquire_match_lock(user_id)
    assert first_acquired is True
    assert second_acquired is False

    await release_match_lock(user_id)
    third_acquired = await try_acquire_match_lock(user_id)
    assert third_acquired is True
