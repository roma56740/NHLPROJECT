from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.settings import is_maintenance_mode_enabled
from app.services.users import is_player_banned
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


BANNED_PLAYER_TEXT = """
<b>🚫 Доступ ограничен</b>

Аккаунт временно заблокирован.

Если нужна помощь, обратись к администрации лиги.
""".strip()

BANNED_PLAYER_ALERT = "🚫 Доступ к аккаунту временно ограничен."

MAINTENANCE_TEXT = """
<b>🛠 Лига на обновлении</b>

Сейчас идёт короткое обслуживание.
Скоро всё снова будет доступно.
""".strip()

MAINTENANCE_ALERT = "🛠 Сейчас идёт обслуживание лиги."


class BannedPlayerMiddleware(BaseMiddleware):
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

        if await is_maintenance_mode_enabled():
            if isinstance(event, Message):
                await safe_delete_message(event)
                await event.answer(MAINTENANCE_TEXT)
                return None

            if isinstance(event, CallbackQuery):
                await event.answer(MAINTENANCE_ALERT, show_alert=True)
                return None

            return None

        if not await is_player_banned(telegram_user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            await safe_delete_message(event)
            await event.answer(BANNED_PLAYER_TEXT)
            return None

        if isinstance(event, CallbackQuery):
            await event.answer(BANNED_PLAYER_ALERT, show_alert=True)
            return None

        return None
