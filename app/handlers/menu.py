from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReplyKeyboardRemove,
)

from app.keyboards.main_menu import (
    build_admin_all_keyboard,
    build_admin_content_keyboard,
    build_admin_economy_keyboard,
    build_admin_home_keyboard,
    build_admin_modes_keyboard,
    build_admin_players_keyboard,
    build_admin_system_keyboard,
    build_user_home_keyboard,
    build_user_more_keyboard,
    build_user_progress_keyboard,
)
from app.services.currencies import format_currency_amount
from app.services.matches import get_match_main_info
from app.services.render_theme import asset_absolute_path, get_render_theme_config
from app.services.renders import render_main_menu_image
from app.services import war2_cosmetics
from app.services.subscription import DEFAULT_START_BANNER_PATH, get_subscription_settings
from app.services.users import get_player_profile_by_telegram_id
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()
HOME_BUTTON_TEXT = "🏠 Главная"


async def get_home_banner_path() -> Path:
    settings = await get_subscription_settings()
    candidates = [
        Path(settings.start_banner_path),
        Path(DEFAULT_START_BANNER_PATH),
        Path("assets/visual/start_banner.jpeg"),
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    raise FileNotFoundError("Не найдено изображение главного меню: start_banner.jpeg")


async def get_home_media(user_id: int) -> tuple[Path, bool]:
    """Return (path, is_video) for the current user's main menu.

    Personal purchased/equipped background wins over the seasonal menu video/theme.
    """
    profile = await get_player_profile_by_telegram_id(user_id)
    if profile is None:
        return await get_home_banner_path(), False

    match_info = await get_match_main_info(user_id)
    personal_background = None
    try:
        personal_background = await war2_cosmetics.get_equipped_background_path(profile.id)
    except Exception:
        personal_background = None

    cfg = get_render_theme_config()
    if not personal_background:
        video_path = asset_absolute_path(cfg.menu_video_path)
        if video_path is not None:
            return video_path, True

    try:
        return render_main_menu_image(
            profile, match_info, user_id, background_override_path=personal_background
        ), False
    except Exception:
        return await get_home_banner_path(), False


async def remove_legacy_reply_keyboard(message: Message) -> None:
    """Убирает старую нижнюю ReplyKeyboard у клиентов после обновления.

    Telegram не позволяет одновременно передать ReplyKeyboardRemove и inline-кнопки,
    поэтому отправляется короткое служебное сообщение, которое сразу удаляется.
    """
    try:
        marker = await message.answer("Обновляю меню…", reply_markup=ReplyKeyboardRemove())
        await safe_delete_message(marker)
    except TelegramBadRequest:
        pass


def build_home_text(profile, match_info) -> str:
    from html import escape

    lines = [
        "🏒 <b>NHL Card Bot</b>",
        f"👤 <b>{escape(profile.nickname, quote=False)}</b> · {escape(profile.league, quote=False)}",
        f"⭐ Рейтинг: <b>{profile.rating_points}</b> · 🎟 Pass: <b>{profile.hockey_pass_level}</b>",
    ]

    if match_info is not None:
        if match_info.is_ready and match_info.lineup_ovr is not None:
            lines.append(f"🧩 Состав: OVR <b>{match_info.lineup_ovr}</b> · готов ✅")
        else:
            lines.append(f"🧩 Состав: {match_info.filled_count}/{match_info.total_slots} · не готов")

    if profile.balances:
        compact_balances = " · ".join(format_currency_amount(balance) for balance in list(profile.balances)[:3])
        if compact_balances:
            lines.append(f"💰 {compact_balances}")

    lines.append("")
    lines.append("Выбери действие кнопками под этой фотографией.")
    return "\n".join(lines)


def build_admin_home_text() -> str:
    return (
        "<b>🧭 Админ-центр</b>\n\n"
        "12 самых используемых действий вынесены на первый экран.\n"
        "Остальные инструменты находятся в разделе «☰ Все разделы»."
    )


async def _home_payload(user_id: int) -> tuple[str, object]:
    if is_admin(user_id):
        return build_admin_home_text(), build_admin_home_keyboard(user_id)

    profile = await get_player_profile_by_telegram_id(user_id)
    if profile is None:
        return "🏒 Открой игру через /start.", build_user_home_keyboard()

    match_info = await get_match_main_info(user_id)
    return build_home_text(profile, match_info), build_user_home_keyboard()


async def send_home_photo(message: Message, user_id: int, *, remove_reply_keyboard: bool = True) -> Message:
    if remove_reply_keyboard:
        await remove_legacy_reply_keyboard(message)
    caption, keyboard = await _home_payload(user_id)
    media_path, is_video = await get_home_media(user_id)
    if is_video:
        return await message.answer_video(
            video=FSInputFile(media_path), caption=caption, reply_markup=keyboard, supports_streaming=True
        )
    return await message.answer_photo(photo=FSInputFile(media_path), caption=caption, reply_markup=keyboard)


async def replace_with_menu_photo(
    callback: CallbackQuery,
    caption: str,
    keyboard,
) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    media_path, is_video = await get_home_media(callback.from_user.id)
    media = (
        InputMediaVideo(media=FSInputFile(media_path), caption=caption, parse_mode="HTML", supports_streaming=True)
        if is_video
        else InputMediaPhoto(media=FSInputFile(media_path), caption=caption, parse_mode="HTML")
    )
    try:
        if message.photo or message.video:
            await message.edit_media(media=media, reply_markup=keyboard)
        else:
            await message.delete()
            if is_video:
                await callback.bot.send_video(chat_id=message.chat.id, video=FSInputFile(media_path), caption=caption, reply_markup=keyboard, supports_streaming=True)
            else:
                await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(media_path), caption=caption, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            try:
                await message.edit_caption(caption=caption, reply_markup=keyboard)
            except Exception:
                pass
            return
        await safe_delete_callback_message(callback)
        if is_video:
            await callback.bot.send_video(chat_id=message.chat.id, video=FSInputFile(media_path), caption=caption, reply_markup=keyboard, supports_streaming=True)
        else:
            await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(media_path), caption=caption, reply_markup=keyboard)


