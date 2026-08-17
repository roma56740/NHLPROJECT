from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.handlers.start import handle_start_payload, send_start_screen
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


@router.callback_query(F.data.startswith(SUBSCRIPTION_CHECK_CALLBACK))
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
            payload = None
            data = str(callback.data or "")
            prefix = f"{SUBSCRIPTION_CHECK_CALLBACK}:"
            if data.startswith(prefix):
                payload = data[len(prefix):].strip() or None
            if payload and await handle_start_payload(message, callback.from_user, payload):
                return
            await send_start_screen(message, callback.from_user)
        return

    await callback.answer("Подписка пока не найдена", show_alert=True)

    if isinstance(message, Message):
        text = build_subscription_text(settings)
        payload = None
        data = str(callback.data or "")
        prefix = f"{SUBSCRIPTION_CHECK_CALLBACK}:"
        if data.startswith(prefix):
            payload = data[len(prefix):].strip() or None
        keyboard = build_subscription_keyboard(settings, return_payload=payload)
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
