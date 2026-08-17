from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database.db import get_connection
from app.services.creators import pay_weekly_rewards, run_creator_weekly_payout_if_due
from app.services.settings import set_setting_value
from tests.conftest import create_test_user


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.messages.append((chat_id, text))


def _creator_bank_coins(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS amount
            FROM creator_bank_items
            WHERE user_id = ? AND item_type = 'currency'
              AND currency_code = 'coins' AND status = 'available'
            """,
            (user_id,),
        ).fetchone()
    return int(row["amount"] or 0)


@pytest.mark.asyncio
async def test_weekly_payout_can_repeat_next_period_but_not_same_period(stronghold_db):
    user_id = await create_test_user("creator-weekly")
    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET is_creator = 1, creator_level = 1 WHERE id = ?",
            (user_id,),
        )
        connection.execute(
            "UPDATE creator_level_settings SET weekly_coins = 12345, weekly_elite_packs = 0, weekly_legendary_packs = 0 WHERE level = 1"
        )
        connection.commit()

    first = await pay_weekly_rewards("auto:test-week-1")
    assert first.creators_count == 1
    assert _creator_bank_coins(user_id) == 12345

    duplicate = await pay_weekly_rewards("auto:test-week-1")
    assert duplicate.creators_count == 0
    assert duplicate.skipped_already_paid == 1
    assert _creator_bank_coins(user_id) == 12345

    second = await pay_weekly_rewards("auto:test-week-2")
    assert second.creators_count == 1
    assert _creator_bank_coins(user_id) == 24690


@pytest.mark.asyncio
async def test_scheduler_pays_when_due_and_waits_until_next_interval(stronghold_db):
    user_id = await create_test_user("creator-scheduler")
    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET is_creator = 1, creator_level = 1 WHERE id = ?",
            (user_id,),
        )
        connection.execute(
            "UPDATE creator_level_settings SET weekly_coins = 500, weekly_elite_packs = 0, weekly_legendary_packs = 0 WHERE level = 1"
        )
        telegram_id = int(connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"])
        connection.commit()

    await set_setting_value("creator_weekly_rewards_enabled", "1")
    await set_setting_value("creator_weekly_rewards_interval_hours", "168")
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    await set_setting_value("creator_weekly_last_paid_at", (now - timedelta(hours=169)).isoformat())

    bot = _FakeBot()
    result = await run_creator_weekly_payout_if_due(bot, now=now)
    assert result is not None
    assert result.creators_count == 1
    assert _creator_bank_coins(user_id) == 500
    assert bot.messages and bot.messages[0][0] == telegram_id

    too_soon = await run_creator_weekly_payout_if_due(bot, now=now + timedelta(hours=1))
    assert too_soon is None
    assert _creator_bank_coins(user_id) == 500
