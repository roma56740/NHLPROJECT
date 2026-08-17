import pytest

from app.database.db import get_connection
from app.services import ranked_bot, war2_draft, war2_modes
from app.services.bot_card_policy import BOT_BLOCKED_COLLECTION_CODE, BOT_BLOCKED_COLLECTION_NAME
from app.services.renders import _all_bot_pool_rows, _bot_pool_rows_for_position
from tests.conftest import create_test_user


_SEQ = 0


def _collection_id(connection, *, code: str, name: str, is_exclusive: int = 0) -> int:
    row = connection.execute("SELECT id FROM collections WHERE code = ?", (code,)).fetchone()
    if row is not None:
        connection.execute(
            "UPDATE collections SET name = ?, active = 1, is_exclusive = ? WHERE id = ?",
            (name, is_exclusive, int(row["id"])),
        )
        return int(row["id"])
    cursor = connection.execute(
        "INSERT INTO collections (code, name, active, is_exclusive) VALUES (?, ?, 1, ?)",
        (code, name, is_exclusive),
    )
    return int(cursor.lastrowid)


def _insert_card(connection, *, collection_id: int, position: str, overall: int, prefix: str) -> int:
    global _SEQ
    _SEQ += 1
    key = f"{prefix}-{position.lower()}-{overall}-{_SEQ}"
    cursor = connection.execute(
        """
        INSERT INTO cards
            (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
        VALUES (?, ?, ?, ?, 'T', 'C', ?, 'Common', 'x.png', 100, 1)
        """,
        (key.title(), key, position, overall, collection_id),
    )
    return int(cursor.lastrowid)


def _seed_allowed_and_blocked_exact_ovr(overall: int = 95) -> None:
    with get_connection() as connection:
        allowed = _collection_id(connection, code="free-cards", name="Free Cards", is_exclusive=0)
        blocked = _collection_id(
            connection,
            code=BOT_BLOCKED_COLLECTION_CODE,
            name=BOT_BLOCKED_COLLECTION_NAME,
            is_exclusive=0,
        )
        for position, count in (("F", 5), ("D", 4), ("G", 3)):
            for _ in range(count):
                _insert_card(connection, collection_id=allowed, position=position, overall=overall, prefix="allowed")
                _insert_card(connection, collection_id=blocked, position=position, overall=overall, prefix="blocked")
        connection.commit()


async def test_ranked_bot_never_uses_team_of_admins(stronghold_db):
    _seed_allowed_and_blocked_exact_ovr(95)
    for _ in range(15):
        result = await ranked_bot.build_bot_lineup("OLYMPICS", target_ovr=95)
        assert result.overview.is_complete
        assert all(
            card is not None and card.collection_name.casefold() != BOT_BLOCKED_COLLECTION_NAME.casefold()
            for card in result.overview.slots.values()
        )


async def test_generic_bot_render_pool_excludes_team_of_admins(stronghold_db):
    _seed_allowed_and_blocked_exact_ovr(95)
    rows = _all_bot_pool_rows(95)
    assert rows
    assert all(row["collection_name"].casefold() != BOT_BLOCKED_COLLECTION_NAME.casefold() for row in rows)
    for position in ("F", "D", "G"):
        rows = _bot_pool_rows_for_position(95, position)
        assert rows
        assert all(row["collection_name"].casefold() != BOT_BLOCKED_COLLECTION_NAME.casefold() for row in rows)


async def test_war2_new_draft_pool_and_clone_war_exclude_team_of_admins(stronghold_db):
    with get_connection() as connection:
        allowed = _collection_id(connection, code="free-cards", name="Free Cards", is_exclusive=0)
        blocked = _collection_id(
            connection,
            code=BOT_BLOCKED_COLLECTION_CODE,
            name=BOT_BLOCKED_COLLECTION_NAME,
            is_exclusive=0,
        )
        for position, draft_count in (("F", 18), ("D", 9), ("G", 6)):
            for i in range(draft_count):
                _insert_card(connection, collection_id=allowed, position=position, overall=92 + (i % 8), prefix="war-allowed")
            for i in range(8):
                _insert_card(connection, collection_id=blocked, position=position, overall=99, prefix="war-blocked")
        connection.commit()

    user_id = await create_test_user("blocked-pool-test")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO war2_matches (user_id, opponent_name, opponent_type, mode_code)
            VALUES (?, 'BOT', 'bot', 'SALARY_WAR')
            """,
            (user_id,),
        )
        match_id = int(cursor.lastrowid)
        connection.commit()

    pool = await war2_draft.generate_draft_pool(match_id)
    assert len(pool) == 24
    assert all(row["collection_name"].casefold() != BOT_BLOCKED_COLLECTION_NAME.casefold() for row in pool)

    clone_ids = await war2_modes.build_clone_war_lineup()
    with get_connection() as connection:
        placeholders = ",".join("?" for _ in clone_ids)
        rows = connection.execute(
            f"""
            SELECT collections.name AS collection_name
            FROM cards JOIN collections ON collections.id = cards.collection_id
            WHERE cards.id IN ({placeholders})
            """,
            clone_ids,
        ).fetchall()
    assert len(rows) == 6
    assert all(row["collection_name"].casefold() != BOT_BLOCKED_COLLECTION_NAME.casefold() for row in rows)


async def test_war2_autopick_rejects_blocked_card_from_legacy_cached_pool(stronghold_db):
    """Even a pool cached before this fix cannot make the automated opponent pick it."""
    _seed_allowed_and_blocked_exact_ovr(95)
    # Policy helper is the final guard used by auto_pick_for_opponent for legacy pools.
    with get_connection() as connection:
        blocked = connection.execute(
            """
            SELECT cards.id, collections.name AS collection_name, collections.code AS collection_code
            FROM cards JOIN collections ON collections.id = cards.collection_id
            WHERE collections.code = ? LIMIT 1
            """,
            (BOT_BLOCKED_COLLECTION_CODE,),
        ).fetchone()
    from app.services.bot_card_policy import is_bot_card_allowed

    assert blocked is not None
    assert is_bot_card_allowed(blocked) is False
