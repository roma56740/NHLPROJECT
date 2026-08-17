from aiogram.types import User as TelegramUser

from app.database.db import get_connection
from app.middlewares.last_active import LastActiveMiddleware
from app.services.black_market_notifications import resolve_target_telegram_ids
from tests.conftest import create_test_user


async def test_last_active_middleware_updates_timestamp(stronghold_db):
    user_id = await create_test_user("bm-active-user")
    with get_connection() as connection:
        telegram_id = int(
            connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"]
        )
        before = connection.execute(
            "SELECT last_active_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()["last_active_at"]
    assert before is None

    middleware = LastActiveMiddleware()

    async def _handler(event, data):
        return "ok"

    telegram_user = TelegramUser(id=telegram_id, is_bot=False, first_name="test")
    result = await middleware(_handler, event=object(), data={"event_from_user": telegram_user})
    assert result == "ok"

    with get_connection() as connection:
        after = connection.execute(
            "SELECT last_active_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()["last_active_at"]
    assert after is not None


async def test_resolve_target_telegram_ids_none_mode_returns_empty(stronghold_db):
    await create_test_user("bm-notify-user")
    assert await resolve_target_telegram_ids("NONE", 7) == []


async def test_resolve_target_telegram_ids_all_mode_returns_everyone(stronghold_db):
    user1 = await create_test_user("bm-notify-all-1")
    user2 = await create_test_user("bm-notify-all-2")

    with get_connection() as connection:
        telegram_ids = {
            int(row["telegram_id"])
            for row in connection.execute(
                "SELECT telegram_id FROM users WHERE id IN (?, ?)", (user1, user2)
            ).fetchall()
        }

    result = set(await resolve_target_telegram_ids("ALL", 7))
    assert telegram_ids <= result


async def test_resolve_target_telegram_ids_active_n_days_filters(stronghold_db):
    active_user = await create_test_user("bm-notify-recent")
    stale_user = await create_test_user("bm-notify-stale")

    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET last_active_at = datetime('now', '-1 day') WHERE id = ?", (active_user,)
        )
        connection.execute(
            "UPDATE users SET last_active_at = datetime('now', '-30 days') WHERE id = ?", (stale_user,)
        )
        active_telegram_id = int(
            connection.execute("SELECT telegram_id FROM users WHERE id = ?", (active_user,)).fetchone()["telegram_id"]
        )
        stale_telegram_id = int(
            connection.execute("SELECT telegram_id FROM users WHERE id = ?", (stale_user,)).fetchone()["telegram_id"]
        )
        connection.commit()

    result = set(await resolve_target_telegram_ids("ACTIVE_N_DAYS", 7))
    assert active_telegram_id in result
    assert stale_telegram_id not in result
