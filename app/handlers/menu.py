from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.reply import (
    build_admin_main_keyboard,
    build_user_main_keyboard,
)
from app.services.currencies import format_currency_amount
from app.services.matches import get_match_main_info
from app.services.users import get_player_profile_by_telegram_id
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()

HOME_BUTTON_TEXT = "🏠 Главная"


def build_home_text(profile, match_info) -> str:
    """Компактная сводка: всё важное на одном экране, без лишних переходов."""
    from html import escape

    lines = [
        "🏒 <b>NHL Card Bot</b>",
        "",
        f"👤 <b>{escape(profile.nickname, quote=False)}</b> · {escape(profile.league, quote=False)}",
        f"⭐ Очки рейтинга: <b>{profile.rating_points}</b>",
        f"🎟 Hockey Pass: уровень <b>{profile.hockey_pass_level}</b>",
    ]

    if match_info is not None:
        if match_info.is_ready and match_info.lineup_ovr is not None:
            lines.append(f"🧩 Состав: OVR <b>{match_info.lineup_ovr}</b> · готов к матчу ✅")
        else:
            lines.append(
                f"🧩 Состав: заполнено {match_info.filled_count}/{match_info.total_slots} · нужно собрать 🧩"
            )

    if profile.balances:
        lines.append("")
        lines.append("💰 <b>Баланс</b>")
        for balance in profile.balances:
            lines.append(format_currency_amount(balance))

    lines.append("")
    lines.append("Выбери раздел на клавиатуре ниже 👇")
    return "\n".join(lines)


async def show_home(message: Message, telegram_id: int) -> None:
    if is_admin(telegram_id):
        await message.answer("🏠 Главное меню админ-панели.", reply_markup=build_admin_main_keyboard())
        return

    profile = await get_player_profile_by_telegram_id(telegram_id)
    if profile is None:
        await message.answer("🏒 Открой игру через /start.", reply_markup=build_user_main_keyboard())
        return

    match_info = await get_match_main_info(telegram_id)
    await message.answer(build_home_text(profile, match_info), reply_markup=build_user_main_keyboard())


@router.message(F.text == HOME_BUTTON_TEXT)
async def home_button(message: Message) -> None:
    if message.from_user is None:
        return
    await safe_delete_message(message)
    await show_home(message, message.from_user.id)


@router.callback_query(F.data == "menu:main")
async def back_to_main_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else None
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    chat_id = message.chat.id
    await safe_delete_callback_message(callback)

    if is_admin(user_id):
        await callback.bot.send_message(
            chat_id=chat_id,
            text="🏠 Главное меню админ-панели.",
            reply_markup=build_admin_main_keyboard(),
        )
    else:
        profile = await get_player_profile_by_telegram_id(user_id) if user_id else None
        if profile is None:
            await callback.bot.send_message(
                chat_id=chat_id,
                text="🏒 Главное меню.",
                reply_markup=build_user_main_keyboard(),
            )
        else:
            match_info = await get_match_main_info(user_id)
            await callback.bot.send_message(
                chat_id=chat_id,
                text=build_home_text(profile, match_info),
                reply_markup=build_user_main_keyboard(),
            )

    await callback.answer()
