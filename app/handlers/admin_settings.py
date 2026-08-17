from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_settings import build_admin_settings_cancel_keyboard, build_admin_settings_keyboard
from app.services.security import add_security_log
from app.services import maintenance
from app.services.settings import (
    get_all_settings,
    get_bool_setting,
    get_setting,
    set_setting_value,
)
from app.states.admin_settings import AdminSettingsStates
from app.texts.admin_settings import (
    ADMIN_SETTINGS_BAD_NUMBER_TEXT,
    ADMIN_SETTINGS_BAD_WAIT_TEXT,
    ADMIN_SETTINGS_MAIN_TEXT,
    ADMIN_SETTINGS_SAVED_TEXT,
    build_admin_setting_edit_text,
    build_admin_settings_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()
ADMIN_SETTINGS_BUTTON_TEXT = "⚙️ Настройки"
NUMBER_SETTINGS = {
    "win_coins_reward",
    "loss_coins_reward",
    "bot_handicap_extra",
    "matchmaking_min_wait_seconds",
    "matchmaking_max_wait_seconds",
    "start_coins",
    "start_energy",
    "start_rank_points",
    "free_card_cooldown_hours",
    "creator_weekly_rewards_interval_hours",
    "asset_warning_interval_hours",
    "pack_animation_step_delay_ms",
    "ranked_shootout_chance_percent",
    "creator_weekly_rewards_enabled",
    "asset_warning_enabled",
    "subscription_required_enabled",
}


async def answer_admin_only(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else None

    if is_admin(user_id):
        return True

    await message.answer("🏒 Раздел доступен только администрации лиги.")
    return False


async def answer_callback_admin_only(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True

    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def show_settings_message(message: Message) -> None:
    settings = await get_all_settings()
    await message.answer(
        build_admin_settings_text(settings),
        reply_markup=build_admin_settings_keyboard(),
    )


async def edit_settings_message(callback: CallbackQuery) -> None:
    settings = await get_all_settings()
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await message.edit_text(
        build_admin_settings_text(settings),
        reply_markup=build_admin_settings_keyboard(),
    )


@router.message(F.text == ADMIN_SETTINGS_BUTTON_TEXT)
async def admin_settings_button(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await state.clear()
    await safe_delete_message(message)
    await show_settings_message(message)


@router.callback_query(F.data == "admin_settings:main")
async def admin_settings_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await edit_settings_message(callback)
    await callback.answer()


@router.callback_query(F.data == "admin_settings:toggle_maintenance")
async def admin_settings_toggle_maintenance(callback: CallbackQuery) -> None:
    if not await answer_callback_admin_only(callback):
        return

    # Быстрый тумблер здесь переиспользует ПОЛНУЮ реализацию из app.services.maintenance
    # (та же, что у раздела "🛠 Технический перерыв" в админ-панели) — единая точка
    # правды для enabled_at/enabled_by/аудит-лога/инвалидации кэша, а не отдельная
    # параллельная запись в тот же game_settings.maintenance_mode ключ.
    status = await maintenance.get_status(use_cache=False)
    if status.enabled:
        await maintenance.disable(callback.from_user.id)
        is_enabled = False
    else:
        await maintenance.enable(callback.from_user.id)
        is_enabled = True
    await add_security_log(
        action="Настройка игры",
        details=f"Режим обслуживания {'включён' if is_enabled else 'выключен'} администратором {callback.from_user.id}",
        telegram_id=callback.from_user.id,
    )
    await edit_settings_message(callback)
    await callback.answer("🛠 Режим обслуживания обновлён")


@router.callback_query(F.data.startswith("admin_settings:edit:"))
async def admin_settings_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    key = callback.data.split(":")[-1] if callback.data else ""
    settings = await get_all_settings()
    setting = next((item for item in settings if item.key == key), None)

    if setting is None:
        await callback.answer("Настройка не найдена", show_alert=True)
        return

    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.set_state(AdminSettingsStates.waiting_for_value)
    await state.update_data(
        key=key,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await message.edit_text(
        build_admin_setting_edit_text(setting),
        reply_markup=build_admin_settings_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminSettingsStates.waiting_for_value)
async def admin_settings_save_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    data = await state.get_data()
    key = str(data.get("key") or "")
    value = (message.text or "").strip()
    chat_id = int(data.get("chat_id") or message.chat.id)
    message_id = int(data.get("message_id") or 0)

    await safe_delete_message(message)

    if key in NUMBER_SETTINGS:
        if not value.isdigit() or int(value) < 0:
            await message.bot.send_message(
                chat_id=chat_id,
                text=ADMIN_SETTINGS_BAD_NUMBER_TEXT,
                reply_markup=build_admin_settings_cancel_keyboard(),
            )
            return

    if key == "ranked_shootout_chance_percent" and int(value) > 100:
        await message.bot.send_message(
            chat_id=chat_id,
            text="Шанс буллитов должен быть от 0 до 100%.",
            reply_markup=build_admin_settings_cancel_keyboard(),
        )
        return

    if key == "matchmaking_min_wait_seconds":
        max_wait = int(await get_setting("matchmaking_max_wait_seconds", "110") or 110)
        if int(value) > max_wait:
            await message.bot.send_message(
                chat_id=chat_id,
                text=ADMIN_SETTINGS_BAD_WAIT_TEXT,
                reply_markup=build_admin_settings_cancel_keyboard(),
            )
            return

    if key == "matchmaking_max_wait_seconds":
        min_wait = int(await get_setting("matchmaking_min_wait_seconds", "90") or 90)
        if int(value) < min_wait:
            await message.bot.send_message(
                chat_id=chat_id,
                text=ADMIN_SETTINGS_BAD_WAIT_TEXT,
                reply_markup=build_admin_settings_cancel_keyboard(),
            )
            return

    await set_setting_value(key, value)
    await add_security_log(
        action="Настройка игры",
        details=f"{key}: {value}. Администратор {message.from_user.id if message.from_user else 0}",
        telegram_id=message.from_user.id if message.from_user else None,
    )
    await state.clear()

    settings = await get_all_settings()
    text = f"{ADMIN_SETTINGS_SAVED_TEXT}\n\n{build_admin_settings_text(settings)}"

    if message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_admin_settings_keyboard(),
            )
            return
        except Exception:
            pass

    await message.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=build_admin_settings_keyboard(),
    )
