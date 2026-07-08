from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.clan_wars import (
    build_admin_arena_delete_confirm_keyboard,
    build_admin_arena_view_keyboard,
    build_admin_arenas_main_keyboard,
    build_arena_cancel_keyboard,
    build_arena_currency_keyboard,
)
from app.services.clan_wars import (
    create_arena,
    delete_arena,
    get_active_currency_choices,
    get_arena,
    get_arenas,
    release_arena,
    toggle_arena_active,
    update_arena_field,
)
from app.states.admin_arenas import ArenaCreateStates, ArenaEditStates
from app.texts.clan_wars import (
    ADMIN_ARENAS_MAIN_TEXT,
    ARENA_CREATE_CAPTURE_AMOUNT_TEXT,
    ARENA_CREATE_CAPTURE_CURRENCY_TEXT,
    ARENA_CREATE_DESCRIPTION_TEXT,
    ARENA_CREATE_INCOME_AMOUNT_TEXT,
    ARENA_CREATE_INCOME_CURRENCY_TEXT,
    ARENA_CREATE_NAME_TEXT,
    ARENA_CREATE_WINS_TEXT,
    ARENA_EDIT_CAPTURE_AMOUNT_TEXT,
    ARENA_EDIT_DESCRIPTION_TEXT,
    ARENA_EDIT_INCOME_AMOUNT_TEXT,
    ARENA_EDIT_NAME_TEXT,
    ARENA_EDIT_WINS_TEXT,
    build_arena_profile_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()

ADMIN_ARENAS_BUTTON_TEXT = "🏟 Арены"


async def admin_only_message(message: Message) -> bool:
    if is_admin(message.from_user.id if message.from_user else None):
        return True
    return False


async def admin_only_callback(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


async def show_arenas_main_message(message: Message) -> None:
    arenas = await get_arenas(include_inactive=True)
    await message.answer(ADMIN_ARENAS_MAIN_TEXT, reply_markup=build_admin_arenas_main_keyboard(arenas))


async def show_arenas_main_callback(callback: CallbackQuery) -> None:
    arenas = await get_arenas(include_inactive=True)
    await edit_or_send(callback, ADMIN_ARENAS_MAIN_TEXT, reply_markup=build_admin_arenas_main_keyboard(arenas))


async def show_arena_view(callback: CallbackQuery, arena_id: int) -> None:
    arena = await get_arena(arena_id)
    if arena is None:
        await show_arenas_main_callback(callback)
        return
    await edit_or_send(
        callback,
        build_arena_profile_text(arena, admin=True),
        reply_markup=build_admin_arena_view_keyboard(arena),
    )


def parse_arena_id(callback: CallbackQuery) -> int:
    raw = callback.data.split(":")[-1] if callback.data else ""
    return int(raw) if raw.isdigit() else 0


@router.message(F.text == ADMIN_ARENAS_BUTTON_TEXT)
async def admin_arenas_button(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await state.clear()
    await safe_delete_message(message)
    await show_arenas_main_message(message)


@router.callback_query(F.data == "admin_arenas:main")
async def admin_arenas_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await show_arenas_main_callback(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_arenas:view:"))
async def admin_arena_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await show_arena_view(callback, parse_arena_id(callback))
    await callback.answer()


# ---------------------------------------------------------------------------
# Создание арены (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_arenas:create")
async def arena_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await state.set_state(ArenaCreateStates.waiting_for_name)
    await edit_or_send(callback, ARENA_CREATE_NAME_TEXT, reply_markup=build_arena_cancel_keyboard())
    await callback.answer()


@router.message(ArenaCreateStates.waiting_for_name)
async def arena_create_name(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await safe_delete_message(message)
    await state.update_data(arena_name=message.text or "")
    await state.set_state(ArenaCreateStates.waiting_for_description)
    await message.answer(ARENA_CREATE_DESCRIPTION_TEXT, reply_markup=build_arena_cancel_keyboard())


@router.message(ArenaCreateStates.waiting_for_description)
async def arena_create_description(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await safe_delete_message(message)
    description = (message.text or "").strip()
    if description == "-":
        description = ""
    await state.update_data(arena_description=description)
    await state.set_state(ArenaCreateStates.waiting_for_wins)
    await message.answer(ARENA_CREATE_WINS_TEXT, reply_markup=build_arena_cancel_keyboard())


@router.message(ArenaCreateStates.waiting_for_wins)
async def arena_create_wins(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 500):
        await message.answer("Введи целое число от 1 до 500.", reply_markup=build_arena_cancel_keyboard())
        return
    await state.update_data(arena_wins=int(raw))
    await state.set_state(None)
    currencies = await get_active_currency_choices()
    await message.answer(
        ARENA_CREATE_INCOME_CURRENCY_TEXT,
        reply_markup=build_arena_currency_keyboard(currencies, "admin_arenas:create_income_currency"),
    )


@router.callback_query(F.data.startswith("admin_arenas:create_income_currency:"))
async def arena_create_income_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    code = callback.data.split(":")[-1] if callback.data else "none"
    if code == "none":
        await state.update_data(income_currency=None, income_amount=0)
        currencies = await get_active_currency_choices()
        await edit_or_send(
            callback,
            ARENA_CREATE_CAPTURE_CURRENCY_TEXT,
            reply_markup=build_arena_currency_keyboard(currencies, "admin_arenas:create_capture_currency"),
        )
        await callback.answer()
        return
    await state.update_data(income_currency=code)
    await state.set_state(ArenaCreateStates.waiting_for_income_amount)
    await edit_or_send(callback, ARENA_CREATE_INCOME_AMOUNT_TEXT, reply_markup=build_arena_cancel_keyboard())
    await callback.answer()


@router.message(ArenaCreateStates.waiting_for_income_amount)
async def arena_create_income_amount(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) > 1000000:
        await message.answer("Введи целое число от 0 до 1 000 000.", reply_markup=build_arena_cancel_keyboard())
        return
    await state.update_data(income_amount=int(raw))
    await state.set_state(None)
    currencies = await get_active_currency_choices()
    await message.answer(
        ARENA_CREATE_CAPTURE_CURRENCY_TEXT,
        reply_markup=build_arena_currency_keyboard(currencies, "admin_arenas:create_capture_currency"),
    )


@router.callback_query(F.data.startswith("admin_arenas:create_capture_currency:"))
async def arena_create_capture_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    code = callback.data.split(":")[-1] if callback.data else "none"
    if code == "none":
        await state.update_data(capture_currency=None, capture_amount=0)
        await finalize_arena_creation(callback, state)
        return
    await state.update_data(capture_currency=code)
    await state.set_state(ArenaCreateStates.waiting_for_capture_amount)
    await edit_or_send(callback, ARENA_CREATE_CAPTURE_AMOUNT_TEXT, reply_markup=build_arena_cancel_keyboard())
    await callback.answer()


@router.message(ArenaCreateStates.waiting_for_capture_amount)
async def arena_create_capture_amount(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) > 1000000:
        await message.answer("Введи целое число от 0 до 1 000 000.", reply_markup=build_arena_cancel_keyboard())
        return
    await state.update_data(capture_amount=int(raw))

    data = await state.get_data()
    await state.clear()
    result = await create_arena(
        name=data.get("arena_name", ""),
        description=data.get("arena_description", ""),
        capture_wins_required=int(data.get("arena_wins", 10)),
        income_currency_code=data.get("income_currency"),
        income_amount=int(data.get("income_amount", 0)),
        capture_currency_code=data.get("capture_currency"),
        capture_amount=int(data.get("capture_amount", 0)),
    )
    arenas = await get_arenas(include_inactive=True)
    await message.answer(
        f"<b>{result.title}</b>\n\n{result.description}",
        reply_markup=build_admin_arenas_main_keyboard(arenas),
    )


async def finalize_arena_creation(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    result = await create_arena(
        name=data.get("arena_name", ""),
        description=data.get("arena_description", ""),
        capture_wins_required=int(data.get("arena_wins", 10)),
        income_currency_code=data.get("income_currency"),
        income_amount=int(data.get("income_amount", 0)),
        capture_currency_code=data.get("capture_currency"),
        capture_amount=int(data.get("capture_amount", 0)),
    )
    arenas = await get_arenas(include_inactive=True)
    await edit_or_send(
        callback,
        f"<b>{result.title}</b>\n\n{result.description}",
        reply_markup=build_admin_arenas_main_keyboard(arenas),
    )
    await callback.answer(result.title, show_alert=not result.ok)


# ---------------------------------------------------------------------------
# Редактирование арены
# ---------------------------------------------------------------------------

EDIT_PROMPTS = {
    "edit_name": (ArenaEditStates.waiting_for_name, ARENA_EDIT_NAME_TEXT),
    "edit_description": (ArenaEditStates.waiting_for_description, ARENA_EDIT_DESCRIPTION_TEXT),
    "edit_wins": (ArenaEditStates.waiting_for_wins, ARENA_EDIT_WINS_TEXT),
    "edit_income": (ArenaEditStates.waiting_for_income_amount, ARENA_EDIT_INCOME_AMOUNT_TEXT),
    "edit_capture": (ArenaEditStates.waiting_for_capture_amount, ARENA_EDIT_CAPTURE_AMOUNT_TEXT),
}

EDIT_FIELDS = {
    ArenaEditStates.waiting_for_name.state: ("name", str),
    ArenaEditStates.waiting_for_description.state: ("description", str),
    ArenaEditStates.waiting_for_wins.state: ("capture_wins_required", int),
    ArenaEditStates.waiting_for_income_amount.state: ("income_amount", int),
    ArenaEditStates.waiting_for_capture_amount.state: ("capture_amount", int),
}


@router.callback_query(F.data.startswith("admin_arenas:edit_"))
async def arena_edit_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 3:
        await callback.answer()
        return
    action = parts[1]
    arena_id = int(parts[2]) if parts[2].isdigit() else 0
    prompt = EDIT_PROMPTS.get(action)
    if prompt is None:
        await callback.answer()
        return
    await state.clear()
    await state.update_data(arena_id=arena_id)
    await state.set_state(prompt[0])
    await edit_or_send(callback, prompt[1], reply_markup=build_arena_cancel_keyboard(arena_id))
    await callback.answer()


@router.message(ArenaEditStates.waiting_for_name)
@router.message(ArenaEditStates.waiting_for_description)
@router.message(ArenaEditStates.waiting_for_wins)
@router.message(ArenaEditStates.waiting_for_income_amount)
@router.message(ArenaEditStates.waiting_for_capture_amount)
async def arena_edit_value(message: Message, state: FSMContext) -> None:
    if not await admin_only_message(message):
        return
    await safe_delete_message(message)

    current_state = await state.get_state()
    field_info = EDIT_FIELDS.get(current_state or "")
    data = await state.get_data()
    arena_id = int(data.get("arena_id", 0))

    if field_info is None or arena_id <= 0:
        await state.clear()
        return

    field, caster = field_info
    raw = (message.text or "").strip()

    if field == "description" and raw == "-":
        raw = ""

    if caster is int:
        if not raw.isdigit():
            await message.answer("Введи целое число.", reply_markup=build_arena_cancel_keyboard(arena_id))
            return
        value: object = int(raw)
    else:
        value = raw

    result = await update_arena_field(arena_id, field, value)
    await state.clear()

    arena = await get_arena(arena_id)
    if arena is not None:
        await message.answer(
            build_arena_profile_text(arena, admin=True),
            reply_markup=build_admin_arena_view_keyboard(arena),
        )
    if not result.ok:
        await message.answer(f"<b>{result.title}</b>\n\n{result.description}")


@router.callback_query(F.data.startswith("admin_arenas:income_currency:"))
async def arena_income_currency_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.clear()
    arena_id = parse_arena_id(callback)
    currencies = await get_active_currency_choices()
    await edit_or_send(
        callback,
        "<b>💰 Выбери валюту ежедневного дохода</b>",
        reply_markup=build_arena_currency_keyboard(currencies, "admin_arenas:set_income_currency", arena_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_arenas:set_income_currency:"))
async def arena_set_income_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 4:
        await callback.answer()
        return
    code = parts[2]
    arena_id = int(parts[3]) if parts[3].isdigit() else 0
    result = await update_arena_field(arena_id, "income_currency_code", None if code == "none" else code)
    await show_arena_view(callback, arena_id)
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("admin_arenas:capture_currency:"))
async def arena_capture_currency_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.clear()
    arena_id = parse_arena_id(callback)
    currencies = await get_active_currency_choices()
    await edit_or_send(
        callback,
        "<b>🎁 Выбери валюту бонуса за захват</b>",
        reply_markup=build_arena_currency_keyboard(currencies, "admin_arenas:set_capture_currency", arena_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_arenas:set_capture_currency:"))
async def arena_set_capture_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 4:
        await callback.answer()
        return
    code = parts[2]
    arena_id = int(parts[3]) if parts[3].isdigit() else 0
    result = await update_arena_field(arena_id, "capture_currency_code", None if code == "none" else code)
    await show_arena_view(callback, arena_id)
    await callback.answer(result.title, show_alert=not result.ok)


# ---------------------------------------------------------------------------
# Переключение, освобождение, удаление
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin_arenas:toggle:"))
async def arena_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    arena_id = parse_arena_id(callback)
    result = await toggle_arena_active(arena_id)
    await show_arena_view(callback, arena_id)
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("admin_arenas:release:"))
async def arena_release(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    arena_id = parse_arena_id(callback)
    result = await release_arena(arena_id)
    await show_arena_view(callback, arena_id)
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("admin_arenas:delete_confirm:"))
async def arena_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    arena_id = parse_arena_id(callback)
    arena = await get_arena(arena_id)
    if arena is None:
        await show_arenas_main_callback(callback)
        await callback.answer()
        return
    await edit_or_send(
        callback,
        f"<b>🗑 Удалить арену?</b>\n\n🏟 <b>{escape(arena.name, quote=False)}</b> и все её атаки будут удалены безвозвратно.",
        reply_markup=build_admin_arena_delete_confirm_keyboard(arena_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_arenas:delete:"))
async def arena_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    arena_id = parse_arena_id(callback)
    result = await delete_arena(arena_id)
    await show_arenas_main_callback(callback)
    await callback.answer(result.title, show_alert=not result.ok)
