from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_chemistry import (
    CHEMISTRY_RULES_PER_PAGE,
    build_admin_chemistry_main_keyboard,
    build_bonus_ovr_keyboard,
    build_chemistry_cancel_keyboard,
    build_chemistry_delete_confirm_keyboard,
    build_chemistry_rule_profile_keyboard,
    build_chemistry_rules_keyboard,
    build_required_cards_keyboard,
    build_rule_type_keyboard,
)
from app.services.chemistry import (
    create_chemistry_rule,
    delete_chemistry_rule,
    get_chemistry_rule,
    get_chemistry_rules_page,
    toggle_chemistry_rule,
    update_chemistry_rule_field,
)
from app.states.admin_chemistry import ChemistryCreateStates, ChemistryEditStates, ChemistrySearchStates
from app.texts.admin_chemistry import (
    ADMIN_CHEMISTRY_TEXT,
    CHEMISTRY_CREATE_TYPE_TEXT,
    CHEMISTRY_CREATE_VALUE_TEXT,
    CHEMISTRY_DELETE_CONFIRM_TEXT,
    CHEMISTRY_SEARCH_TEXT,
    build_chemistry_rule_profile_text,
    build_chemistry_rules_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()
ADMIN_CHEMISTRY_BUTTON_TEXT = "🧪 Химия"


async def admin_only(message_or_callback: Message | CallbackQuery) -> bool:
    user = message_or_callback.from_user
    return bool(user and is_admin(user.id))


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


async def show_main(callback: CallbackQuery) -> None:
    await edit_or_send(callback, ADMIN_CHEMISTRY_TEXT, build_admin_chemistry_main_keyboard())


async def show_rule_profile(callback: CallbackQuery, rule_id: int, page: int = 1) -> None:
    rule = await get_chemistry_rule(rule_id)

    if rule is None:
        await callback.answer("Бонус не найден", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_chemistry_rule_profile_text(rule),
        build_chemistry_rule_profile_keyboard(rule, page=page),
    )


async def show_rules_page(callback: CallbackQuery, page: int = 1, query: str | None = None) -> None:
    rules_page = await get_chemistry_rules_page(
        page=page,
        per_page=CHEMISTRY_RULES_PER_PAGE,
        query=query,
    )
    await edit_or_send(
        callback,
        build_chemistry_rules_text(rules_page),
        build_chemistry_rules_keyboard(rules_page),
    )


@router.message(F.text == ADMIN_CHEMISTRY_BUTTON_TEXT)
async def admin_chemistry_button(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return

    await state.clear()
    await safe_delete_message(message)
    await message.answer(ADMIN_CHEMISTRY_TEXT, reply_markup=build_admin_chemistry_main_keyboard())


@router.callback_query(F.data == "chemistry:main")
async def chemistry_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    await show_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:list:"))
async def chemistry_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 1
    await show_rules_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:view:"))
async def chemistry_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    rule_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await show_rule_profile(callback, rule_id=rule_id, page=page)
    await callback.answer()


@router.callback_query(F.data == "chemistry:create")
async def chemistry_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    await edit_or_send(callback, CHEMISTRY_CREATE_TYPE_TEXT, build_rule_type_keyboard("chemistry:create_type"))
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:create_type:"))
async def chemistry_create_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    rule_type = callback.data.split(":")[-1] if callback.data else ""
    await state.update_data(rule_type=rule_type)
    await state.set_state(ChemistryCreateStates.waiting_for_value)
    await edit_or_send(callback, CHEMISTRY_CREATE_VALUE_TEXT, build_chemistry_cancel_keyboard())
    await callback.answer()


@router.message(ChemistryCreateStates.waiting_for_value)
async def chemistry_create_value(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return

    value = (message.text or "").strip()
    await safe_delete_message(message)
    await state.update_data(value=value)

    prompt_message_id = None
    data = await state.get_data()
    await message.answer(
        "<b>📌 Сколько карточек нужно для бонуса?</b>",
        reply_markup=build_required_cards_keyboard("chemistry:create_required"),
    )


@router.callback_query(F.data.startswith("chemistry:create_required:"))
async def chemistry_create_required(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    required_cards = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 3
    await state.update_data(required_cards=required_cards)
    await edit_or_send(callback, "<b>⭐ Какой бонус OVR дать составу?</b>", build_bonus_ovr_keyboard("chemistry:create_bonus"))
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:create_bonus:"))
async def chemistry_create_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    bonus_ovr = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 1
    data = await state.get_data()
    result = await create_chemistry_rule(
        rule_type=str(data.get("rule_type", "")),
        value=str(data.get("value", "")),
        required_cards=int(data.get("required_cards", 3)),
        bonus_ovr=bonus_ovr,
    )
    await state.clear()

    if not result.success or result.rule_id is None:
        await callback.answer(result.message, show_alert=True)
        await show_main(callback)
        return

    await show_rule_profile(callback, rule_id=result.rule_id)
    await callback.answer(result.message)


@router.callback_query(F.data == "chemistry:search")
async def chemistry_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.set_state(ChemistrySearchStates.waiting_for_query)
    await edit_or_send(callback, CHEMISTRY_SEARCH_TEXT, build_chemistry_cancel_keyboard())
    await callback.answer()


@router.message(ChemistrySearchStates.waiting_for_query)
async def chemistry_search_query(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return

    query = (message.text or "").strip()
    await safe_delete_message(message)
    await state.clear()
    rules_page = await get_chemistry_rules_page(page=1, per_page=CHEMISTRY_RULES_PER_PAGE, query=query)
    await message.answer(build_chemistry_rules_text(rules_page), reply_markup=build_chemistry_rules_keyboard(rules_page))


@router.callback_query(F.data.startswith("chemistry:edit_type:"))
async def chemistry_edit_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    await state.update_data(rule_id=rule_id, field="rule_type")
    await edit_or_send(callback, "<b>🏷 Выбери новый тип бонуса</b>", build_rule_type_keyboard("chemistry:set_type"))
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:set_type:"))
async def chemistry_set_type(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rule_id = int(data.get("rule_id", 0))
    rule_type = callback.data.split(":")[-1] if callback.data else ""
    result = await update_chemistry_rule_field(rule_id, "rule_type", rule_type)
    await state.clear()
    await show_rule_profile(callback, rule_id=rule_id)
    await callback.answer(result.message, show_alert=not result.success)


@router.callback_query(F.data.startswith("chemistry:edit_required:"))
async def chemistry_edit_required(callback: CallbackQuery, state: FSMContext) -> None:
    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    await state.update_data(rule_id=rule_id, field="required_cards")
    await edit_or_send(callback, "<b>📌 Сколько карточек нужно для бонуса?</b>", build_required_cards_keyboard("chemistry:set_required"))
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:set_required:"))
async def chemistry_set_required(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rule_id = int(data.get("rule_id", 0))
    required_cards = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 3
    result = await update_chemistry_rule_field(rule_id, "required_cards", required_cards)
    await state.clear()
    await show_rule_profile(callback, rule_id=rule_id)
    await callback.answer(result.message, show_alert=not result.success)


@router.callback_query(F.data.startswith("chemistry:edit_bonus:"))
async def chemistry_edit_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    await state.update_data(rule_id=rule_id, field="bonus_ovr")
    await edit_or_send(callback, "<b>⭐ Какой бонус OVR дать составу?</b>", build_bonus_ovr_keyboard("chemistry:set_bonus"))
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:set_bonus:"))
async def chemistry_set_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rule_id = int(data.get("rule_id", 0))
    bonus_ovr = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 1
    result = await update_chemistry_rule_field(rule_id, "bonus_ovr", bonus_ovr)
    await state.clear()
    await show_rule_profile(callback, rule_id=rule_id)
    await callback.answer(result.message, show_alert=not result.success)


@router.callback_query(F.data.startswith("chemistry:edit_value:"))
async def chemistry_edit_value(callback: CallbackQuery, state: FSMContext) -> None:
    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    await state.update_data(rule_id=rule_id, field="value")
    await state.set_state(ChemistryEditStates.waiting_for_value)
    await edit_or_send(callback, CHEMISTRY_CREATE_VALUE_TEXT, build_chemistry_cancel_keyboard())
    await callback.answer()


@router.message(ChemistryEditStates.waiting_for_value)
async def chemistry_edit_value_message(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return

    value = (message.text or "").strip()
    data = await state.get_data()
    rule_id = int(data.get("rule_id", 0))
    await safe_delete_message(message)
    result = await update_chemistry_rule_field(rule_id, "value", value)
    await state.clear()

    rule = await get_chemistry_rule(rule_id)
    if rule is None:
        await message.answer(result.message)
        return

    await message.answer(build_chemistry_rule_profile_text(rule), reply_markup=build_chemistry_rule_profile_keyboard(rule))


@router.callback_query(F.data.startswith("chemistry:toggle:"))
async def chemistry_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    result = await toggle_chemistry_rule(rule_id)
    await show_rule_profile(callback, rule_id=rule_id)
    await callback.answer(result.message, show_alert=not result.success)


@router.callback_query(F.data.startswith("chemistry:delete_confirm:"))
async def chemistry_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    await edit_or_send(callback, CHEMISTRY_DELETE_CONFIRM_TEXT, build_chemistry_delete_confirm_keyboard(rule_id))
    await callback.answer()


@router.callback_query(F.data.startswith("chemistry:delete:"))
async def chemistry_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    rule_id = int(callback.data.split(":")[-1]) if callback.data and callback.data.split(":")[-1].isdigit() else 0
    result = await delete_chemistry_rule(rule_id)
    await show_rules_page(callback, page=1)
    await callback.answer(result.message, show_alert=not result.success)


@router.callback_query(F.data == "chemistry:cancel")
async def chemistry_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return

    await state.clear()
    await show_main(callback)
    await callback.answer("Действие отменено")


@router.callback_query(F.data == "chemistry:page_info")
async def chemistry_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
