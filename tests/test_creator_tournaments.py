"""Надёжность турнирной системы (creator_tournaments): полный прогон сетки, идемпотентность
завершения матчей, восстановление зависших матчей, ручной ввод результата, анти-дубликаты
финала/3-го места/наград. См. docs/TOURNAMENT_RELIABILITY_SPEC.md.
"""

import pytest

from app.database.db import get_connection
from app.services.creator_tournaments import (
    STATUS_FAILED,
    STATUS_PLAYING,
    STATUS_WAITING,
    _mark_match_failed,
    cancel_match,
    complete_match,
    create_pending_result,
    create_tournament,
    expire_tournament_matches,
    find_matches_needing_attention,
    force_simulate_match,
    get_active_pending_result,
    mark_ready_and_play,
    parse_score_text,
    register,
    restart_match,
    submit_manual_result,
)
from tests.conftest import create_test_user, give_and_slot_card


async def _build_lineup(user_id: int) -> None:
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])
        card_ids = {}
        for slot, position in [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]:
            cursor = connection.execute(
                "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES (?, ?, ?, 60, 'T', 'C', ?, 'Common', 'x.png', 100, 1)",
                (f"TC {slot} {user_id}", f"tc-{slot.lower()}-{user_id}", position, collection_id),
            )
            card_ids[slot] = int(cursor.lastrowid)
        connection.commit()
    for slot, card_id in card_ids.items():
        await give_and_slot_card(user_id, card_id, slot)


async def _make_creator_with_bank_item(user_id: int, qty: int = 10) -> int:
    with get_connection() as connection:
        connection.execute("UPDATE users SET is_creator=1 WHERE id=?", (user_id,))
        cursor = connection.execute(
            "INSERT INTO creator_bank_items (user_id, item_type, currency_code, quantity, value_per_unit, status) VALUES (?, 'currency', 'coins', ?, 100, 'available')",
            (user_id, qty),
        )
        connection.commit()
    return int(cursor.lastrowid)


async def _setup_tournament(capacity: int, tag: str = "") -> tuple[int, int, list[int]]:
    creator_id = await create_test_user(f"creator-{capacity}-{tag}")
    bank_item_id = await _make_creator_with_bank_item(creator_id)
    ok, msg, tid = await create_tournament(
        creator_id, f"Test Cup {capacity} {tag}", "desc", capacity, 60,
        [{"place_from": 1, "place_to": 1, "bank_item_id": bank_item_id, "quantity": 5}],
    )
    assert ok, msg
    participant_ids = []
    for i in range(capacity):
        uid = await create_test_user(f"player-{capacity}-{tag}-{i}")
        await _build_lineup(uid)
        participant_ids.append(uid)
    return creator_id, tid, participant_ids


async def _register_all(tid: int, participant_ids: list[int]) -> None:
    for uid in participant_ids:
        ok, msg, _started = await register(tid, uid)
        assert ok, msg


async def _pending_matches(tid: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM creator_tournament_matches WHERE tournament_id=? AND status IN ('pending','waiting') ORDER BY round_no,is_third_place,bracket_index",
            (tid,),
        ).fetchall()
    return [dict(r) for r in rows]


async def _play_all_pending(tid: int) -> None:
    for _ in range(50):  # safety bound, real brackets finish in a handful of passes
        matches = await _pending_matches(tid)
        if not matches:
            return
        progressed = False
        for m in matches:
            if not m["player1_user_id"] or not m["player2_user_id"]:
                continue
            ok1, msg1, _ = await mark_ready_and_play(m["id"], int(m["player1_user_id"]))
            ok2, msg2, _ = await mark_ready_and_play(m["id"], int(m["player2_user_id"]))
            assert ok1, msg1
            assert ok2, msg2
            progressed = True
        if not progressed:
            return
    raise AssertionError("bracket did not converge")


