"""Small server-side debounce for Telegram spam/autoclickers.

The authoritative economy/match code remains transactional.  This middleware only
prevents a client from hammering the same action hundreds of times while a normal
request is already being processed.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

_DEFAULT_COOLDOWN = 0.65
_EXPENSIVE_COOLDOWN = 2.0
_store: dict[tuple[int, str], float] = {}
_last_cleanup = 0.0


def _fingerprint(event: TelegramObject) -> tuple[int | None, str, float]:
    if isinstance(event, CallbackQuery):
        uid = event.from_user.id if event.from_user else None
        data = event.data or "callback"
        expensive_prefixes = (
            "release:buy_box:",
            "release:open_box:",
            "shop:buy:",
            "packs:open:",
            "match:",
            "matches:",
            "quick_match",
            "ranked:",
            "war2:",
        )
        is_expensive = any(data.startswith(prefix) for prefix in expensive_prefixes)
        # Expensive economy/match actions share one per-user bucket. An autoclicker
        # cannot bypass the limiter by alternating two different buy/open callbacks.
        key = "cb:expensive" if is_expensive else f"cb:{data}"
        cooldown = _EXPENSIVE_COOLDOWN if is_expensive else _DEFAULT_COOLDOWN
        return uid, key, cooldown

    if isinstance(event, Message):
        uid = event.from_user.id if event.from_user else None
        text = (event.text or "").strip()[:96]
        return uid, f"msg:{text}", _DEFAULT_COOLDOWN

    return None, "other", _DEFAULT_COOLDOWN


def _blocked(uid: int, key: str, cooldown: float) -> bool:
    global _last_cleanup
    now = time.monotonic()
    store_key = (uid, key)
    unlock_at = _store.get(store_key, 0.0)
    if unlock_at > now:
        return True
    _store[store_key] = now + cooldown

    # Keep the in-memory limiter bounded for long-running Railway workers.
    if len(_store) > 30_000 and now - _last_cleanup > 60:
        _last_cleanup = now
        expired = [item for item, until in _store.items() if until <= now]
        for item in expired[:20_000]:
            _store.pop(item, None)
    return False


class AntiAutoClickMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        uid, key, cooldown = _fingerprint(event)
        if uid is not None and _blocked(int(uid), key, cooldown):
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("Слишком часто. Подожди секунду.", show_alert=False)
                except Exception:
                    pass
            return None
        return await handler(event, data)
