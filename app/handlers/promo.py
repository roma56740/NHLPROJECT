from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.promo import (
    build_admin_promo_create_cancel_keyboard,
    build_admin_promo_delete_keyboard,
    build_admin_promo_edit_cancel_keyboard,
    build_admin_promo_list_keyboard,
    build_admin_promo_pack_keyboard,
    build_admin_promo_view_keyboard,
    build_promo_after_redeem_keyboard,
    build_promo_cancel_keyboard,
)
from app.services.community import get_user_id_by_telegram_id
from app.services.promo import (
    create_promo,
    delete_promo,
    get_promo,
    list_packs_for_picker,
    list_promos,
    redeem_promo,
    toggle_promo_active,
    update_promo_field,
)
from app.states.promo import PromoCreateStates, PromoEditStates, PromoRedeemStates
from app.texts.promo import (
    ADMIN_PROMO_BUTTON_TEXT,
    ADMIN_PROMO_CREATE_CODE_TEXT,
    ADMIN_PROMO_CREATE_COINS_TEXT,
    ADMIN_PROMO_CREATE_MAX_TEXT,
    ADMIN_PROMO_CREATE_RUBLES_TEXT,
    PROMO_ENTER_TEXT,
    build_admin_promo_list_text,
    build_admin_promo_text,
    build_promo_success_text,
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
# Игрок: ввод промокода (вход из профиля -> callback profile:promo)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "promo:enter")
async def promo_enter(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PromoRedeemStates.waiting_for_code)
    await edit_or_send(callback, PROMO_ENTER_TEXT, reply_markup=build_promo_cancel_keyboard())
    await callback.answer()


@router.message(PromoRedeemStates.waiting_for_code)
async def promo_redeem_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await safe_delete_message(message)
    await state.clear()

    user_id = get_user_id_by_telegram_id(message.from_user.id)
    if user_id is None:
        await message.answer("🏒 Открой игру через /start.")
        return

    reward, status = await redeem_promo(user_id, message.text or "")
    if reward is None:
        await message.answer(f"❌ {status}", reply_markup=build_promo_after_redeem_keyboard())
        return

    await message.answer(build_promo_success_text(reward), reply_markup=build_promo_after_redeem_keyboard())


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

async def admin_guard_cb(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def admin_guard_msg(message: Message) -> bool:
    return bool(message.from_user and is_admin(message.from_user.id))


def parse_id(callback: CallbackQuery) -> int:
    raw = callback.data.split(":")[-1] if callback.data else ""
    return int(raw) if raw.isdigit() else 0


async def show_promo_list_msg(message: Message) -> None:
    promos = await list_promos()
    await message.answer(build_admin_promo_list_text(promos), reply_markup=build_admin_promo_list_keyboard(promos))


async def show_promo_list_cb(callback: CallbackQuery) -> None:
    promos = await list_promos()
    await edit_or_send(callback, build_admin_promo_list_text(promos), reply_markup=build_admin_promo_list_keyboard(promos))


async def show_promo_view(callback: CallbackQuery, promo_id: int) -> None:
    promo = await get_promo(promo_id)
    if promo is None:
        await show_promo_list_cb(callback)
        return
    await edit_or_send(callback, build_admin_promo_text(promo), reply_markup=build_admin_promo_view_keyboard(promo))


@router.message(F.text == ADMIN_PROMO_BUTTON_TEXT)
async def admin_promo_button(message: Message, state: FSMContext) -> None:
    if not await admin_guard_msg(message):
        return
    await state.clear()
    await safe_delete_message(message)
    await show_promo_list_msg(message)


@router.callback_query(F.data == "admin_promo:main")
async def admin_promo_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    await state.clear()
    await show_promo_list_cb(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo:view:"))
async def admin_promo_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    await state.clear()
    await show_promo_view(callback, parse_id(callback))
    await callback.answer()


# --- создание ---

@router.callback_query(F.data == "admin_promo:create")
async def admin_promo_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    await state.clear()
    await state.set_state(PromoCreateStates.waiting_for_code)
    await edit_or_send(callback, ADMIN_PROMO_CREATE_CODE_TEXT, reply_markup=build_admin_promo_create_cancel_keyboard())
    await callback.answer()


@router.message(PromoCreateStates.waiting_for_code)
async def promo_create_code(message: Message, state: FSMContext) -> None:
    if not await admin_guard_msg(message):
        return
    await safe_delete_message(message)
    await state.update_data(code=message.text or "")
    await state.set_state(PromoCreateStates.waiting_for_coins)
    await message.answer(ADMIN_PROMO_CREATE_COINS_TEXT, reply_markup=build_admin_promo_create_cancel_keyboard())


@router.message(PromoCreateStates.waiting_for_coins)
async def promo_create_coins(message: Message, state: FSMContext) -> None:
    if not await admin_guard_msg(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи целое число.", reply_markup=build_admin_promo_create_cancel_keyboard())
        return
    await state.update_data(coins=int(raw))
    await state.set_state(PromoCreateStates.waiting_for_rubles)
    await message.answer(ADMIN_PROMO_CREATE_RUBLES_TEXT, reply_markup=build_admin_promo_create_cancel_keyboard())


@router.message(PromoCreateStates.waiting_for_rubles)
async def promo_create_rubles(message: Message, state: FSMContext) -> None:
    if not await admin_guard_msg(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи целое число.", reply_markup=build_admin_promo_create_cancel_keyboard())
        return
    await state.update_data(rubles=int(raw))
    await state.set_state(PromoCreateStates.waiting_for_max)
    await message.answer(ADMIN_PROMO_CREATE_MAX_TEXT, reply_markup=build_admin_promo_create_cancel_keyboard())


@router.message(PromoCreateStates.waiting_for_max)
async def promo_create_max(message: Message, state: FSMContext) -> None:
    if not await admin_guard_msg(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи целое число.", reply_markup=build_admin_promo_create_cancel_keyboard())
        return

    data = await state.get_data()
    await state.clear()
    info, msg = await create_promo(
        code=data.get("code", ""),
        coins=int(data.get("coins", 0)),
        rubles=int(data.get("rubles", 0)),
        max_activations=int(raw),
        per_user_limit=1,
    )
    if info is None:
        promos = await list_promos()
        await message.answer(f"❌ {msg}", reply_markup=build_admin_promo_list_keyboard(promos))
        return
    await message.answer(build_admin_promo_text(info), reply_markup=build_admin_promo_view_keyboard(info))


# --- редактирование числовых полей и срока ---

EDIT_MAP = {
    "edit_coins": ("coins", "🪙 Введи количество Coins (0 — без монет)."),
    "edit_rubles": ("rubles", "💵 Введи количество Рублей (0 — без рублей)."),
    "edit_bp": ("bp_points", "🎟 Введи количество BP Points (0 — без BP)."),
    "edit_max": ("max_activations", "🔢 Общий лимит активаций (0 — без лимита)."),
    "edit_per_user": ("per_user_limit", "👤 Лимит на одного игрока (0 — без лимита)."),
    "edit_expires": ("expires_at", "📅 Дата окончания (ГГГГ-ММ-ДД) или «-», чтобы убрать срок."),
}


@router.callback_query(F.data.startswith("admin_promo:edit_"))
async def admin_promo_edit_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 3:
        await callback.answer()
        return
    action, promo_id = parts[1], (int(parts[2]) if parts[2].isdigit() else 0)
    if action not in EDIT_MAP:
        await callback.answer()
        return
    field, prompt = EDIT_MAP[action]
    await state.clear()
    await state.update_data(promo_id=promo_id, field=field)
    await state.set_state(PromoEditStates.waiting_for_value)
    await edit_or_send(callback, f"<b>🎫 Изменение</b>\n\n{prompt}", reply_markup=build_admin_promo_edit_cancel_keyboard(promo_id))
    await callback.answer()


@router.message(PromoEditStates.waiting_for_value)
async def admin_promo_edit_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_msg(message):
        return
    await safe_delete_message(message)
    data = await state.get_data()
    promo_id = int(data.get("promo_id", 0))
    field = data.get("field", "")
    raw = (message.text or "").strip()

    if field == "expires_at":
        value: object | None = None if raw == "-" else raw
    else:
        if not raw.isdigit():
            await message.answer("Введи целое число.", reply_markup=build_admin_promo_edit_cancel_keyboard(promo_id))
            return
        value = int(raw)

    ok, msg = await update_promo_field(promo_id, field, value)
    await state.clear()
    promo = await get_promo(promo_id)
    if promo is not None:
        await message.answer(build_admin_promo_text(promo), reply_markup=build_admin_promo_view_keyboard(promo))
    if not ok:
        await message.answer(f"❌ {msg}")


# --- пак ---

@router.callback_query(F.data.startswith("admin_promo:pack:"))
async def admin_promo_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    await state.clear()
    promo_id = parse_id(callback)
    packs = await list_packs_for_picker()
    if not packs:
        await callback.answer("Сначала создай паки", show_alert=True)
        return
    await edit_or_send(callback, "<b>🎁 Выбери пак-награду</b>", reply_markup=build_admin_promo_pack_keyboard(promo_id, packs))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo:set_pack:"))
async def admin_promo_set_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 4:
        await callback.answer()
        return
    promo_id = int(parts[2]) if parts[2].isdigit() else 0
    pack_id = int(parts[3]) if parts[3].isdigit() else 0
    ok, msg = await update_promo_field(promo_id, "pack_id", pack_id)
    await show_promo_view(callback, promo_id)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data.startswith("admin_promo:clear_pack:"))
async def admin_promo_clear_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    promo_id = parse_id(callback)
    await update_promo_field(promo_id, "pack_id", None)
    await show_promo_view(callback, promo_id)
    await callback.answer("Пак убран")


# --- вкл/выкл, удаление ---

@router.callback_query(F.data.startswith("admin_promo:toggle:"))
async def admin_promo_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    promo_id = parse_id(callback)
    ok, msg = await toggle_promo_active(promo_id)
    await show_promo_view(callback, promo_id)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data.startswith("admin_promo:delete_confirm:"))
async def admin_promo_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    promo_id = parse_id(callback)
    promo = await get_promo(promo_id)
    if promo is None:
        await show_promo_list_cb(callback)
        await callback.answer()
        return
    await edit_or_send(
        callback,
        f"<b>🗑 Удалить промокод {promo.code}?</b>\n\nЭто действие необратимо.",
        reply_markup=build_admin_promo_delete_keyboard(promo_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo:delete:"))
async def admin_promo_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_cb(callback):
        return
    promo_id = parse_id(callback)
    ok, msg = await delete_promo(promo_id)
    await show_promo_list_cb(callback)
    await callback.answer(msg, show_alert=not ok)
