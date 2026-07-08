from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.daily_login import (
    build_admin_daily_main_keyboard,
    build_admin_day_cancel_keyboard,
    build_admin_day_keyboard,
    build_admin_day_pack_keyboard,
    build_daily_after_claim_keyboard,
    build_daily_user_keyboard,
)
from app.services.daily_login import (
    claim_daily,
    get_daily_status,
    get_ladder,
    list_packs_for_picker,
    reward_for_day,
    update_reward_field,
)
from app.services.community import get_user_id_by_telegram_id
from app.states.daily_login import DailyEditStates
from app.texts.daily_login import (
    ADMIN_DAILY_BUTTON_TEXT,
    ADMIN_DAILY_MAIN_TEXT,
    DAILY_BUTTON_TEXT,
    build_admin_daily_text,
    build_admin_day_text,
    build_daily_claim_text,
    build_daily_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


# ---------------------------------------------------------------------------
# Игрок
# ---------------------------------------------------------------------------

@router.message(F.text == DAILY_BUTTON_TEXT)
async def daily_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    # Админам эта же кнопка открывает редактор наград.
    if is_admin(message.from_user.id):
        await state.clear()
        await safe_delete_message(message)
        ladder = await get_ladder()
        await message.answer(build_admin_daily_text(ladder), reply_markup=build_admin_daily_main_keyboard(ladder))
        return

    await state.clear()
    await safe_delete_message(message)
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    if user_id is None:
        await message.answer("🏒 Открой игру через /start.")
        return
    status = await get_daily_status(user_id)
    await message.answer(build_daily_text(status), reply_markup=build_daily_user_keyboard(status.can_claim))


@router.callback_query(F.data == "daily:main")
async def daily_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    status = await get_daily_status(user_id)
    await edit_or_send(callback, build_daily_text(status), reply_markup=build_daily_user_keyboard(status.can_claim))
    await callback.answer()


@router.callback_query(F.data == "daily:claim")
async def daily_claim(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    result, error = await claim_daily(user_id)
    if result is None:
        if error == "already":
            status = await get_daily_status(user_id)
            await edit_or_send(callback, build_daily_text(status), reply_markup=build_daily_user_keyboard(status.can_claim))
            await callback.answer("Награда за сегодня уже получена", show_alert=True)
        else:
            await callback.answer("Награды пока не настроены", show_alert=True)
        return

    await edit_or_send(callback, build_daily_claim_text(result), reply_markup=build_daily_after_claim_keyboard())
    await callback.answer("Награда получена 🎉")


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

async def admin_guard(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def show_admin_day(callback: CallbackQuery, day: int) -> None:
    ladder = await get_ladder()
    reward = reward_for_day(ladder, day)
    if reward is None:
        await edit_or_send(callback, ADMIN_DAILY_MAIN_TEXT, reply_markup=build_admin_daily_main_keyboard(ladder))
        return
    await edit_or_send(callback, build_admin_day_text(reward), reply_markup=build_admin_day_keyboard(day, reward.pack_id is not None))


@router.callback_query(F.data == "admin_daily:main")
async def admin_daily_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    ladder = await get_ladder()
    await edit_or_send(callback, build_admin_daily_text(ladder), reply_markup=build_admin_daily_main_keyboard(ladder))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_daily:day:"))
async def admin_daily_day(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    raw = callback.data.split(":")[-1] if callback.data else ""
    day = int(raw) if raw.isdigit() else 0
    await show_admin_day(callback, day)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_daily:edit_coins:"))
async def admin_daily_edit_coins(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    day = int(raw) if raw.isdigit() else 0
    await state.clear()
    await state.set_state(DailyEditStates.waiting_for_coins)
    await state.update_data(day=day)
    await edit_or_send(callback, f"<b>🪙 День {day}</b>\n\nВведи количество Coins (0 — без монет).", reply_markup=build_admin_day_cancel_keyboard(day))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_daily:edit_rubles:"))
async def admin_daily_edit_rubles(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    day = int(raw) if raw.isdigit() else 0
    await state.clear()
    await state.set_state(DailyEditStates.waiting_for_rubles)
    await state.update_data(day=day)
    await edit_or_send(callback, f"<b>💵 День {day}</b>\n\nВведи количество Рублей (0 — без рублей).", reply_markup=build_admin_day_cancel_keyboard(day))
    await callback.answer()


@router.message(DailyEditStates.waiting_for_coins)
@router.message(DailyEditStates.waiting_for_rubles)
async def admin_daily_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    current_state = await state.get_state()
    data = await state.get_data()
    day = int(data.get("day", 0))
    field = "coins" if current_state == DailyEditStates.waiting_for_coins.state else "rubles"

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи целое число.", reply_markup=build_admin_day_cancel_keyboard(day))
        return

    ok, msg = await update_reward_field(day, field, int(raw))
    await state.clear()

    ladder = await get_ladder()
    reward = reward_for_day(ladder, day)
    if reward is not None:
        await message.answer(build_admin_day_text(reward), reply_markup=build_admin_day_keyboard(day, reward.pack_id is not None))
    if not ok:
        await message.answer(msg)


@router.callback_query(F.data.startswith("admin_daily:pack:"))
async def admin_daily_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    raw = callback.data.split(":")[-1] if callback.data else ""
    day = int(raw) if raw.isdigit() else 0
    packs = await list_packs_for_picker()
    if not packs:
        await callback.answer("Сначала создай паки", show_alert=True)
        return
    await edit_or_send(callback, f"<b>🎁 День {day}</b>\n\nВыбери пак для награды:", reply_markup=build_admin_day_pack_keyboard(day, packs))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_daily:set_pack:"))
async def admin_daily_set_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 4:
        await callback.answer()
        return
    day = int(parts[2]) if parts[2].isdigit() else 0
    pack_id = int(parts[3]) if parts[3].isdigit() else 0
    ok, msg = await update_reward_field(day, "pack_id", pack_id)
    await show_admin_day(callback, day)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data.startswith("admin_daily:clear_pack:"))
async def admin_daily_clear_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    day = int(raw) if raw.isdigit() else 0
    await update_reward_field(day, "pack_id", None)
    await show_admin_day(callback, day)
    await callback.answer("Пак убран")
