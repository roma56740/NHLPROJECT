from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.inline import (
    build_profile_edit_cancel_keyboard,
    build_profile_keyboard,
    build_profile_olympics_locked_keyboard,
    build_profile_settings_keyboard,
)
from app.services.users import (
    PlayerProfile,
    can_edit_team_profile,
    get_player_profile_by_telegram_id,
    toggle_player_cards_privacy,
    update_player_nickname,
    update_player_team_country,
    update_player_team_logo_path,
    update_player_team_name,
)
from app.states.profile import ProfileSettingsStates
from app.texts.profile import (
    EDIT_NICKNAME_TEXT,
    EDIT_TEAM_COUNTRY_TEXT,
    EDIT_TEAM_LOGO_TEXT,
    EDIT_TEAM_NAME_TEXT,
    OLYMPICS_LOCKED_TEXT,
    build_profile_settings_text,
    build_profile_text,
    validate_text_value,
)
from app.utils.messages import safe_delete_message


router = Router()

PROFILE_BUTTON_TEXT = "👤 Профиль"
TEAM_LOGOS_DIR = Path("assets/uploads/team_logos")


async def get_profile_or_notify(message: Message) -> PlayerProfile | None:
    if message.from_user is None:
        return None

    profile = await get_player_profile_by_telegram_id(message.from_user.id)

    if profile is None:
        await message.answer("🏒 Профиль пока не найден. Нажми /start, чтобы выйти на лёд.")
        return None

    return profile


async def get_profile_for_callback(callback: CallbackQuery) -> PlayerProfile | None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Профиль не найден")
        return None

    return profile