async def show_home_callback(callback: CallbackQuery) -> None:
    caption, keyboard = await _home_payload(callback.from_user.id)
    await replace_with_menu_photo(callback, caption, keyboard)


@router.message(F.text == HOME_BUTTON_TEXT)
async def home_button(message: Message) -> None:
    if message.from_user is None:
        return
    await safe_delete_message(message)
    await send_home_photo(message, message.from_user.id)


@router.callback_query(F.data == "menu:main")
async def back_to_main_menu(callback: CallbackQuery) -> None:
    await show_home_callback(callback)
    await callback.answer()


@router.callback_query(F.data == "menu:user:progress")
async def user_progress_menu(callback: CallbackQuery) -> None:
    await replace_with_menu_photo(
        callback,
        "<b>🎯 Прогресс и награды</b>\n\nЗадания, пропуски, ежедневные награды, события и рейтинг.",
        build_user_progress_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:user:more")
async def user_more_menu(callback: CallbackQuery) -> None:
    await replace_with_menu_photo(
        callback,
        "<b>☰ Дополнительные разделы</b>\n\nПрофиль, сообщество, креаторы и инструкция для новичка.",
        build_user_more_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:user:help")
async def user_help_menu(callback: CallbackQuery) -> None:
    await replace_with_menu_photo(
        callback,
        "<b>ℹ️ Как начать играть</b>\n\n"
        "1️⃣ Забери бесплатную карту или открой пак.\n"
        "2️⃣ Открой «🧩 Состав» и заполни все позиции.\n"
        "3️⃣ Начни с обычного матча.\n"
        "4️⃣ Выполняй задания и забирай награды.\n\n"
        "Ranked доступен с AHL. Stronghold и Clan War используют отдельные правила.",
        build_user_more_keyboard(),
    )
    await callback.answer()


async def _admin_menu(callback: CallbackQuery, caption: str, keyboard) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    await replace_with_menu_photo(callback, caption, keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:admin:all")
async def admin_all_menu(callback: CallbackQuery) -> None:
    await _admin_menu(
        callback,
        "<b>☰ Все разделы админки</b>\n\nВыбери направление управления.",
        build_admin_all_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:admin:content")
async def admin_content_menu(callback: CallbackQuery) -> None:
    await _admin_menu(
        callback,
        "<b>🃏 Контент</b>\n\nКарты, паки, косметика, стартовый набор, дивизионы и химия.",
        build_admin_content_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:admin:modes")
async def admin_modes_menu(callback: CallbackQuery) -> None:
    await _admin_menu(
        callback,
        "<b>🎮 Режимы</b>\n\nRanked, Stronghold, Clan War, события, лиги и Чёрный рынок.",
        build_admin_modes_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:admin:players")
async def admin_players_menu(callback: CallbackQuery) -> None:
    await _admin_menu(
        callback,
        "<b>👥 Игроки</b>\n\nПользователи, кланы, обмены, безопасность и креаторы.",
        build_admin_players_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:admin:economy")
async def admin_economy_menu(callback: CallbackQuery) -> None:
    await _admin_menu(
        callback,
        "<b>💰 Экономика</b>\n\nВалюты, зарплаты, награды, задания, пропуски и промокоды.",
        build_admin_economy_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:admin:system")
async def admin_system_menu(callback: CallbackQuery) -> None:
    await _admin_menu(
        callback,
        "<b>🛡 Система</b>\n\nТехперерыв, активные матчи, настройки, сезоны и рассылка.",
        build_admin_system_keyboard(callback.from_user.id),
    )