# ---------------------------------------------------------------------------
# Полный прогон сетки
# ---------------------------------------------------------------------------

async def test_full_bracket_4_players_creates_exactly_one_final_and_third_place(stronghold_db):
    creator_id, tid, players = await _setup_tournament(4, "bracket")
    await _register_all(tid, players)
    await _play_all_pending(tid)

    with get_connection() as connection:
        tournament = connection.execute("SELECT status FROM creator_tournaments WHERE id=?", (tid,)).fetchone()
        finals = connection.execute(
            "SELECT * FROM creator_tournament_matches WHERE tournament_id=? AND is_third_place=0 AND round_no=(SELECT MAX(round_no) FROM creator_tournament_matches WHERE tournament_id=? AND is_third_place=0)",
            (tid, tid),
        ).fetchall()
        thirds = connection.execute("SELECT * FROM creator_tournament_matches WHERE tournament_id=? AND is_third_place=1", (tid,)).fetchall()
        placements = connection.execute("SELECT user_id,final_place FROM creator_tournament_participants WHERE tournament_id=?", (tid,)).fetchall()

    assert tournament["status"] == "completed"
    assert len(finals) == 1
    assert finals[0]["status"] == "completed"
    assert len(thirds) == 1
    assert thirds[0]["status"] == "completed"
    places = {int(p["final_place"]) for p in placements if p["final_place"]}
    assert places == {1, 2, 3, 4}


async def test_full_bracket_reward_delivered_exactly_once(stronghold_db):
    creator_id, tid, players = await _setup_tournament(4, "reward")
    await _register_all(tid, players)
    await _play_all_pending(tid)

    with get_connection() as connection:
        deliveries = connection.execute("SELECT * FROM creator_tournament_reward_deliveries WHERE tournament_id=?", (tid,)).fetchall()
    assert len(deliveries) == 1  # только за 1-е место, единственный reward tier в setup


async def test_full_bracket_8_players(stronghold_db):
    creator_id, tid, players = await _setup_tournament(8, "eight")
    await _register_all(tid, players)
    await _play_all_pending(tid)

    with get_connection() as connection:
        tournament = connection.execute("SELECT status FROM creator_tournaments WHERE id=?", (tid,)).fetchone()
        match_count = connection.execute("SELECT COUNT(*) c FROM creator_tournament_matches WHERE tournament_id=?", (tid,)).fetchone()["c"]
        thirds = connection.execute("SELECT COUNT(*) c FROM creator_tournament_matches WHERE tournament_id=? AND is_third_place=1", (tid,)).fetchone()["c"]
    assert tournament["status"] == "completed"
    # 4 (QF) + 2 (SF) + 1 (final) + 1 (3rd place) = 8
    assert match_count == 8
    assert thirds == 1


# ---------------------------------------------------------------------------
# Идемпотентность
# ---------------------------------------------------------------------------

