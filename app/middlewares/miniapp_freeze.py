from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.keyboards.miniapp import build_miniapp_keyboard
from app.services.miniapp_runtime import miniapp_only_mode_enabled
from app.utils.users import is_admin


class MiniAppOnlyMiddleware(BaseMiddleware):
    """Freeze legacy player Telegram UI without deleting its handlers/services.

    Administrators keep full access to the old bot/admin panel. Ordinary players
    can use /start to receive the Mini App entry button. Stale old buttons and
    commands are intercepted here so legacy features remain reversible in code.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if is_admin(user_id) or not miniapp_only_mode_enabled():
            return await handler(event, data)

        if isinstance(event, Message):
            text = (event.text or "").strip().lower()
            if text == "/start" or text.startswith("/start "):
                return await handler(event, data)
            await event.answer(
                "NHL Cards теперь открывается через Mini App.",
                reply_markup=build_miniapp_keyboard(),
            )
            return None

        if isinstance(event, CallbackQuery):
            try:
                await event.answer("Этот раздел заморожен. Открой NHL Cards через Mini App.", show_alert=True)
            finally:
                message = event.message
                if isinstance(message, Message):
                    await message.answer(
                        "Открыть NHL Cards:",
                        reply_markup=build_miniapp_keyboard(),
                    )
            return None

        return await handler(event, data)
