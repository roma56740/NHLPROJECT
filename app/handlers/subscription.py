from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.handlers.start import send_start_screen
from app.services.subscription import (
    SUBSCRIPTION_CHECK_CALLBACK,
    build_subscription_debug_note,
    build_subscription_keyboard,
    build_subscription_text,
    get_start_banner_file,
    get_subscription_settings,
    is_user_subscribed,
)


router = Router()


@router.callback_query(F.data == SUBSCRIPTION_CHECK_CALLBACK)
async def subscription_check(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    settings = await get_subscription_settings()
    if not settings.enabled:
        await callback.answer("Проверка подписки выключена.")
        return

    is_subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)
    message = callback.message

    if is_subscribed:
        await callback.answer("✅ Подписка найдена")
        if isinstance(message, Message):
            try:
                await message.delete()
            except Exception:
                pass
            await send_start_screen(message, callback.from_user)
        return

    await callback.answer("Подписка пока не найдена", show_alert=True)

    if isinstance(message, Message):
        text = build_subscription_text(settings)
        keyboard = build_subscription_keyboard(settings)
        banner = get_start_banner_file(settings)
        debug_note = build_subscription_debug_note(settings)
        admin_hint = f"\n\n<i>{debug_note}</i>"

        try:
            if banner is not None:
                await message.edit_caption(caption=f"{text}{admin_hint}", reply_markup=keyboard)
            else:
                await message.edit_text(f"{text}{admin_hint}", reply_markup=keyboard)
        except Exception:
            pass
