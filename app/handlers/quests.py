from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.quests import (
    ADMIN_QUESTS_PER_PAGE,
    build_admin_quest_confirm_keyboard,
    build_admin_quest_delete_keyboard,
    build_admin_quest_edit_period_keyboard,
    build_admin_quest_edit_target_keyboard,
    build_admin_quest_period_keyboard,
    build_admin_quest_profile_keyboard,
    build_admin_quest_target_keyboard,
    build_admin_quests_cancel_keyboard,
    build_admin_quests_list_keyboard,
    build_admin_quests_main_keyboard,
    build_quest_list_keyboard,
    build_quests_main_keyboard,
)
from app.services.quests import (
    QuestDraft,
    claim_quest_reward,
    create_admin_quest,
    delete_admin_quest,
    get_admin_quest_profile,
    get_admin_quests_page,
    get_quest_main_info,
    get_user_quests,
    parse_int_value,
    toggle_admin_quest_active,
    update_admin_quest_choice_field,
    update_admin_quest_number_field,
    update_admin_quest_text_field,
    validate_positive_int,
    validate_quest_description,
    validate_quest_title,
)
from app.states.quests import QuestAdminStates
from app.texts.quests import (
    ADMIN_QUEST_BAD_DESCRIPTION_TEXT,
    ADMIN_QUEST_BAD_NUMBER_TEXT,
    ADMIN_QUEST_BAD_TITLE_TEXT,
    ADMIN_QUEST_BP_REWARD_TEXT,
    ADMIN_QUEST_COINS_REWARD_TEXT,
    ADMIN_QUEST_DESCRIPTION_TEXT,
    ADMIN_QUEST_NOT_FOUND_TEXT,
    ADMIN_QUEST_SAVED_TEXT,
    ADMIN_QUEST_TARGET_VALUE_TEXT,
    ADMIN_QUEST_TITLE_TEXT,
    ADMIN_QUEST_UPDATED_TEXT,
    ADMIN_QUESTS_MAIN_TEXT,
    ADMIN_QUESTS_SEARCH_TEXT,
    build_admin_delete_text,
    build_admin_edit_value_text,
    build_admin_quest_draft_text,
    build_admin_quest_profile_text,
    build_admin_quests_page_text,
    build_claim_result_text,
    build_quest_list_text,
    build_quests_main_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()

QUESTS_BUTTON_TEXT = "🎯 Задания"
ADMIN_QUEST_SEARCH_CACHE: dict[int, str] = {}
ACTIVE_QUEST_MESSAGES: dict[int, tuple[int, int]] = {}


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    try:
        if message.photo:
            await message.delete()
            sent = await callback.bot.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=reply_markup,
            )
        else:
            await message.edit_text(text, reply_markup=reply_markup)
            sent = message

        ACTIVE_QUEST_MESSAGES[callback.from_user.id] = (sent.chat.id, sent.message_id)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        sent = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
        )
        ACTIVE_QUEST_MESSAGES[callback.from_user.id] = (sent.chat.id, sent.message_id)


async def send_clean_message(message: Message, text: str, reply_markup=None) -> Message:
    old_message = ACTIVE_QUEST_MESSAGES.get(message.from_user.id if message.from_user else 0)

    if old_message:
        try:
            await message.bot.delete_message(chat_id=old_message[0], message_id=old_message[1])
        except TelegramBadRequest:
            pass

    sent = await message.answer(text, reply_markup=reply_markup)

    if message.from_user:
        ACTIVE_QUEST_MESSAGES[message.from_user.id] = (sent.chat.id, sent.message_id)

    return sent


