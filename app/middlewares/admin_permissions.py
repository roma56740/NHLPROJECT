from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.admin_permissions import (
    get_permission_for_admin_text,
    get_permission_for_callback,
    get_permission_for_command,
    has_admin_permission,
    is_panel_admin,
)
from app.utils.messages import safe_delete_message

DENIED_TEXT = "🚫 У тебя нет доступа к этому разделу админки."
DENIED_ALERT = "🚫 Нет доступа к этому разделу админки."


class AdminPermissionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")
        if telegram_user is None:
            return await handler(event, data)

        permission: str | None = None
        if isinstance(event, Message):
            # Текстовые кнопки вроде «🎁 Паки» есть и у игроков, и у админов.
            # Поэтому ограничиваем их только для действующих админов с урезанным уровнем.
            if is_panel_admin(telegram_user.id):
                permission = get_permission_for_admin_text(event.text)
            permission = permission or get_permission_for_command(event.text)
        elif isinstance(event, CallbackQuery):
            permission = get_permission_for_callback(event.data)

        if permission is None:
            return await handler(event, data)

        if has_admin_permission(telegram_user.id, permission):
            return await handler(event, data)

        if isinstance(event, Message):
            await safe_delete_message(event)
            await event.answer(DENIED_TEXT)
            return None

        if isinstance(event, CallbackQuery):
            await event.answer(DENIED_ALERT, show_alert=True)
            return None

        return None
