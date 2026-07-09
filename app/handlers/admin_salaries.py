from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_salaries import (
    SALARY_PER_PAGE,
    build_admin_salaries_main_keyboard,
    build_cancel_keyboard,
    build_collection_salary_mode_keyboard,
    build_salary_cards_keyboard,
    build_salary_collections_keyboard,
)
from app.services.admin_salaries import (
    get_salary_cards_page,
    get_salary_collections,
    get_salary_summary,
    set_all_zero_salary,
    set_collection_salary,
    set_salary_by_overall_range,
)
from app.states.admin_salaries import AdminSalaryStates
from app.texts.admin_salaries import (
    ADMIN_OVR_RANGE_TEXT,
    ADMIN_SALARY_VALUE_TEXT,
    ADMIN_SALARIES_BUTTON_TEXT,
    build_salary_cards_page_text,
    build_salary_collections_text,
    build_salary_summary_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()


async def admin_guard_message(message: Message) -> bool:
    if message.from_user and is_admin(message.from_user.id):
        return True
    await message.answer("🚫 Раздел доступен только администрации.")
    return False


async def admin_guard_callback(callback: CallbackQuery) -> bool:
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


async def show_main(target) -> None:
    summary = await get_salary_summary()
    text = build_salary_summary_text(summary)
    keyboard = build_admin_salaries_main_keyboard()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard)
    else:
        await edit_or_send(target, text, reply_markup=keyboard)


@router.message(F.text == ADMIN_SALARIES_BUTTON_TEXT)
async def salaries_button(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    await state.clear()
    await safe_delete_message(message)
    await show_main(message)


@router.callback_query(F.data == "admin_salaries:main")
async def salaries_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    await show_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_salaries:list:"))
async def salaries_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    _, _, mode, page_raw = callback.data.split(":")
    page = await get_salary_cards_page(mode=mode, page=int(page_raw), per_page=SALARY_PER_PAGE)
    await edit_or_send(callback, build_salary_cards_page_text(page), reply_markup=build_salary_cards_keyboard(page))
    await callback.answer()


@router.callback_query(F.data == "admin_salaries:collections")
async def salaries_collections(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    collections = await get_salary_collections()
    await edit_or_send(callback, build_salary_collections_text(collections), reply_markup=build_salary_collections_keyboard(collections))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_salaries:collection:"))
async def salaries_collection(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    collection_id = int(callback.data.split(":")[-1])
    await edit_or_send(callback, "<b>🗂 Зарплата коллекции</b>\n\nВыбери режим обновления.", reply_markup=build_collection_salary_mode_keyboard(collection_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_salaries:collection_mode:"))
async def salaries_collection_mode(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    parts = callback.data.split(":")
    collection_id = int(parts[2])
    mode = parts[3]
    await state.set_state(AdminSalaryStates.waiting_for_collection_salary)
    await state.update_data(collection_id=collection_id, mode=mode)
    await edit_or_send(callback, ADMIN_SALARY_VALUE_TEXT, reply_markup=build_cancel_keyboard())
    await callback.answer()


@router.message(AdminSalaryStates.waiting_for_collection_salary)
async def salaries_collection_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    data = await state.get_data()
    await safe_delete_message(message)
    ok, msg, changed = await set_collection_salary(int(data.get("collection_id") or 0), message.text or "", only_zero=(data.get("mode") == "zero"))
    await state.clear()
    await message.answer(f"{'✅' if ok else '⚠️'} {msg}\nИзменено карточек: <b>{changed}</b>", reply_markup=build_admin_salaries_main_keyboard())


@router.callback_query(F.data == "admin_salaries:set_zero")
async def salaries_set_zero(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.set_state(AdminSalaryStates.waiting_for_zero_salary)
    await edit_or_send(callback, f"{ADMIN_SALARY_VALUE_TEXT}\n\nБудут обновлены <b>только карточки с зарплатой 0</b>.", reply_markup=build_cancel_keyboard())
    await callback.answer()


@router.message(AdminSalaryStates.waiting_for_zero_salary)
async def salaries_zero_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    await safe_delete_message(message)
    ok, msg, changed = await set_all_zero_salary(message.text or "")
    await state.clear()
    await message.answer(f"{'✅' if ok else '⚠️'} {msg}\nИзменено карточек: <b>{changed}</b>", reply_markup=build_admin_salaries_main_keyboard())


@router.callback_query(F.data == "admin_salaries:ovr_range")
async def salaries_ovr_range(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.set_state(AdminSalaryStates.waiting_for_ovr_range)
    await edit_or_send(callback, ADMIN_OVR_RANGE_TEXT, reply_markup=build_cancel_keyboard())
    await callback.answer()


@router.message(AdminSalaryStates.waiting_for_ovr_range)
async def salaries_ovr_range_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip().replace("—", "-").replace("–", "-")
    parts = raw.split()
    if len(parts) < 2 or "-" not in parts[0]:
        await message.answer("⚠️ Формат: 90-93 5.5", reply_markup=build_cancel_keyboard())
        return
    try:
        min_ovr, max_ovr = [int(x) for x in parts[0].split("-", 1)]
    except ValueError:
        await message.answer("⚠️ Формат: 90-93 5.5", reply_markup=build_cancel_keyboard())
        return
    ok, msg, changed = await set_salary_by_overall_range(min_ovr, max_ovr, parts[1])
    await state.clear()
    await message.answer(f"{'✅' if ok else '⚠️'} {msg}\nИзменено карточек: <b>{changed}</b>", reply_markup=build_admin_salaries_main_keyboard())


@router.callback_query(F.data == "admin_salaries:noop")
async def salaries_noop(callback: CallbackQuery) -> None:
    await callback.answer()
