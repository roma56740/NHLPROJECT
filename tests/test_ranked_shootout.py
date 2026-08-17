"""Interactive Ranked shootout: pure rules and two-phase persistence."""

from __future__ import annotations

from app.database.db import get_connection
from app.services import ranked_core, ranked_shootout
from app.services.settings import set_setting_value
from tests.conftest import create_test_user, give_and_slot_card


async def _ready_ranked_player() -> tuple[int, int]:
    user_id = await create_test_user("ranked-shootout-user")
    with get_connection() as connection:
        telegram_id = int(
            connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"]
        )
        connection.execute("UPDATE users SET league = 'AHL' WHERE id = ?", (user_id,))
        collection_id = int(
            connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()["id"]
        )
        card_ids: dict[str, int] = {}
        for slot, position in (("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")):
            cursor = connection.execute(
                """
                INSERT INTO cards
                    (name, player_key, position, overall, team, country, collection_id,
                     rarity, image_path, salary, active)
                VALUES (?, ?, ?, 85, 'Test', 'Test', ?, 'Common', 'x.png', 1000, 1)
                """,
                (f"Shootout {slot}", f"shootout-{user_id}-{slot.lower()}", position, collection_id),
            )
            card_ids[slot] = int(cursor.lastrowid)
        connection.commit()
    for slot, card_id in card_ids.items():
        await give_and_slot_card(user_id, card_id, slot)
    return user_id, telegram_id


def test_ranked_shootout_attempt_rules() -> None:
    assert ranked_shootout.resolve_attempt(None, "TL").reason == "shooter_timeout"
    assert ranked_shootout.resolve_attempt(None, "TL").is_goal is False

    assert ranked_shootout.resolve_attempt("TR", None).reason == "goalie_timeout"
    assert ranked_shootout.resolve_attempt("TR", None).is_goal is True

    assert ranked_shootout.resolve_attempt("BL", "BL").reason == "save"
    assert ranked_shootout.resolve_attempt("BL", "BL").is_goal is False

    assert ranked_shootout.resolve_attempt("TL", "BR").reason == "goal"
    assert ranked_shootout.resolve_attempt("TL", "BR").is_goal is True


async def test_ranked_shootout_commits_only_after_minigame(stronghold_db) -> None:
    await ranked_core.start_ranked_season()
    await set_setting_value("ranked_shootout_chance_percent", "100")
    user_id, telegram_id = await _ready_ranked_player()

    pending = await ranked_core.play_ranked_match(telegram_id, interactive_shootout=True)
    assert pending.pending_shootout is True
    assert pending.user_score == pending.opponent_score

    with get_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) n FROM ranked_matches WHERE user_id = ?", (user_id,)
        ).fetchone()["n"] == 0
        assert connection.execute(
            "SELECT COUNT(*) n FROM player_match_locks WHERE user_id = ? AND status IN ('ACQUIRING','ACTIVE','RESOLVING')",
            (user_id,),
        ).fetchone()["n"] == 1

    completed = await ranked_core.finalize_ranked_shootout(
        pending,
        user_won=True,
        shootout_user_goals=2,
        shootout_opponent_goals=1,
        shootout_log=[
            {"round": 1, "phase": "user_shoots", "goal": True},
            {"round": 1, "phase": "user_defends", "goal": False},
        ],
    )
    assert completed.pending_shootout is False
    assert completed.result == "win"
    assert completed.user_score == completed.opponent_score + 1
    assert completed.shootout_user_goals == 2
    assert completed.shootout_opponent_goals == 1

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM ranked_matches WHERE id = ?", (completed.match_id,)
        ).fetchone()
        assert row["is_shootout"] == 1
        assert row["regulation_user_score"] == row["regulation_opponent_score"]
        assert row["shootout_user_goals"] == 2
        assert row["shootout_opponent_goals"] == 1
        assert "user_shoots" in row["shootout_log_json"]
        assert connection.execute(
            "SELECT COUNT(*) n FROM player_match_locks WHERE user_id = ? AND status IN ('ACQUIRING','ACTIVE','RESOLVING')",
            (user_id,),
        ).fetchone()["n"] == 0
