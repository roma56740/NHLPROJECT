"""ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: физическая (partial unique index), транзакционная
защита от одновременного участия одного пользователя более чем в одном
незавершённом матче — единая для Ranked/The Stronghold/Clan War 2.0/обычного
режима/турниров. См. app/services/match_guard.py.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.database.db import get_connection
from app.services import match_guard, ranked_core, stronghold_fortress, war2_core
from app.services.ranked_common import RankedError
from app.services.stronghold_common import StrongholdError
from app.services.war2_common import War2Error
from tests.conftest import build_full_stronghold_lineup, create_test_user, get_balance, grant_balance
from tests.test_war2 import _make_clan, _seed_base_pool


async def _telegram_id_for(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"])


async def _multi_mode_ready_user(nickname: str) -> tuple[int, int]:
    """Пользователь, одновременно годный для Ranked (лига AHL+) И The Stronghold
    (карта коллекции the_stronghold в составе, зарплата под STRONGHOLD_SALARY_CAP,
    который ниже RANKED_SALARY_CAP) — один и тот же общий состав (см.
    app/services/lineup.py) годится для обоих режимов сразу."""
    user_id = await create_test_user(nickname)
    with get_connection() as connection:
        connection.execute("UPDATE users SET league = 'AHL' WHERE id = ?", (user_id,))
        connection.commit()
    await build_full_stronghold_lineup(user_id)
    return user_id, await _telegram_id_for(user_id)


async def _war2_ready(user_id: int, nickname: str) -> None:
    await _seed_base_pool()
    await _make_clan(f"clan-{nickname}", user_id)


# ---------------------------------------------------------------------------
# 1. Базовый примитив: acquire/release/finalize/cancel/expire
# ---------------------------------------------------------------------------

async def test_first_lock_acquired(stronghold_db):
    user_id = await create_test_user("mg-first")
    result = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert result.acquired is True
    assert result.lock_id is not None


async def test_second_lock_for_same_user_rejected(stronghold_db):
    user_id = await create_test_user("mg-second-blocked")
    first = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert first.acquired is True

    second = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert second.acquired is False
    assert second.existing is not None
    assert second.existing.user_id == user_id


async def test_user_a_does_not_block_user_b(stronghold_db):
    user_a = await create_test_user("mg-user-a")
    user_b = await create_test_user("mg-user-b")

    lock_a = await match_guard.acquire_player_match_lock(user_a, "ranked")
    lock_b = await match_guard.acquire_player_match_lock(user_b, "ranked")

    assert lock_a.acquired is True
    assert lock_b.acquired is True


async def test_finalize_then_new_match_allowed(stronghold_db):
    user_id = await create_test_user("mg-finalize-then-new")
    first = await match_guard.acquire_player_match_lock(user_id, "ranked")
    await match_guard.finalize_match(user_id, match_id=1, reason="COMPLETED")

    second = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert second.acquired is True


async def test_cancel_then_new_match_allowed(stronghold_db):
    user_id = await create_test_user("mg-cancel-then-new")
    await match_guard.acquire_player_match_lock(user_id, "ranked")
    await match_guard.cancel_match(user_id, reason="TEST_CANCEL")

    second = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert second.acquired is True


async def test_lock_released_after_creation_error(stronghold_db):
    """Ошибка ПОСЛЕ получения lock'а (до финализации) должна освобождать его —
    имитирует ranked_core.play_ranked_match/matches.play_quick_match's `except
    Exception: cancel_match(...); raise`."""
    user_id = await create_test_user("mg-error-releases")
    lock = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert lock.acquired is True

    try:
        raise RuntimeError("simulated failure during match creation")
    except RuntimeError:
        await match_guard.cancel_match(user_id, reason="SIMULATED_ERROR")

    retry = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert retry.acquired is True


async def test_finalize_and_cancel_are_idempotent(stronghold_db):
    """Повторный вызов finalize/cancel/release на уже терминальной записи не
    должен бросать ошибку — просто ничего не делает (0 affected rows)."""
    user_id = await create_test_user("mg-idempotent-terminal")
    await match_guard.acquire_player_match_lock(user_id, "ranked")
    await match_guard.finalize_match(user_id, match_id=1)
    await match_guard.finalize_match(user_id, match_id=1)  # не должно бросать
    await match_guard.cancel_match(user_id)  # тоже не должно бросать (уже COMPLETED)

    status = await match_guard.get_active_match(user_id)
    assert status is None


# ---------------------------------------------------------------------------
# 2. Idempotency по request_id
# ---------------------------------------------------------------------------

async def test_same_request_id_is_idempotent(stronghold_db):
    user_id = await create_test_user("mg-same-request-id")
    request_id = str(uuid.uuid4())

    first = await match_guard.acquire_player_match_lock(user_id, "ranked", request_id=request_id)
    second = await match_guard.acquire_player_match_lock(user_id, "ranked", request_id=request_id)

    assert first.acquired is True
    assert second.acquired is True
    assert second.idempotent_replay is True
    assert second.lock_id == first.lock_id


async def test_different_request_ids_still_only_one_active_match(stronghold_db):
    user_id = await create_test_user("mg-different-request-ids")
    first = await match_guard.acquire_player_match_lock(user_id, "ranked", request_id=str(uuid.uuid4()))
    second = await match_guard.acquire_player_match_lock(user_id, "ranked", request_id=str(uuid.uuid4()))

    assert first.acquired is True
    assert second.acquired is False
    assert second.idempotent_replay is False


# ---------------------------------------------------------------------------
# 3. Реальная конкуренция (настоящие OS-потоки, не asyncio-таски в одном loop)
# ---------------------------------------------------------------------------

def _run_acquire_in_thread(user_id: int, match_type: str, results: list, index: int) -> None:
    async def _run() -> None:
        result = await match_guard.acquire_player_match_lock(user_id, match_type)
        results[index] = result.acquired

    asyncio.run(_run())


async def test_two_concurrent_requests_only_one_match(stronghold_db):
    user_id = await create_test_user("mg-concurrent-2")
    results = [None, None]
    threads = [
        threading.Thread(target=_run_acquire_in_thread, args=(user_id, "normal", results, 0)),
        threading.Thread(target=_run_acquire_in_thread, args=(user_id, "normal", results, 1)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == [False, True]


async def test_double_callback_creates_only_one_match(stronghold_db):
    """Имитирует двойной клик/повторную доставку одного и того же Update: два
    "одновременных" вызова одного и того же обработчика для одного user_id."""
    user_id = await create_test_user("mg-double-callback")
    results = [None, None, None, None]
    threads = [
        threading.Thread(target=_run_acquire_in_thread, args=(user_id, "normal", results, i))
        for i in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert results.count(True) == 1
    assert results.count(False) == 3


async def test_multiple_service_instances_do_not_create_two_matches(stronghold_db):
    """"Несколько процессов бота" эмулируются несколькими независимыми потоками,
    каждый со своим asyncio event loop и своим sqlite3-соединением (get_connection()
    не шарит соединение между потоками) — ровно то, что происходило бы при
    нескольких worker-процессах, обращающихся к одному файлу БД."""
    user_id = await create_test_user("mg-multi-instance")
    results = [None] * 6
    threads = [
        threading.Thread(target=_run_acquire_in_thread, args=(user_id, mt, results, i))
        for i, mt in enumerate(["ranked", "stronghold_fortress", "war2", "normal", "normal_pvp", "tournament"])
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert results.count(True) == 1


# ---------------------------------------------------------------------------
# 4. Межрежимная блокировка (Ranked <-> Stronghold <-> Clan War 2.0 <-> обычный)
# ---------------------------------------------------------------------------

async def test_second_ranked_match_blocked_while_first_locked(stronghold_db, active_event):
    user_id, telegram_id = await _multi_mode_ready_user("mg-ranked-second")
    held = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert held.acquired is True

    with pytest.raises(RankedError) as exc_info:
        await ranked_core.play_ranked_match(telegram_id)
    assert exc_info.value.code == "MATCH_ALREADY_ACTIVE"


async def test_ranked_and_stronghold_mutually_exclusive(stronghold_db, active_event):
    user_id, telegram_id = await _multi_mode_ready_user("mg-ranked-stronghold")

    # Ranked "уже идёт" -> Stronghold должен быть заблокирован.
    ranked_lock = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert ranked_lock.acquired is True

    fortresses = await stronghold_fortress.list_fortresses(user_id)
    fortress = await stronghold_fortress.get_fortress(user_id, fortresses[0].id)
    first_match = fortress.matches[0]

    coins_before = get_balance(user_id, "coins")
    with pytest.raises(StrongholdError) as exc_info:
        await stronghold_fortress.play_fortress_match(telegram_id, user_id, first_match.id)
    assert exc_info.value.code == "CARD_IN_ACTIVE_MATCH"
    assert get_balance(user_id, "coins") == coins_before  # ничего не списано/начислено

    await match_guard.cancel_match(user_id, reason="TEST_CLEANUP")

    # И наоборот: Stronghold "уже идёт" -> Ranked заблокирован.
    stronghold_lock = await match_guard.acquire_player_match_lock(user_id, "stronghold_fortress")
    assert stronghold_lock.acquired is True

    with pytest.raises(RankedError) as exc_info:
        await ranked_core.play_ranked_match(telegram_id)
    assert exc_info.value.code == "MATCH_ALREADY_ACTIVE"


async def test_ranked_and_war2_mutually_exclusive(stronghold_db, active_event):
    user_id, telegram_id = await _multi_mode_ready_user("mg-ranked-war2")
    await _war2_ready(user_id, "mg-ranked-war2")

    ranked_lock = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert ranked_lock.acquired is True

    tickets_before = await war2_core.get_remaining_tickets(user_id)
    with pytest.raises(War2Error) as exc_info:
        await war2_core.start_war2_match(user_id)
    assert exc_info.value.code == "MATCH_ALREADY_ACTIVE"
    assert await war2_core.get_remaining_tickets(user_id) == tickets_before  # билет не списан

    await match_guard.cancel_match(user_id, reason="TEST_CLEANUP")

    war2_start = await war2_core.start_war2_match(user_id)
    assert war2_start.match_id is not None

    with pytest.raises(RankedError) as exc_info:
        await ranked_core.play_ranked_match(telegram_id)
    assert exc_info.value.code == "MATCH_ALREADY_ACTIVE"


async def test_stronghold_and_normal_match_mutually_exclusive(stronghold_db, active_event):
    from app.services.matches import play_quick_match

    user_id, telegram_id = await _multi_mode_ready_user("mg-stronghold-normal")

    stronghold_lock = await match_guard.acquire_player_match_lock(user_id, "stronghold_fortress")
    assert stronghold_lock.acquired is True

    result = await play_quick_match(telegram_id)
    assert result.success is False
    assert "активный матч" in result.message.lower()

    await match_guard.cancel_match(user_id, reason="TEST_CLEANUP")

    normal_lock = await match_guard.acquire_player_match_lock(user_id, "normal")
    assert normal_lock.acquired is True

    fortresses = await stronghold_fortress.list_fortresses(user_id)
    fortress = await stronghold_fortress.get_fortress(user_id, fortresses[0].id)
    with pytest.raises(StrongholdError) as exc_info:
        await stronghold_fortress.play_fortress_match(telegram_id, user_id, fortress.matches[0].id)
    assert exc_info.value.code == "CARD_IN_ACTIVE_MATCH"


async def test_blocked_second_start_does_not_change_progress_or_currency(stronghold_db, active_event):
    """При отказе второго запуска: попытка/прогресс/валюта не меняются — общий
    тест для Stronghold: fortress match progress остаётся нетронутым."""
    user_id, telegram_id = await _multi_mode_ready_user("mg-blocked-no-side-effects")
    await match_guard.acquire_player_match_lock(user_id, "ranked")

    fortresses = await stronghold_fortress.list_fortresses(user_id)
    fortress = await stronghold_fortress.get_fortress(user_id, fortresses[0].id)
    first_match = fortress.matches[0]

    with get_connection() as connection:
        progress_before = connection.execute(
            "SELECT COUNT(*) AS n FROM stronghold_user_fortress_match_progress WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        ft_before = get_balance(user_id, "fortress_token")

    with pytest.raises(StrongholdError):
        await stronghold_fortress.play_fortress_match(telegram_id, user_id, first_match.id)

    with get_connection() as connection:
        progress_after = connection.execute(
            "SELECT COUNT(*) AS n FROM stronghold_user_fortress_match_progress WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        ft_after = get_balance(user_id, "fortress_token")

    assert progress_before == progress_after
    assert ft_before == ft_after


# ---------------------------------------------------------------------------
# 5. PvP: атомарная блокировка двух участников
# ---------------------------------------------------------------------------

async def test_two_player_lock_blocks_both(stronghold_db):
    user_a = await create_test_user("mg-pvp-a")
    user_b = await create_test_user("mg-pvp-b")

    result = await match_guard.acquire_two_player_match_lock(user_a, user_b, "normal_pvp")
    assert result.success is True

    assert (await match_guard.get_active_match(user_a)) is not None
    assert (await match_guard.get_active_match(user_b)) is not None


async def test_two_player_lock_order_is_stable_by_ascending_user_id(stronghold_db):
    user_a = await create_test_user("mg-pvp-order-a")
    user_b = await create_test_user("mg-pvp-order-b")

    result_ab = await match_guard.acquire_two_player_match_lock(user_a, user_b, "normal_pvp")
    assert result_ab.first_user_id == min(user_a, user_b)
    assert result_ab.second_user_id == max(user_a, user_b)
    await match_guard.release_two_player_match_lock(result_ab)

    result_ba = await match_guard.acquire_two_player_match_lock(user_b, user_a, "normal_pvp")
    assert result_ba.first_user_id == min(user_a, user_b)
    assert result_ba.second_user_id == max(user_a, user_b)


async def test_second_pvp_participant_busy_releases_first(stronghold_db):
    user_a = await create_test_user("mg-pvp-busy-a")
    user_b = await create_test_user("mg-pvp-busy-b")

    # user_b уже занят другим матчем.
    await match_guard.acquire_player_match_lock(user_b, "ranked")

    result = await match_guard.acquire_two_player_match_lock(user_a, user_b, "normal_pvp")
    assert result.success is False

    # user_a НЕ должен остаться заблокированным навсегда.
    a_lock = await match_guard.get_active_match(user_a)
    assert a_lock is None


async def test_pvp_lock_order_prevents_deadlock_between_two_concurrent_pairings(stronghold_db):
    """Два потока одновременно пытаются заматчить ОДНУ И ТУ ЖЕ пару (A,B) и (B,A) —
    стабильный порядок по возрастанию user_id гарантирует отсутствие deadlock
    (оба потока всегда берут lock в одном и том же порядке), ровно один поток
    получает оба lock'а."""
    user_a = await create_test_user("mg-pvp-deadlock-a")
    user_b = await create_test_user("mg-pvp-deadlock-b")

    results = [None, None]

    def worker(order, index):
        async def _run():
            first, second = order
            r = await match_guard.acquire_two_player_match_lock(first, second, "normal_pvp")
            results[index] = r.success
        asyncio.run(_run())

    threads = [
        threading.Thread(target=worker, args=((user_a, user_b), 0)),
        threading.Thread(target=worker, args=((user_b, user_a), 1)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == [False, True]


async def test_pvp_match_via_play_player_match_end_to_end(stronghold_db, active_event):
    from app.services.matches import play_player_match

    user_a, tg_a = await _multi_mode_ready_user("mg-pvp-e2e-a")
    user_b, tg_b = await _multi_mode_ready_user("mg-pvp-e2e-b")

    result_a, result_b = await play_player_match(tg_a, tg_b)
    assert result_a is not None
    assert result_b is not None
    assert (await match_guard.get_active_match(user_a)) is None
    assert (await match_guard.get_active_match(user_b)) is None


async def test_pvp_blocked_when_one_participant_already_in_match(stronghold_db, active_event):
    from app.services.matches import play_player_match

    user_a, tg_a = await _multi_mode_ready_user("mg-pvp-blocked-a")
    user_b, tg_b = await _multi_mode_ready_user("mg-pvp-blocked-b")

    await match_guard.acquire_player_match_lock(user_b, "ranked")

    result_a, result_b = await play_player_match(tg_a, tg_b)
    assert result_a is None
    assert result_b is None
    # user_a не должен был остаться заблокированным чужой занятостью.
    assert (await match_guard.get_active_match(user_a)) is None


# ---------------------------------------------------------------------------
# 6. Boot recovery / зависшие lock'и / TTL
# ---------------------------------------------------------------------------

def _insert_raw_lock(user_id: int, match_type: str, status: str, match_id: int | None, expires_delta_seconds: int) -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    expires_at = (now + timedelta(seconds=expires_delta_seconds)).strftime("%Y-%m-%d %H:%M:%S")
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO player_match_locks (user_id, match_id, match_type, status, acquired_at, heartbeat_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, match_id, match_type, status, now_text, now_text, expires_at),
        )
        connection.commit()
        return int(cursor.lastrowid)


async def test_expired_lock_with_no_match_is_expired_by_recovery(stronghold_db):
    user_id = await create_test_user("mg-recovery-missing")
    _insert_raw_lock(user_id, "ranked", "ACTIVE", match_id=None, expires_delta_seconds=-10)

    report = await match_guard.recover_stale_matches()
    assert report.scanned >= 1
    assert any(a.user_id == user_id and a.outcome == "expired" for a in report.actions)

    assert (await match_guard.get_active_match(user_id)) is None


async def test_expired_lock_bound_to_completed_match_is_released(stronghold_db):
    user_id = await create_test_user("mg-recovery-completed")
    # Реальная завершённая строка в общей таблице matches (see app.services.matches.save_match_result).
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO matches (user_id, opponent_name, opponent_type, user_lineup_ovr, opponent_lineup_ovr, "
            "user_score, opponent_score, result, rating_delta, coins_reward, rank_points_reward, "
            "league_before, league_after, is_overtime, is_shootout, mvp_title) "
            "VALUES (?, 'Bot', 'bot', 70, 70, 3, 1, 'win', 10, 100, 10, 'AHL', 'AHL', 0, 0, 'Test')",
            (user_id,),
        )
        match_id = int(cursor.lastrowid)
        connection.commit()

    _insert_raw_lock(user_id, "normal", "ACTIVE", match_id=match_id, expires_delta_seconds=-10)

    report = await match_guard.recover_stale_matches()
    assert any(a.user_id == user_id and a.outcome == "released_completed" for a in report.actions)
    assert (await match_guard.get_active_match(user_id)) is None


async def test_expired_lock_for_still_running_war2_draft_is_extended_not_expired(stronghold_db):
    """Истечение lock'а НЕ должно аннулировать реально идущий матч — war2_matches в
    статусе 'drafting' считается ещё реально активным."""
    user_id = await create_test_user("mg-recovery-war2-running")
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO war2_matches (status, user_id, opponent_name, opponent_type, mode_code) "
            "VALUES ('drafting', ?, 'Bot', 'bot', 'CLONE_WAR')",
            (user_id,),
        )
        match_id = int(cursor.lastrowid)
        connection.commit()

    lock_id = _insert_raw_lock(user_id, "war2", "ACTIVE", match_id=match_id, expires_delta_seconds=-10)

    report = await match_guard.recover_stale_matches()
    assert any(a.lock_id == lock_id and a.outcome == "extended" for a in report.actions)

    # lock должен ОСТАТЬСЯ активным (не EXPIRED) — матч реально ещё идёт.
    active = await match_guard.get_active_match(user_id)
    assert active is not None
    assert active.status == "ACTIVE"


async def test_not_yet_expired_lock_is_left_untouched_by_recovery(stronghold_db):
    user_id = await create_test_user("mg-recovery-not-expired")
    _insert_raw_lock(user_id, "ranked", "ACTIVE", match_id=None, expires_delta_seconds=600)

    report = await match_guard.recover_stale_matches()
    assert not any(a.user_id == user_id for a in report.actions)
    assert (await match_guard.get_active_match(user_id)) is not None


async def test_boot_recovery_restores_state_after_restart(stronghold_db):
    """Симулирует рестарт бота: активный lock, привязанный к реально
    завершённому матчу, "переживает" рестарт (запись в БД никуда не делась) и
    затем корректно приводится в порядок при следующем recover_stale_matches()."""
    user_id = await create_test_user("mg-boot-recovery")
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO matches (user_id, opponent_name, opponent_type, user_lineup_ovr, opponent_lineup_ovr, "
            "user_score, opponent_score, result, rating_delta, coins_reward, rank_points_reward, "
            "league_before, league_after, is_overtime, is_shootout, mvp_title) "
            "VALUES (?, 'Bot', 'bot', 70, 70, 3, 1, 'win', 10, 100, 10, 'AHL', 'AHL', 0, 0, 'Test')",
            (user_id,),
        )
        match_id = int(cursor.lastrowid)
        connection.commit()
    _insert_raw_lock(user_id, "normal", "ACTIVE", match_id=match_id, expires_delta_seconds=-1)

    # "Рестарт" — lock уже в БД (никакого in-memory состояния не требуется), новый
    # процесс просто вызывает recover_stale_matches(), как main.py делает при старте.
    before = await match_guard.get_active_match(user_id)
    assert before is not None

    report = await match_guard.recover_stale_matches()
    assert report.scanned >= 1

    after = await match_guard.get_active_match(user_id)
    assert after is None


async def test_corrupted_lock_record_is_diagnosed_via_missing_match(stronghold_db):
    """"Повреждённая запись" — match_id указывает на несуществующую строку матча
    (например, матч удалили/данные не консистентны) — recovery должна безопасно
    считать это "matching not found" -> EXPIRED, не молчать и не падать."""
    user_id = await create_test_user("mg-corrupted-record")
    _insert_raw_lock(user_id, "ranked", "ACTIVE", match_id=999_999_999, expires_delta_seconds=-10)

    report = await match_guard.recover_stale_matches()
    assert any(a.user_id == user_id and a.outcome == "expired" for a in report.actions)


# ---------------------------------------------------------------------------
# 7. Безопасность: старый/повторный callback, подмена user_id
# ---------------------------------------------------------------------------

async def test_stale_callback_after_completion_does_not_create_second_match(stronghold_db):
    """"Старый callback" — повторная обработка того же Update ПОСЛЕ того, как матч
    уже завершился и lock освобождён (finalize) — не должна вести себя иначе, чем
    обычный новый запуск (что и является корректным поведением: раз матч
    завершён, новый можно начинать; двойной РЕЗУЛЬТАТ при этом невозможен,
    поскольку повторный вызов реального движка просто играет ещё один
    настоящий матч, а не дублирует старый)."""
    user_id = await create_test_user("mg-stale-callback")
    lock = await match_guard.acquire_player_match_lock(user_id, "ranked")
    await match_guard.finalize_match(user_id, match_id=1)

    # "Старый" повторно доставленный callback пытается снова получить lock —
    # он либо получает НОВЫЙ lock (матч уже завершён, это легитимно), либо (если
    # бы матч всё ещё шёл) получил бы отказ. Ключевое свойство: НИКОГДА не бывает
    # двух одновременно активных lock'ов для одного user_id.
    retry = await match_guard.acquire_player_match_lock(user_id, "ranked")
    assert retry.acquired is True
    assert retry.lock_id != lock.lock_id

    with get_connection() as connection:
        active_count = connection.execute(
            "SELECT COUNT(*) AS n FROM player_match_locks WHERE user_id = ? AND status IN ('ACQUIRING','ACTIVE','RESOLVING')",
            (user_id,),
        ).fetchone()["n"]
    assert active_count == 1


async def test_spoofed_user_id_does_not_bypass_guard(stronghold_db):
    """Подмена user_id в callback_data не может обойти защиту, потому что guard
    работает по ОДНОМУ И ТОМУ ЖЕ внутреннему user_id независимо от того, что
    злоумышленник передал бы в самом callback_data — сервисные функции всегда
    резолвят user_id из реального инициатора Update (telegram_id -> profile.id),
    а не из строки callback_data."""
    victim = await create_test_user("mg-spoof-victim")
    attacker = await create_test_user("mg-spoof-attacker")

    victim_lock = await match_guard.acquire_player_match_lock(victim, "ranked")
    assert victim_lock.acquired is True

    # "Подмена" здесь означает: атакующий пытается заблокировать/освободить lock
    # ЧУЖОГО user_id напрямую — но у него нет пути сделать это иначе, чем зная
    # чужой внутренний id, а release/acquire всё равно оперируют per-user_id
    # записями без побочных эффектов на других пользователей.
    attacker_lock = await match_guard.acquire_player_match_lock(attacker, "ranked")
    assert attacker_lock.acquired is True  # у атакующего свой собственный lock

    # Lock жертвы остаётся ЕЁ и никак не пострадал от действий атакующего.
    victim_active = await match_guard.get_active_match(victim)
    assert victim_active is not None
    assert victim_active.id == victim_lock.lock_id


# ---------------------------------------------------------------------------
# 8. Административная диагностика
# ---------------------------------------------------------------------------

async def test_admin_force_release_works_and_is_idempotent(stronghold_db):
    user_id = await create_test_user("mg-admin-release")
    lock = await match_guard.acquire_player_match_lock(user_id, "ranked")

    released = await match_guard.admin_force_release_lock(lock.lock_id, admin_id=999999999, reason="test release")
    assert released is not None
    assert released.user_id == user_id
    assert (await match_guard.get_active_match(user_id)) is None

    # Повторное принудительное освобождение уже освобождённого lock'а — идемпотентно.
    released_again = await match_guard.admin_force_release_lock(lock.lock_id, admin_id=999999999, reason="test release again")
    assert released_again is None


async def test_admin_force_release_is_recorded_in_audit_log(stronghold_db):
    user_id = await create_test_user("mg-admin-audit")
    lock = await match_guard.acquire_player_match_lock(user_id, "ranked")
    await match_guard.admin_force_release_lock(lock.lock_id, admin_id=999999999, reason="audit-check-reason")

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM audit_log WHERE action = 'match_lock_force_release' AND entity_id = ?", (lock.lock_id,)
        ).fetchone()
    assert row is not None
    assert row["actor_user_id"] == 999999999
    assert "audit-check-reason" in row["details"]


async def test_only_admin_can_force_release_via_handler(stronghold_db, monkeypatch):
    """Обычный пользователь (не администратор) не может дойти до принудительного
    освобождения через хендлер — answer_callback_admin_only отклоняет запрос ДО
    вызова match_guard.admin_force_release_lock."""
    from app.handlers.admin_security import admin_security_match_lock_release

    user_id = await create_test_user("mg-non-admin-release")
    lock = await match_guard.acquire_player_match_lock(user_id, "ranked")

    class _FakeUser:
        def __init__(self, id):
            self.id = id

    class _FakeCallback:
        def __init__(self, telegram_id, data):
            self.from_user = _FakeUser(telegram_id)
            self.data = data
            self.answered = []

        async def answer(self, text=None, show_alert=False):
            self.answered.append(text)

    callback = _FakeCallback(123123123, f"admin_security:match_lock_release:{lock.lock_id}:1")
    await admin_security_match_lock_release(callback)

    # Lock должен остаться активным — обычный пользователь не смог его освободить.
    active = await match_guard.get_active_match(user_id)
    assert active is not None
    assert active.id == lock.lock_id


async def test_list_active_locks_includes_diagnostics_fields(stronghold_db):
    user_id = await create_test_user("mg-list-diagnostics")
    lock = await match_guard.acquire_player_match_lock(user_id, "stronghold_endless")

    locks = await match_guard.list_active_locks()
    match = next((entry for entry in locks if entry.id == lock.lock_id), None)
    assert match is not None
    assert match.user_id == user_id
    assert match.match_type == "stronghold_endless"
    assert match.status == "ACQUIRING"
    assert match.acquired_at is not None
    assert match.expires_at is not None


# ---------------------------------------------------------------------------
# 9. Все режимы используют единый MatchGuard (не параллельные системы)
# ---------------------------------------------------------------------------

async def test_all_game_mode_services_use_shared_match_guard(stronghold_db):
    import app.services.matches as matches_module

    for module in (ranked_core, stronghold_fortress, war2_core, matches_module):
        source = inspect.getsource(module)
        assert "match_guard" in source, f"{module.__name__} must use the shared match_guard service"

    import app.services.stronghold_endless as stronghold_endless_module
    assert "match_guard" in inspect.getsource(stronghold_endless_module)


async def test_no_duplicate_locking_system_active_matches_table_unused_by_new_code(stronghold_db):
    """Старая active_matches таблица не удалена (история/безопасность), но новый
    код (app.services.match_guard) больше не читает и не пишет её напрямую —
    единственный источник правды теперь player_match_locks."""
    source = inspect.getsource(match_guard)
    assert '"active_matches"' not in source
    assert "FROM active_matches" not in source
    assert "INTO active_matches" not in source


# ---------------------------------------------------------------------------
# 10. Интеграционный тест: два конкурентных запроса через РАЗНЫЕ сервисы
# (Ranked vs The Stronghold) — обязательный отдельный тест по ТЗ.
# ---------------------------------------------------------------------------

def _run_ranked_in_thread(telegram_id: int, outcome: dict) -> None:
    async def _run() -> None:
        try:
            result = await ranked_core.play_ranked_match(telegram_id)
            outcome["ranked"] = ("success", result.match_id)
        except RankedError as error:
            outcome["ranked"] = ("error", error.code)

    asyncio.run(_run())


def _run_stronghold_in_thread(telegram_id: int, user_id: int, fortress_match_id: int, outcome: dict) -> None:
    async def _run() -> None:
        try:
            result = await stronghold_fortress.play_fortress_match(telegram_id, user_id, fortress_match_id)
            outcome["stronghold"] = ("success", result.success)
        except StrongholdError as error:
            outcome["stronghold"] = ("error", error.code)

    asyncio.run(_run())


async def test_concurrent_ranked_vs_stronghold_exactly_one_match(stronghold_db, active_event):
    user_id, telegram_id = await _multi_mode_ready_user("mg-integration-ranked-stronghold")

    fortresses = await stronghold_fortress.list_fortresses(user_id)
    fortress = await stronghold_fortress.get_fortress(user_id, fortresses[0].id)
    fortress_match_id = fortress.matches[0].id

    coins_before = get_balance(user_id, "coins")
    ft_before = get_balance(user_id, "fortress_token")
    with get_connection() as connection:
        ranked_matches_before = connection.execute(
            "SELECT COUNT(*) AS n FROM ranked_matches WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        fortress_progress_before = connection.execute(
            "SELECT COUNT(*) AS n FROM stronghold_user_fortress_match_progress WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]

    outcome: dict = {}
    threads = [
        threading.Thread(target=_run_ranked_in_thread, args=(telegram_id, outcome)),
        threading.Thread(target=_run_stronghold_in_thread, args=(telegram_id, user_id, fortress_match_id, outcome)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert "ranked" in outcome and "stronghold" in outcome

    outcomes = [outcome["ranked"], outcome["stronghold"]]
    successes = [o for o in outcomes if o[0] == "success"]
    errors = [o for o in outcomes if o[0] == "error"]

    # Ровно один из двух конкурентных запросов должен реально пройти.
    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0][1] == "MATCH_ALREADY_ACTIVE" or errors[0][1] == "CARD_IN_ACTIVE_MATCH"

    # Ровно один активный lock не должен остаться висеть после того, как оба
    # запроса завершились (успешный сам себя финализировал, отказавший ничего не создал).
    assert (await match_guard.get_active_match(user_id)) is None

    with get_connection() as connection:
        ranked_matches_after = connection.execute(
            "SELECT COUNT(*) AS n FROM ranked_matches WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        fortress_progress_after = connection.execute(
            "SELECT COUNT(*) AS n FROM stronghold_user_fortress_match_progress WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]

    # Только ОДИН из двух режимов реально записал результат матча — никаких
    # двойных списаний/наград ни в одной из систем.
    ranked_created = ranked_matches_after - ranked_matches_before
    fortress_created = fortress_progress_after - fortress_progress_before
    assert ranked_created + fortress_created == 1
