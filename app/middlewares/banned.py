from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.subscription import (
    SUBSCRIPTION_CHECK_CALLBACK,
    build_subscription_keyboard,
    build_subscription_text,
    get_start_banner_file,
    get_subscription_settings,
    is_user_subscribed,
    normalize_channel_id,
)
from app.services.users import is_player_banned
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


BANNED_PLAYER_TEXT = """
<b>🚫 Доступ ограничен</b>

Аккаунт временно заблокирован.

Если нужна помощь, обратись к администрации лиги.
""".strip()

BANNED_PLAYER_ALERT = "🚫 Доступ к аккаунту временно ограничен."


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

        # Технический перерыв теперь обрабатывается отдельным, более ранним
        # MaintenanceModeMiddleware (app/middlewares/maintenance.py) — этот Update
        # сюда вообще не доходит, пока технический перерыв включён и пользователь
        # не администратор. Раздельная проверка здесь больше не нужна.

        if await is_player_banned(telegram_user.id):
            if isinstance(event, Message):
                await safe_delete_message(event)
                await event.answer(BANNED_PLAYER_TEXT)
                return None

            if isinstance(event, CallbackQuery):
                await event.answer(BANNED_PLAYER_ALERT, show_alert=True)
                return None

            return None

        if isinstance(event, CallbackQuery) and str(event.data or "").startswith(SUBSCRIPTION_CHECK_CALLBACK):
            return await handler(event, data)

        subscription_settings = await get_subscription_settings()
        bot = data.get("bot")
        channel_is_configured = bool(normalize_channel_id(subscription_settings.channel_id))
        if subscription_settings.enabled and channel_is_configured and bot is not None and not await is_user_subscribed(bot, telegram_user.id):
            if isinstance(event, Message):
                await safe_delete_message(event)
                banner = get_start_banner_file(subscription_settings)
                text = build_subscription_text(subscription_settings)
                return_payload = None
                raw_text = (event.text or "").strip()
                if raw_text.startswith("/start "):
                    candidate = raw_text.split(maxsplit=1)[1].strip()
                    if len(candidate) <= 40 and all(ch.isalnum() or ch in "_-" for ch in candidate):
                        return_payload = candidate
                keyboard = build_subscription_keyboard(subscription_settings, return_payload=return_payload)

                if banner is not None:
                    await event.answer_photo(photo=banner, caption=text, reply_markup=keyboard)
                else:
                    await event.answer(text, reply_markup=keyboard)
                return None

            if isinstance(event, CallbackQuery):
                await event.answer("Сначала подпишись на канал лиги.", show_alert=True)
                return None

            return None

        return await handler(event, data)