async def send_prompt(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")

    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except TelegramBadRequest:
            pass

    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(prompt_message_id=sent.message_id)

    if message.from_user:
        ACTIVE_QUEST_MESSAGES[message.from_user.id] = (sent.chat.id, sent.message_id)


async def clear_prompt_from_state(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    chat_id: int | None = None

    if isinstance(event, Message):
        chat_id = event.chat.id
        bot = event.bot
    else:
        message = event.message
        bot = event.bot
        if isinstance(message, Message):
            chat_id = message.chat.id

    if prompt_message_id and chat_id is not None:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
        except TelegramBadRequest:
            pass


async def show_user_quests_main(callback: CallbackQuery) -> None:
    info = await get_quest_main_info(callback.from_user.id)

    if info is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_quests_main_text(info),
        reply_markup=build_quests_main_keyboard(),
    )


async def show_admin_quests_main(callback: CallbackQuery) -> None:
    await edit_or_send(
        callback,
        ADMIN_QUESTS_MAIN_TEXT,
        reply_markup=build_admin_quests_main_keyboard(),
    )


async def show_admin_quests_page(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    quest_page = await get_admin_quests_page(page=page, per_page=ADMIN_QUESTS_PER_PAGE, search=search)
    await edit_or_send(
        callback,
        build_admin_quests_page_text(quest_page),
        reply_markup=build_admin_quests_list_keyboard(quest_page),
    )


async def show_admin_quest_profile(callback: CallbackQuery, quest_id: int, page: int) -> None:
    profile = await get_admin_quest_profile(quest_id)

    if profile is None:
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    await edit_or_send(
        callback,
        build_admin_quest_profile_text(profile),
        reply_markup=build_admin_quest_profile_keyboard(profile, page),
    )


@router.message(F.text == QUESTS_BUTTON_TEXT)
async def quests_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await safe_delete_message(message)

    if message.from_user is None:
        return

    if is_admin(message.from_user.id):
        await send_clean_message(
            message,
            ADMIN_QUESTS_MAIN_TEXT,
            reply_markup=build_admin_quests_main_keyboard(),
        )
        return

    info = await get_quest_main_info(message.from_user.id)

    if info is None:
        await message.answer("🎯 Открой игру через /start.")
        return

    await send_clean_message(
        message,
        build_quests_main_text(info),
        reply_markup=build_quests_main_keyboard(),
    )


@router.callback_query(F.data == "quests:main")
async def quests_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_user_quests_main(callback)
    await callback.answer()


@router.callback_query(F.data.in_({"quests:daily", "quests:seasonal"}))
async def quests_list(callback: CallbackQuery) -> None:
    period_type = "daily" if callback.data == "quests:daily" else "seasonal"
    quest_list = await get_user_quests(callback.from_user.id, period_type)

    if quest_list is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_quest_list_text(quest_list),
        reply_markup=build_quest_list_keyboard(quest_list),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quests:claim:"))
async def quests_claim(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        progress_id = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Награда недоступна", show_alert=True)
        return

    result = await claim_quest_reward(callback.from_user.id, progress_id)

    if not result.success:
        await callback.answer(result.message, show_alert=True)
    else:
        await callback.answer("Награда получена!", show_alert=True)

    quest_list = await get_user_quests(callback.from_user.id, result.period_type)

    if quest_list is None:
        return

    await edit_or_send(
        callback,
        build_quest_list_text(quest_list),
        reply_markup=build_quest_list_keyboard(quest_list),
    )


@router.callback_query(F.data == "admin_quests:main")
async def admin_quests_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору.", show_alert=True)
        return

    await clear_prompt_from_state(callback, state)
    await state.clear()
    await show_admin_quests_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:list:"))
async def admin_quests_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору.", show_alert=True)
        return

    try:
        page = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 1

    await show_admin_quests_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data == "admin_quests:create")
async def admin_quests_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору.", show_alert=True)
        return

    await state.clear()
    await state.update_data(draft={})
    await edit_or_send(
        callback,
        "<b>➕ Новое задание</b>\n\nВыбери срок выполнения задания.",
        reply_markup=build_admin_quest_period_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:create_period:"))
async def admin_quests_create_period(callback: CallbackQuery, state: FSMContext) -> None:
    period_type = (callback.data or "").split(":")[-1]
    await state.update_data(draft={"period_type": period_type})
    await edit_or_send(
        callback,
        "<b>🎯 Цель задания</b>\n\nВыбери действие, за которое игрок будет получать прогресс.",
        reply_markup=build_admin_quest_target_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:create_target:"))
async def admin_quests_create_target(callback: CallbackQuery, state: FSMContext) -> None:
    target_type = (callback.data or "").split(":")[-1]
    data = await state.get_data()
    draft = data.get("draft", {})
    draft["target_type"] = target_type
    await state.update_data(draft=draft)
    await state.set_state(QuestAdminStates.create_title)
    await edit_or_send(
        callback,
        ADMIN_QUEST_TITLE_TEXT,
        reply_markup=build_admin_quests_cancel_keyboard(),
    )
    await callback.answer()


@router.message(QuestAdminStates.create_title)
async def admin_quests_create_title(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    title = (message.text or "").strip()

    if not validate_quest_title(title):
        await send_prompt(message, state, ADMIN_QUEST_BAD_TITLE_TEXT, reply_markup=build_admin_quests_cancel_keyboard())
        return

    data = await state.get_data()
    draft = data.get("draft", {})
    draft["title"] = title
    await state.update_data(draft=draft)
    await state.set_state(QuestAdminStates.create_description)
    await send_prompt(message, state, ADMIN_QUEST_DESCRIPTION_TEXT, reply_markup=build_admin_quests_cancel_keyboard())


@router.message(QuestAdminStates.create_description)
async def admin_quests_create_description(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    description = (message.text or "").strip()

    if description == "-":
        description = ""

    if not validate_quest_description(description):
        await send_prompt(message, state, ADMIN_QUEST_BAD_DESCRIPTION_TEXT, reply_markup=build_admin_quests_cancel_keyboard())
        return

    data = await state.get_data()
    draft = data.get("draft", {})
    draft["description"] = description
    await state.update_data(draft=draft)
    await state.set_state(QuestAdminStates.create_target_value)
    await send_prompt(message, state, ADMIN_QUEST_TARGET_VALUE_TEXT, reply_markup=build_admin_quests_cancel_keyboard())


@router.message(QuestAdminStates.create_target_value)
async def admin_quests_create_target_value(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    value = parse_int_value(message.text or "")

    if value is None or not validate_positive_int(value, 1, 100000):
        await send_prompt(message, state, ADMIN_QUEST_BAD_NUMBER_TEXT, reply_markup=build_admin_quests_cancel_keyboard())
        return

    data = await state.get_data()
    draft = data.get("draft", {})
    draft["target_value"] = value
    await state.update_data(draft=draft)
    await state.set_state(QuestAdminStates.create_bp_reward)
    await send_prompt(message, state, ADMIN_QUEST_BP_REWARD_TEXT, reply_markup=build_admin_quests_cancel_keyboard())


@router.message(QuestAdminStates.create_bp_reward)
async def admin_quests_create_bp_reward(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    value = parse_int_value(message.text or "")

    if value is None or not validate_positive_int(value, 0, 100000):
        await send_prompt(message, state, ADMIN_QUEST_BAD_NUMBER_TEXT, reply_markup=build_admin_quests_cancel_keyboard())
        return

    data = await state.get_data()
    draft = data.get("draft", {})
    draft["bp_reward"] = value
    await state.update_data(draft=draft)
    await state.set_state(QuestAdminStates.create_coins_reward)
    await send_prompt(message, state, ADMIN_QUEST_COINS_REWARD_TEXT, reply_markup=build_admin_quests_cancel_keyboard())


@router.message(QuestAdminStates.create_coins_reward)
async def admin_quests_create_coins_reward(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    value = parse_int_value(message.text or "")

    if value is None or not validate_positive_int(value, 0, 1000000000):
        await send_prompt(message, state, ADMIN_QUEST_BAD_NUMBER_TEXT, reply_markup=build_admin_quests_cancel_keyboard())
        return

    data = await state.get_data()
    draft_dict = data.get("draft", {})
    draft_dict["coins_reward"] = value
    draft = QuestDraft(**draft_dict)
    await state.update_data(draft=draft_dict)
    await state.set_state(None)
    await send_prompt(
        message,
        state,
        build_admin_quest_draft_text(draft),
        reply_markup=build_admin_quest_confirm_keyboard(),
    )


@router.callback_query(F.data == "admin_quests:create_confirm")
async def admin_quests_create_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft_dict = data.get("draft")

    if not draft_dict:
        await callback.answer("Черновик уже очищен.", show_alert=True)
        return

    quest_id = await create_admin_quest(QuestDraft(**draft_dict))
    await clear_prompt_from_state(callback, state)
    await state.clear()
    await callback.answer(ADMIN_QUEST_SAVED_TEXT, show_alert=True)
    await show_admin_quest_profile(callback, quest_id=quest_id, page=1)


@router.callback_query(F.data == "admin_quests:search")
async def admin_quests_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(QuestAdminStates.search)
    await edit_or_send(
        callback,
        ADMIN_QUESTS_SEARCH_TEXT,
        reply_markup=build_admin_quests_cancel_keyboard(),
    )
    await callback.answer()


@router.message(QuestAdminStates.search)
async def admin_quests_search_value(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    query = (message.text or "").strip()
    await clear_prompt_from_state(message, state)
    await state.clear()

    if not query:
        await send_prompt(message, state, ADMIN_QUESTS_SEARCH_TEXT, reply_markup=build_admin_quests_cancel_keyboard())
        await state.set_state(QuestAdminStates.search)
        return

    ADMIN_QUEST_SEARCH_CACHE[message.from_user.id] = query
    page = await get_admin_quests_page(1, ADMIN_QUESTS_PER_PAGE, query)
    await send_clean_message(
        message,
        build_admin_quests_page_text(page),
        reply_markup=build_admin_quests_list_keyboard(page),
    )


@router.callback_query(F.data.startswith("admin_quests:search_list:"))
async def admin_quests_search_list(callback: CallbackQuery) -> None:
    try:
        page = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 1

    query = ADMIN_QUEST_SEARCH_CACHE.get(callback.from_user.id, "")
    await show_admin_quests_page(callback, page=page, search=query)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:view:"))
async def admin_quests_view(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    await show_admin_quest_profile(callback, quest_id=quest_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:toggle:"))
async def admin_quests_toggle(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    result = await toggle_admin_quest_active(quest_id)
    await callback.answer(result.message, show_alert=True)
    await show_admin_quest_profile(callback, quest_id=quest_id, page=page)


@router.callback_query(F.data.startswith("admin_quests:edit_period:"))
async def admin_quests_edit_period(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    await edit_or_send(
        callback,
        "<b>📅 Тип задания</b>\n\nВыбери новый срок выполнения.",
        reply_markup=build_admin_quest_edit_period_keyboard(quest_id, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:set_period:"))
async def admin_quests_set_period(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        period_type = parts[3]
        page = int(parts[4])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    result = await update_admin_quest_choice_field(quest_id, "period_type", period_type)
    await callback.answer(result.message, show_alert=True)
    await show_admin_quest_profile(callback, quest_id=quest_id, page=page)


@router.callback_query(F.data.startswith("admin_quests:edit_target:"))
async def admin_quests_edit_target(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    await edit_or_send(
        callback,
        "<b>🎯 Цель задания</b>\n\nВыбери действие для прогресса.",
        reply_markup=build_admin_quest_edit_target_keyboard(quest_id, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:set_target:"))
async def admin_quests_set_target(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        target_type = parts[3]
        page = int(parts[4])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    result = await update_admin_quest_choice_field(quest_id, "target_type", target_type)
    await callback.answer(result.message, show_alert=True)
    await show_admin_quest_profile(callback, quest_id=quest_id, page=page)


@router.callback_query(F.data.startswith("admin_quests:edit:"))
async def admin_quests_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")

    try:
        field = parts[2]
        quest_id = int(parts[3])
        page = int(parts[4])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    await state.clear()
    await state.set_state(QuestAdminStates.edit_value)
    await state.update_data(edit_field=field, edit_quest_id=quest_id, edit_page=page)
    await edit_or_send(
        callback,
        build_admin_edit_value_text(field),
        reply_markup=build_admin_quests_cancel_keyboard(f"admin_quests:view:{quest_id}:{page}"),
    )
    await callback.answer()


@router.message(QuestAdminStates.edit_value)
async def admin_quests_edit_value(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    data = await state.get_data()
    field = data.get("edit_field")
    quest_id = int(data.get("edit_quest_id", 0))
    page = int(data.get("edit_page", 1))
    value_text = (message.text or "").strip()

    if field in {"title", "description"}:
        if field == "description" and value_text == "-":
            value_text = ""

        result = await update_admin_quest_text_field(quest_id, field, value_text)
    else:
        value = parse_int_value(value_text)

        if value is None:
            await send_prompt(message, state, ADMIN_QUEST_BAD_NUMBER_TEXT, reply_markup=build_admin_quests_cancel_keyboard(f"admin_quests:view:{quest_id}:{page}"))
            return

        result = await update_admin_quest_number_field(quest_id, field, value)

    if not result.success:
        await send_prompt(message, state, result.message, reply_markup=build_admin_quests_cancel_keyboard(f"admin_quests:view:{quest_id}:{page}"))
        return

    await clear_prompt_from_state(message, state)
    await state.clear()
    profile = await get_admin_quest_profile(quest_id)

    if profile is None:
        await send_clean_message(message, ADMIN_QUEST_NOT_FOUND_TEXT, reply_markup=build_admin_quests_main_keyboard())
        return

    await send_clean_message(
        message,
        build_admin_quest_profile_text(profile),
        reply_markup=build_admin_quest_profile_keyboard(profile, page),
    )


@router.callback_query(F.data.startswith("admin_quests:delete_ask:"))
async def admin_quests_delete_ask(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    profile = await get_admin_quest_profile(quest_id)

    if profile is None:
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    await edit_or_send(
        callback,
        build_admin_delete_text(profile),
        reply_markup=build_admin_quest_delete_keyboard(quest_id, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_quests:delete:"))
async def admin_quests_delete(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")

    try:
        quest_id = int(parts[2])
        page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer(ADMIN_QUEST_NOT_FOUND_TEXT, show_alert=True)
        return

    result = await delete_admin_quest(quest_id)
    await callback.answer(result.message, show_alert=True)
    await show_admin_quests_page(callback, page=page)


@router.callback_query(F.data == "admin_quests:page_info")
async def admin_quests_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Листай задания стрелками.")