async def edit_callback_message(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await message.edit_text(text, reply_markup=reply_markup)


async def edit_state_message(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest:
            pass

    sent_message = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(chat_id=sent_message.chat.id, message_id=sent_message.message_id)


async def start_profile_edit(callback: CallbackQuery, state: FSMContext, text: str, next_state) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.clear()
    await state.set_state(next_state)
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)

    await message.edit_text(text, reply_markup=build_profile_edit_cancel_keyboard())
    await callback.answer()


async def require_olympics_team_profile(callback: CallbackQuery) -> PlayerProfile | None:
    profile = await get_profile_for_callback(callback)

    if profile is None:
        return None

    if can_edit_team_profile(profile):
        return profile

    await edit_callback_message(
        callback,
        OLYMPICS_LOCKED_TEXT,
        reply_markup=build_profile_olympics_locked_keyboard(),
    )
    await callback.answer()
    return None


async def save_team_logo(message: Message) -> str | None:
    if not message.photo or message.from_user is None:
        return None

    TEAM_LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"team_logo_{message.from_user.id}_{created_at}.jpg"
    file_path = TEAM_LOGOS_DIR / file_name

    await message.bot.download(message.photo[-1], destination=file_path)
    return file_path.as_posix()


@router.message(F.text == PROFILE_BUTTON_TEXT)
async def profile_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    profile = await get_profile_or_notify(message)

    if profile is None:
        return

    await safe_delete_message(message)
    await message.answer(
        build_profile_text(profile),
        reply_markup=build_profile_keyboard(),
    )


@router.callback_query(F.data == "profile:refresh")
async def refresh_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_profile_for_callback(callback)

    if profile is None:
        return

    await edit_callback_message(
        callback,
        build_profile_text(profile),
        reply_markup=build_profile_keyboard(),
    )
    await callback.answer("Профиль обновлён")


@router.callback_query(F.data == "profile:settings")
async def profile_settings(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_profile_for_callback(callback)

    if profile is None:
        return

    await edit_callback_message(
        callback,
        build_profile_settings_text(profile),
        reply_markup=build_profile_settings_keyboard(profile.privacy_public_cards),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:toggle_cards_privacy")
async def toggle_cards_privacy(callback: CallbackQuery) -> None:
    profile = await toggle_player_cards_privacy(callback.from_user.id)

    if profile is None:
        await callback.answer("Профиль не найден")
        return

    await edit_callback_message(
        callback,
        build_profile_settings_text(profile),
        reply_markup=build_profile_settings_keyboard(profile.privacy_public_cards),
    )
    await callback.answer("Настройки сохранены")


@router.callback_query(F.data == "profile:edit_nickname")
async def edit_nickname(callback: CallbackQuery, state: FSMContext) -> None:
    await start_profile_edit(
        callback,
        state,
        EDIT_NICKNAME_TEXT,
        ProfileSettingsStates.waiting_for_nickname,
    )


@router.callback_query(F.data == "profile:edit_team_name")
async def edit_team_name(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await require_olympics_team_profile(callback)

    if profile is None:
        return

    await start_profile_edit(
        callback,
        state,
        EDIT_TEAM_NAME_TEXT,
        ProfileSettingsStates.waiting_for_team_name,
    )


@router.callback_query(F.data == "profile:edit_team_country")
async def edit_team_country(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await require_olympics_team_profile(callback)

    if profile is None:
        return

    await start_profile_edit(
        callback,
        state,
        EDIT_TEAM_COUNTRY_TEXT,
        ProfileSettingsStates.waiting_for_team_country,
    )


@router.callback_query(F.data == "profile:edit_team_logo")
async def edit_team_logo(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await require_olympics_team_profile(callback)

    if profile is None:
        return

    await start_profile_edit(
        callback,
        state,
        EDIT_TEAM_LOGO_TEXT,
        ProfileSettingsStates.waiting_for_team_logo,
    )


@router.callback_query(F.data == "profile:cancel_edit")
async def cancel_profile_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_profile_for_callback(callback)

    if profile is None:
        return

    await edit_callback_message(
        callback,
        build_profile_settings_text(profile),
        reply_markup=build_profile_settings_keyboard(profile.privacy_public_cards),
    )
    await callback.answer("Отменено")


async def finish_profile_edit(message: Message, state: FSMContext, profile: PlayerProfile | None) -> None:
    if profile is None:
        await state.clear()
        await message.answer("🏒 Профиль пока не найден. Нажми /start, чтобы выйти на лёд.")
        return

    await edit_state_message(
        message,
        state,
        build_profile_settings_text(profile),
        reply_markup=build_profile_settings_keyboard(profile.privacy_public_cards),
    )
    await state.clear()


async def stop_team_edit_if_locked(message: Message, state: FSMContext) -> bool:
    if message.from_user is None:
        return True

    profile = await get_player_profile_by_telegram_id(message.from_user.id)

    if profile is None:
        await state.clear()
        await message.answer("🏒 Профиль пока не найден. Нажми /start, чтобы выйти на лёд.")
        return True

    if can_edit_team_profile(profile):
        return False

    await edit_state_message(
        message,
        state,
        OLYMPICS_LOCKED_TEXT,
        reply_markup=build_profile_olympics_locked_keyboard(),
    )
    await state.clear()
    return True


@router.message(ProfileSettingsStates.waiting_for_nickname)
async def save_nickname(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await safe_delete_message(message)

    if not message.text:
        await edit_state_message(
            message,
            state,
            "🏒 Отправь никнейм текстом одним сообщением.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    nickname = validate_text_value(message.text, min_length=2, max_length=24)

    if nickname is None:
        await edit_state_message(
            message,
            state,
            "🏒 Никнейм должен быть от 2 до 24 символов. Попробуй ещё раз.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    profile = await update_player_nickname(message.from_user.id, nickname)
    await finish_profile_edit(message, state, profile)


@router.message(ProfileSettingsStates.waiting_for_team_name)
async def save_team_name(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await safe_delete_message(message)

    if await stop_team_edit_if_locked(message, state):
        return

    if not message.text:
        await edit_state_message(
            message,
            state,
            "🏒 Отправь название команды текстом одним сообщением.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    team_name = validate_text_value(message.text, min_length=2, max_length=32)

    if team_name is None:
        await edit_state_message(
            message,
            state,
            "🏒 Название команды должно быть от 2 до 32 символов. Попробуй ещё раз.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    profile = await update_player_team_name(message.from_user.id, team_name)
    await finish_profile_edit(message, state, profile)


@router.message(ProfileSettingsStates.waiting_for_team_country)
async def save_team_country(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await safe_delete_message(message)

    if await stop_team_edit_if_locked(message, state):
        return

    if not message.text:
        await edit_state_message(
            message,
            state,
            "🌍 Отправь страну команды текстом одним сообщением.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    team_country = validate_text_value(message.text, min_length=2, max_length=32)

    if team_country is None:
        await edit_state_message(
            message,
            state,
            "🌍 Название страны должно быть от 2 до 32 символов. Попробуй ещё раз.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    profile = await update_player_team_country(message.from_user.id, team_country)
    await finish_profile_edit(message, state, profile)


@router.message(ProfileSettingsStates.waiting_for_team_logo)
async def save_team_logo_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await safe_delete_message(message)

    if await stop_team_edit_if_locked(message, state):
        return

    team_logo_path = await save_team_logo(message)

    if team_logo_path is None:
        await edit_state_message(
            message,
            state,
            "🖼 Отправь логотип изображением одним сообщением.",
            reply_markup=build_profile_edit_cancel_keyboard(),
        )
        return

    profile = await update_player_team_logo_path(message.from_user.id, team_logo_path)
    await finish_profile_edit(message, state, profile)
