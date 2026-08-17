"""Глобальный технический перерыв — ранний middleware (ТЗ "GLOBAL MAINTENANCE
MIDDLEWARE"). Регистрируется ПЕРВЫМ в app/handlers/__init__.py::setup_routers(),
раньше BannedPlayerMiddleware/AdminPermissionMiddleware/LastActiveMiddleware —
блокирует Update до того, как он доходит до любого игрового хендлера.

Админ-байпас переиспользует существующую систему прав (app.utils.users.is_admin
-> app.services.admin_permissions.is_panel_admin), отдельного списка админов не
заводится. Для CallbackQuery ВСЕГДА вызывается callback.answer() (даже при
cooldown) — иначе кнопка "крутится" бесконечно у заблокированного пользователя.

Cooldown ограничивает только ПОВТОРНУЮ отправку самого maintenance-сообщения
одному пользователю (защита от спама одинаковыми ответами) — Update при этом
ВСЕГДА блокируется (return None), cooldown никогда не пропускает его дальше к
игровым хендлерам.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject

from app.services import maintenance
from app.utils.users import is_admin

NOTICE_COOLDOWN_SECONDS = 3.0


class MaintenanceModeMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._last_notice_at: dict[int, float] = {}

    def _should_send_notice(self, telegram_user_id: int) -> bool:
        now = time.monotonic()
        last = self._last_notice_at.get(telegram_user_id)
        if last is not None and (now - last) < NOTICE_COOLDOWN_SECONDS:
            return False
        self._last_notice_at[telegram_user_id] = now
        return True

    async def _send_notice(self, event: Message | CallbackQuery, status: maintenance.MaintenanceStatus) -> None:
        target = event if isinstance(event, Message) else event.message
        if not isinstance(target, Message):
            return
        try:
            if status.photo_file_id:
                await target.answer_photo(photo=status.photo_file_id, caption=status.effective_text)
            else:
                await target.answer(status.effective_text)
        except Exception:
            # Технический перерыв не должен ронять обработку Update из-за
            # сетевой ошибки при отправке уведомления.
            pass

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")

        if telegram_user is None:
            return await handler(event, data)

        if is_admin(telegram_user.id):
            return await handler(event, data)

        status = await maintenance.get_status()
        if not status.enabled:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer()
            if self._should_send_notice(telegram_user.id):
                await self._send_notice(event, status)
            return None

        if isinstance(event, Message):
            if self._should_send_notice(telegram_user.id):
                await self._send_notice(event, status)
            return None

        if isinstance(event, InlineQuery):
            try:
                await event.answer(results=[], cache_time=1)
            except Exception:
                pass
            return None

        # Другие типы Update (могут запускать игровые действия) — блокируем без
        # уведомления, отправлять уведомление здесь физически некуда.
        return None
