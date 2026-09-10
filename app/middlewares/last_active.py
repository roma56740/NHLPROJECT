"""Lightweight user activity tracking without blocking real handlers.

`last_active_at` is used for notification targeting, but it is not gameplay state.
Writing it on every Telegram message/callback created avoidable SQLite write-lock
contention.  We now update at most once per five minutes per user and schedule the
write in a worker thread without awaiting it in the request path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.db import get_connection

_LAST_ACTIVE_MIN_INTERVAL = timedelta(minutes=5)
_last_write_by_user: dict[int, datetime] = {}
_background_tasks: set[asyncio.Task[Any]] = set()


def _should_update(telegram_id: int, now: datetime) -> bool:
    last = _last_write_by_user.get(telegram_id)
    if last is not None and now - last < _LAST_ACTIVE_MIN_INTERVAL:
        return False
    _last_write_by_user[telegram_id] = now

    # Bound the process-local cache. This does not affect DB correctness; at worst
    # an evicted user gets one harmless extra activity write on their next action.
    if len(_last_write_by_user) > 20_000:
        cutoff = now - timedelta(hours=24)
        stale = [uid for uid, value in _last_write_by_user.items() if value < cutoff]
        for uid in stale[:10_000]:
            _last_write_by_user.pop(uid, None)
    return True


def _write_last_active(telegram_id: int) -> None:
    try:
        with get_connection() as connection:
            connection.execute(
                "UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (telegram_id,),
            )
            connection.commit()
    except Exception:
        # Activity tracking must never fail or delay a gameplay action.
        return


def _schedule_write(telegram_id: int) -> None:
    task = asyncio.create_task(asyncio.to_thread(_write_last_active, telegram_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class LastActiveMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")
        if telegram_user is not None:
            telegram_id = int(telegram_user.id)
            if _should_update(telegram_id, datetime.now(timezone.utc)):
                _schedule_write(telegram_id)

        return await handler(event, data)