async def test_repeated_completion_of_completed_match_is_noop(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "idempotent")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]
    p1, p2 = int(matches[0]["player1_user_id"]), int(matches[0]["player2_user_id"])

    await complete_match(match_id, p1, 3, 1, "manual")
    with get_connection() as connection:
        after_first = dict(connection.execute("SELECT * FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone())
        deliveries_after_first = connection.execute("SELECT COUNT(*) c FROM creator_tournament_reward_deliveries WHERE tournament_id=?", (tid,)).fetchone()["c"]

    # повторное завершение с другим "результатом" не должно ничего изменить
    await complete_match(match_id, p2, 0, 5, "manual")
    with get_connection() as connection:
        after_second = dict(connection.execute("SELECT * FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone())
        deliveries_after_second = connection.execute("SELECT COUNT(*) c FROM creator_tournament_reward_deliveries WHERE tournament_id=?", (tid,)).fetchone()["c"]

    assert after_first["winner_user_id"] == after_second["winner_user_id"] == p1
    assert after_first["score1"] == after_second["score1"] == 3
    assert after_first["score2"] == after_second["score2"] == 1
    assert deliveries_after_first == deliveries_after_second  # для 2-участникового турнира финал сразу решает всё


async def test_repeated_button_press_returns_already_completed(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "double-press")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    ok1, msg1, res1 = await mark_ready_and_play(match_id, int(matches[0]["player1_user_id"]))
    ok2, msg2, res2 = await mark_ready_and_play(match_id, int(matches[0]["player2_user_id"]))
    assert ok1 and ok2

    # повторный клик по уже сыгранному матчу — статус больше не 'pending'/'waiting', недоступен
    ok3, msg3, res3 = await mark_ready_and_play(match_id, int(matches[0]["player1_user_id"]))
    assert ok3 is False
    assert res3 is None


# ---------------------------------------------------------------------------
# Восстановление зависших матчей
# ---------------------------------------------------------------------------

async def test_crash_during_match_marks_failed_not_stuck(stronghold_db, monkeypatch):
    creator_id, tid, players = await _setup_tournament(2, "crash")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated engine crash")

    monkeypatch.setattr("app.services.matches.play_player_match", _boom)

    ok1, _, _ = await mark_ready_and_play(match_id, int(matches[0]["player1_user_id"]))
    ok2, msg2, res2 = await mark_ready_and_play(match_id, int(matches[0]["player2_user_id"]))
    assert ok1 is True  # первый игрок просто отметился
    assert ok2 is False
    assert res2 is None

    with get_connection() as connection:
        row = connection.execute("SELECT status,error_message FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == STATUS_FAILED
    assert "simulated engine crash" in row["error_message"]


async def test_restart_match_resets_stuck_playing_match(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "restart")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    with get_connection() as connection:
        connection.execute(
            "UPDATE creator_tournament_matches SET status=?,player1_ready_at=CURRENT_TIMESTAMP,player2_ready_at=CURRENT_TIMESTAMP,started_at=CURRENT_TIMESTAMP,last_activity_at=datetime('now','-40 minutes') WHERE id=?",
            (STATUS_PLAYING, match_id),
        )
        connection.commit()

    ok, msg = await restart_match(match_id, creator_id)
    assert ok, msg

    with get_connection() as connection:
        row = connection.execute("SELECT * FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == STATUS_WAITING
    assert row["player1_ready_at"] is None
    assert row["player2_ready_at"] is None
    assert int(row["attempt_count"]) == 1

    # матч снова играбелен
    ok1, _, _ = await mark_ready_and_play(match_id, int(matches[0]["player1_user_id"]))
    ok2, _, res2 = await mark_ready_and_play(match_id, int(matches[0]["player2_user_id"]))
    assert ok1 and ok2 and res2 is not None


async def test_only_creator_can_restart_match(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "restart-perm")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]
    with get_connection() as connection:
        connection.execute("UPDATE creator_tournament_matches SET status=? WHERE id=?", (STATUS_PLAYING, match_id))
        connection.commit()

    ok, msg = await restart_match(match_id, players[0])  # не создатель турнира
    assert ok is False


async def test_force_simulate_completes_failed_match(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "force-sim")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    await _mark_match_failed(match_id, "test failure")
    with get_connection() as connection:
        row = connection.execute("SELECT status FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == STATUS_FAILED

    ok, msg, result = await force_simulate_match(match_id, creator_id)
    assert ok, msg
    assert result is not None
    with get_connection() as connection:
        row = connection.execute("SELECT status FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == "completed"


async def test_cancel_match_marks_cancelled(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "cancel")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    ok, msg = await cancel_match(match_id, creator_id, "test cancel")
    assert ok, msg
    with get_connection() as connection:
        row = connection.execute("SELECT status,error_message FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == "cancelled"
    assert row["error_message"] == "test cancel"


async def test_cannot_cancel_completed_match(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "cancel-completed")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]
    await complete_match(match_id, int(matches[0]["player1_user_id"]), 3, 0, "manual")

    ok, msg = await cancel_match(match_id, creator_id, "too late")
    assert ok is False
    assert "3:0" in msg


async def test_expire_marks_stale_playing_as_failed(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "stale")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]
    with get_connection() as connection:
        connection.execute(
            "UPDATE creator_tournament_matches SET status=?,last_activity_at=datetime('now','-45 minutes') WHERE id=?",
            (STATUS_PLAYING, match_id),
        )
        connection.commit()

    actions = await expire_tournament_matches()
    assert any(a.get("match_id") == match_id for a in actions)
    with get_connection() as connection:
        row = connection.execute("SELECT status,error_message FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == STATUS_FAILED
    assert row["error_message"]


async def test_find_matches_needing_attention_lists_stale_and_failed(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "attention")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]
    with get_connection() as connection:
        connection.execute(
            "UPDATE creator_tournament_matches SET status=?,last_activity_at=datetime('now','-20 minutes') WHERE id=?",
            (STATUS_PLAYING, match_id),
        )
        connection.commit()

    attention = await find_matches_needing_attention(tid)
    assert any(int(m["id"]) == match_id for m in attention)


# ---------------------------------------------------------------------------
# Ручной ввод результата
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("3:2", (3, 2)),
    ("3-2", (3, 2)),
    ("3 — 2", (3, 2)),
    ("3 2", (3, 2)),
    ("0:0", None),  # ничья запрещена
    ("-1:2", None),  # отрицательное
    ("3:2:1", None),  # больше двух чисел
    ("", None),  # пусто
    ("abc", None),  # не число
    ("99:2", None),  # выше лимита (MAX_SCORE=30)
])
def test_parse_score_text(text, expected):
    assert parse_score_text(text) == expected


async def test_submit_manual_result_completes_match(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "manual")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    ok, msg = await submit_manual_result(match_id, creator_id, 4, 1)
    assert ok, msg
    with get_connection() as connection:
        row = connection.execute("SELECT status,score1,score2,decided_by FROM creator_tournament_matches WHERE id=?", (match_id,)).fetchone()
    assert row["status"] == "completed"
    assert (row["score1"], row["score2"]) == (4, 1)
    assert row["decided_by"] == "creator_manual"


async def test_submit_manual_result_twice_returns_stored_score(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "manual-repeat")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    await submit_manual_result(match_id, creator_id, 4, 1)
    ok, msg = await submit_manual_result(match_id, creator_id, 2, 2)
    assert ok is False
    assert "4:1" in msg


async def test_only_creator_can_submit_manual_result(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "manual-perm")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    ok, msg = await submit_manual_result(match_id, players[0], 3, 1)
    assert ok is False


async def test_pending_result_survives_restart_simulation(stronghold_db):
    """Ожидание хранится в БД (creator_tournament_pending_results), не в aiogram FSM —
    "переживает restart" means любой новый запрос к БД видит его, что этот тест и проверяет
    (в реальном restart процесс перезапускается, но БД — персистентна)."""
    creator_id, tid, players = await _setup_tournament(2, "pending-restart")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    ok, msg, pending_id = await create_pending_result(creator_id, tid, match_id, chat_id=12345)
    assert ok, msg

    # "restart" — просто новый независимый запрос к персистентному хранилищу
    pending = await get_active_pending_result(creator_id)
    assert pending is not None
    assert int(pending["match_id"]) == match_id
    assert int(pending["id"]) == pending_id


async def test_cannot_create_pending_result_for_completed_match(stronghold_db):
    creator_id, tid, players = await _setup_tournament(2, "pending-completed")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]
    await complete_match(match_id, int(matches[0]["player1_user_id"]), 3, 0, "manual")

    ok, msg, pending_id = await create_pending_result(creator_id, tid, match_id, chat_id=1)
    assert ok is False
    assert pending_id is None
