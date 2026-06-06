from __future__ import annotations

from pathlib import Path
from time import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.events import (
    ADMIN_EVENTS_PER_PAGE,
    EVENTS_PER_PAGE,
    build_admin_event_profile_keyboard,
    build_admin_events_list_keyboard,
    build_admin_events_main_keyboard,
    build_choice_page_keyboard,
    build_currency_keyboard,
    build_event_cancel_keyboard,
    build_event_confirm_keyboard,
    build_event_delete_keyboard,
    build_event_image_keyboard,
    build_event_reward_type_keyboard,
    build_event_target_keyboard,
    build_user_event_profile_keyboard,
    build_user_events_keyboard,
)
from app.services.events import (
    EventDraft,
    claim_event_reward,
    create_event,
    delete_event,
    get_admin_event_profile,
    get_admin_events_page,
    get_card_choices,
    get_pack_choices,
    get_user_event_profile,
    get_user_events_page,
    mark_event_announced,
    parse_msk_datetime,
    toggle_event_active,
    update_event_end_at,
    update_event_image,
    update_event_number_field,
    update_event_reward_card,
    update_event_reward_currency,
    update_event_reward_pack,
    update_event_target,
    update_event_text_field,
    get_announcement_recipients,
)
from app.states.events import EventAdminStates
from app.texts.events import (
    ADMIN_EVENTS_MAIN_TEXT,
    EVENT_BAD_DATE_TEXT,
    EVENT_BAD_DESCRIPTION_TEXT,
    EVENT_BAD_NUMBER_TEXT,
    EVENT_BAD_TITLE_TEXT,
    EVENT_DESCRIPTION_TEXT,
    EVENT_END_AT_TEXT,
    EVENT_IMAGE_TEXT,
    EVENT_NOT_FOUND_TEXT,
    EVENT_REWARD_AMOUNT_TEXT,
    EVENT_SEARCH_TEXT,
    EVENT_TARGET_VALUE_TEXT,
    EVENT_TITLE_TEXT,
    build_admin_event_profile_text,
    build_admin_events_page_text,
    build_event_announcement_text,
    build_event_claim_text,
    build_event_delete_text,
    build_event_draft_text,
    build_user_event_profile_text,
    build_user_events_page_text,
    parse_positive_int,
    validate_description,
    validate_title,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()
ADMIN_EVENTS_BUTTON_TEXT = "🎪 События"
UPLOAD_EVENTS_DIR = Path("assets/uploads/events")
EVENT_SEARCH_CACHE: dict[int, str] = {}
EVENT_PACK_SEARCH_CACHE: dict[int, str] = {}
EVENT_CARD_SEARCH_CACHE: dict[int, str] = {}
ACTIVE_EVENT_MESSAGES: dict[int, tuple[int, int]] = {}


async def admin_only(event: Message | CallbackQuery) -> bool:
    user = event.from_user
    return bool(user and is_admin(user.id))


def file_exists(path: str | None) -> bool:
    return bool(path and Path(path).exists())


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None, image_path: str | None = None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    image = image_path if file_exists(image_path) else None

    try:
        if image:
            await message.delete()
            sent = await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(image), caption=text, reply_markup=reply_markup)
        elif message.photo:
            await message.delete()
            sent = await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
            sent = message
        ACTIVE_EVENT_MESSAGES[callback.from_user.id] = (sent.chat.id, sent.message_id)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        if image:
            sent = await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(image), caption=text, reply_markup=reply_markup)
        else:
            sent = await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
        ACTIVE_EVENT_MESSAGES[callback.from_user.id] = (sent.chat.id, sent.message_id)


async def send_clean_message(message: Message, text: str, reply_markup=None, image_path: str | None = None) -> Message:
    old = ACTIVE_EVENT_MESSAGES.get(message.from_user.id if message.from_user else 0)
    if old:
        try:
            await message.bot.delete_message(chat_id=old[0], message_id=old[1])
        except TelegramBadRequest:
            pass

    if file_exists(image_path):
        sent = await message.answer_photo(photo=FSInputFile(image_path or ""), caption=text, reply_markup=reply_markup)
    else:
        sent = await message.answer(text, reply_markup=reply_markup)

    if message.from_user:
        ACTIVE_EVENT_MESSAGES[message.from_user.id] = (sent.chat.id, sent.message_id)
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


async def clear_prompt(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if not prompt_message_id:
        return
    if isinstance(event, Message):
        chat_id = event.chat.id
        bot = event.bot
    else:
        if not isinstance(event.message, Message):
            return
        chat_id = event.message.chat.id
        bot = event.bot
    try:
        await bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
    except TelegramBadRequest:
        pass


async def save_event_photo(message: Message) -> str | None:
    if not message.photo:
        return None
    UPLOAD_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"event_{message.from_user.id if message.from_user else 0}_{int(time())}.jpg"
    path = UPLOAD_EVENTS_DIR / file_name
    await message.bot.download(message.photo[-1], destination=path)
    return str(path).replace("\\", "/")


async def show_user_events_page(callback: CallbackQuery, page: int = 1) -> None:
    event_page = await get_user_events_page(callback.from_user.id, page=page, per_page=EVENTS_PER_PAGE)
    if event_page is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    await edit_or_send(callback, build_user_events_page_text(event_page), build_user_events_keyboard(event_page))


async def show_user_event_profile(callback: CallbackQuery, event_id: int, page: int = 1) -> None:
    profile = await get_user_event_profile(callback.from_user.id, event_id)
    if profile is None:
        await callback.answer(EVENT_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_user_event_profile_text(profile), build_user_event_profile_keyboard(profile, page), profile.image_path)


async def show_admin_main(callback: CallbackQuery) -> None:
    await edit_or_send(callback, ADMIN_EVENTS_MAIN_TEXT, build_admin_events_main_keyboard())


async def show_admin_events_page(callback: CallbackQuery, page: int = 1, search: str | None = None) -> None:
    events_page = await get_admin_events_page(page=page, per_page=ADMIN_EVENTS_PER_PAGE, search=search)
    await edit_or_send(callback, build_admin_events_page_text(events_page), build_admin_events_list_keyboard(events_page))


async def show_admin_event_profile(callback: CallbackQuery, event_id: int, page: int = 1) -> None:
    profile = await get_admin_event_profile(event_id)
    if profile is None:
        await callback.answer(EVENT_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_admin_event_profile_text(profile), build_admin_event_profile_keyboard(profile, page), profile.image_path)


async def show_pack_choices(callback: CallbackQuery, state: FSMContext, page: int = 1) -> None:
    data = await state.get_data()
    search = data.get("pack_search")
    choice_page = await get_pack_choices(page=page, per_page=5, search=search)
    await edit_or_send(
        callback,
        "<b>🎁 Выбери пак для награды</b>",
        build_choice_page_keyboard(choice_page, "admin_events:choose_pack", "admin_events:main", "admin_events:search_pack"),
    )


async def show_card_choices(callback: CallbackQuery, state: FSMContext, page: int = 1) -> None:
    data = await state.get_data()
    search = data.get("card_search")
    choice_page = await get_card_choices(page=page, per_page=5, search=search)
    await edit_or_send(
        callback,
        "<b>🃏 Выбери карточку для награды</b>",
        build_choice_page_keyboard(choice_page, "admin_events:choose_card", "admin_events:main", "admin_events:search_card"),
    )


@router.message(F.text == ADMIN_EVENTS_BUTTON_TEXT)
async def admin_events_button(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    await state.clear()
    await safe_delete_message(message)
    await send_clean_message(message, ADMIN_EVENTS_MAIN_TEXT, build_admin_events_main_keyboard())


@router.callback_query(F.data == "events:user_list:1")
@router.callback_query(F.data.startswith("events:user_list:"))
async def user_events_list(callback: CallbackQuery) -> None:
    page = int((callback.data or "").split(":")[-1]) if (callback.data or "").split(":")[-1].isdigit() else 1
    await show_user_events_page(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("events:user_view:"))
async def user_event_view(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await show_user_event_profile(callback, event_id, page)
    await callback.answer()


@router.callback_query(F.data.startswith("events:claim:"))
async def user_event_claim(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    progress_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    result = await claim_event_reward(callback.from_user.id, progress_id)
    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return
    await edit_or_send(callback, build_event_claim_text(result), image_path=result.image_path, reply_markup=None)
    await callback.answer("Награда получена")


@router.callback_query(F.data == "admin_events:main")
async def admin_events_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    await show_admin_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:list:"))
async def admin_events_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    page = int((callback.data or "").split(":")[-1]) if (callback.data or "").split(":")[-1].isdigit() else 1
    await show_admin_events_page(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:view:"))
async def admin_events_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    parts = (callback.data or "").split(":")
    event_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await show_admin_event_profile(callback, event_id, page)
    await callback.answer()


@router.callback_query(F.data == "admin_events:search")
async def admin_events_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.set_state(EventAdminStates.search)
    await edit_or_send(callback, EVENT_SEARCH_TEXT, build_event_cancel_keyboard())
    await callback.answer()


@router.message(EventAdminStates.search)
async def admin_events_search_text(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    query = (message.text or "").strip()
    await safe_delete_message(message)
    await state.clear()
    page = await get_admin_events_page(page=1, per_page=ADMIN_EVENTS_PER_PAGE, search=query)
    await message.answer(build_admin_events_page_text(page), reply_markup=build_admin_events_list_keyboard(page))


@router.callback_query(F.data == "admin_events:create")
async def admin_event_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only(callback):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    await state.set_state(EventAdminStates.create_image)
    await edit_or_send(callback, EVENT_IMAGE_TEXT, build_event_image_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_events:create_no_image")
async def admin_event_no_image(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(image_path=None)
    await state.set_state(EventAdminStates.create_title)
    await edit_or_send(callback, EVENT_TITLE_TEXT, build_event_cancel_keyboard())
    await callback.answer()


@router.message(EventAdminStates.create_image)
async def admin_event_image(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    image_path = await save_event_photo(message)
    await safe_delete_message(message)
    if image_path is None:
        await send_prompt(message, state, EVENT_IMAGE_TEXT, build_event_image_keyboard())
        return
    await state.update_data(image_path=image_path)
    await state.set_state(EventAdminStates.create_title)
    await send_prompt(message, state, EVENT_TITLE_TEXT, build_event_cancel_keyboard())


@router.message(EventAdminStates.create_title)
async def admin_event_title(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    title = validate_title(message.text or "")
    await safe_delete_message(message)
    if title is None:
        await send_prompt(message, state, EVENT_BAD_TITLE_TEXT, build_event_cancel_keyboard())
        return
    await state.update_data(title=title)
    await state.set_state(EventAdminStates.create_description)
    await send_prompt(message, state, EVENT_DESCRIPTION_TEXT, build_event_cancel_keyboard())


@router.message(EventAdminStates.create_description)
async def admin_event_description(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    description = validate_description(message.text or "")
    await safe_delete_message(message)
    if description is None:
        await send_prompt(message, state, EVENT_BAD_DESCRIPTION_TEXT, build_event_cancel_keyboard())
        return
    await state.update_data(description=description)
    await state.set_state(None)
    await send_prompt(message, state, "<b>🎯 Выбери цель события</b>", build_event_target_keyboard("admin_events:create_target"))


@router.callback_query(F.data.startswith("admin_events:create_target:"))
async def admin_event_create_target(callback: CallbackQuery, state: FSMContext) -> None:
    target_type = (callback.data or "").split(":")[-1]
    await state.update_data(target_type=target_type)
    await state.set_state(EventAdminStates.create_target_value)
    await edit_or_send(callback, EVENT_TARGET_VALUE_TEXT, build_event_cancel_keyboard())
    await callback.answer()


@router.message(EventAdminStates.create_target_value)
async def admin_event_target_value(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    value = parse_positive_int(message.text or "")
    await safe_delete_message(message)
    if value is None:
        await send_prompt(message, state, EVENT_BAD_NUMBER_TEXT, build_event_cancel_keyboard())
        return
    await state.update_data(target_value=value)
    await state.set_state(None)
    await send_prompt(message, state, "<b>🎁 Выбери тип награды</b>", build_event_reward_type_keyboard("admin_events:create_reward_type"))


@router.callback_query(F.data.startswith("admin_events:create_reward_type:"))
async def admin_event_create_reward_type(callback: CallbackQuery, state: FSMContext) -> None:
    reward_type = (callback.data or "").split(":")[-1]
    await state.update_data(reward_type=reward_type, reward_currency_code=None, reward_pack_id=None, reward_card_id=None)
    if reward_type == "currency":
        await edit_or_send(callback, "<b>💱 Выбери валюту награды</b>", build_currency_keyboard("admin_events:create_currency"))
    elif reward_type == "pack":
        await state.update_data(reward_context="create", pack_search=None)
        await show_pack_choices(callback, state, 1)
    else:
        await state.update_data(reward_context="create", card_search=None)
        await show_card_choices(callback, state, 1)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:create_currency:"))
async def admin_event_create_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency_code = (callback.data or "").split(":")[-1]
    await state.update_data(reward_currency_code=currency_code)
    await state.set_state(EventAdminStates.create_reward_amount)
    await edit_or_send(callback, EVENT_REWARD_AMOUNT_TEXT, build_event_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:choose_pack:"))
async def admin_event_choose_pack(callback: CallbackQuery, state: FSMContext) -> None:
    pack_id = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    if data.get("reward_context") == "edit":
        event_id = int(data.get("event_id", 0))
        page = int(data.get("page", 1))
        result = await update_event_reward_pack(event_id, pack_id, int(data.get("reward_amount", 1) or 1))
        await state.clear()
        await callback.answer(result.message)
        await show_admin_event_profile(callback, event_id, page)
        return
    await state.update_data(reward_pack_id=pack_id, reward_type="pack")
    await state.set_state(EventAdminStates.create_reward_amount)
    await edit_or_send(callback, EVENT_REWARD_AMOUNT_TEXT, build_event_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:choose_card:"))
async def admin_event_choose_card(callback: CallbackQuery, state: FSMContext) -> None:
    card_id = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    if data.get("reward_context") == "edit":
        event_id = int(data.get("event_id", 0))
        page = int(data.get("page", 1))
        result = await update_event_reward_card(event_id, card_id, int(data.get("reward_amount", 1) or 1))
        await state.clear()
        await callback.answer(result.message)
        await show_admin_event_profile(callback, event_id, page)
        return
    await state.update_data(reward_card_id=card_id, reward_type="card")
    await state.set_state(EventAdminStates.create_reward_amount)
    await edit_or_send(callback, EVENT_REWARD_AMOUNT_TEXT, build_event_cancel_keyboard())
    await callback.answer()


@router.message(EventAdminStates.create_reward_amount)
async def admin_event_reward_amount(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    amount = parse_positive_int(message.text or "")
    await safe_delete_message(message)
    if amount is None:
        await send_prompt(message, state, EVENT_BAD_NUMBER_TEXT, build_event_cancel_keyboard())
        return
    await state.update_data(reward_amount=amount)
    await state.set_state(EventAdminStates.create_end_at)
    await send_prompt(message, state, EVENT_END_AT_TEXT, build_event_cancel_keyboard())


@router.message(EventAdminStates.create_end_at)
async def admin_event_end_at(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    await safe_delete_message(message)
    try:
        end_at = parse_msk_datetime(message.text or "")
    except ValueError:
        await send_prompt(message, state, EVENT_BAD_DATE_TEXT, build_event_cancel_keyboard())
        return
    await state.update_data(end_at=end_at)
    data = await state.get_data()
    draft = EventDraft(
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        image_path=data.get("image_path"),
        target_type=str(data.get("target_type", "matches_played")),
        target_value=int(data.get("target_value", 1)),
        reward_type=str(data.get("reward_type", "currency")),
        reward_currency_code=data.get("reward_currency_code"),
        reward_amount=int(data.get("reward_amount", 1)),
        reward_pack_id=data.get("reward_pack_id"),
        reward_card_id=data.get("reward_card_id"),
        end_at=data.get("end_at"),
    )
    await send_prompt(message, state, build_event_draft_text(draft), build_event_confirm_keyboard())


@router.callback_query(F.data == "admin_events:create_confirm")
async def admin_event_create_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = EventDraft(
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        image_path=data.get("image_path"),
        target_type=str(data.get("target_type", "matches_played")),
        target_value=int(data.get("target_value", 1)),
        reward_type=str(data.get("reward_type", "currency")),
        reward_currency_code=data.get("reward_currency_code"),
        reward_amount=int(data.get("reward_amount", 1)),
        reward_pack_id=data.get("reward_pack_id"),
        reward_card_id=data.get("reward_card_id"),
        end_at=data.get("end_at"),
    )
    result = await create_event(draft)
    await state.clear()
    if not result.success or result.event_id is None:
        await callback.answer(result.message, show_alert=True)
        await show_admin_main(callback)
        return
    await callback.answer(result.message)
    await show_admin_event_profile(callback, result.event_id, 1)


@router.callback_query(F.data.startswith("admin_events:toggle:"))
async def admin_event_toggle(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    result = await toggle_event_active(event_id)
    await callback.answer(result.message)
    await show_admin_event_profile(callback, event_id, page)


@router.callback_query(F.data.startswith("admin_events:delete_ask:"))
async def admin_event_delete_ask(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    profile = await get_admin_event_profile(event_id)
    if profile is None:
        await callback.answer(EVENT_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_event_delete_text(profile), build_event_delete_keyboard(event_id, page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:delete:"))
async def admin_event_delete(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    result = await delete_event(event_id)
    await callback.answer(result.message)
    await show_admin_events_page(callback, page)


@router.callback_query(F.data.startswith("admin_events:announce:"))
async def admin_event_announce(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    profile = await get_admin_event_profile(event_id)
    if profile is None:
        await callback.answer(EVENT_NOT_FOUND_TEXT, show_alert=True)
        return
    recipients = await get_announcement_recipients()
    text = build_event_announcement_text(profile)
    sent_count = 0
    for telegram_id in recipients:
        try:
            if file_exists(profile.image_path):
                await callback.bot.send_photo(chat_id=telegram_id, photo=FSInputFile(profile.image_path or ""), caption=text)
            else:
                await callback.bot.send_message(chat_id=telegram_id, text=text)
            sent_count += 1
        except Exception:
            continue
    await mark_event_announced(event_id)
    await callback.answer(f"📢 Объявление отправлено: {sent_count}", show_alert=True)
    await show_admin_event_profile(callback, event_id, page)


@router.callback_query(F.data.startswith("admin_events:edit:"))
async def admin_event_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    field = parts[2]
    event_id = int(parts[3])
    page = int(parts[4])
    await state.update_data(event_id=event_id, page=page, field=field)
    await state.set_state(EventAdminStates.edit_text)
    prompt = EVENT_TITLE_TEXT if field == "title" else EVENT_DESCRIPTION_TEXT
    await edit_or_send(callback, prompt, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
    await callback.answer()


@router.message(EventAdminStates.edit_text)
async def admin_event_edit_text_value(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    data = await state.get_data()
    field = str(data.get("field"))
    event_id = int(data.get("event_id", 0))
    page = int(data.get("page", 1))
    value = validate_title(message.text or "") if field == "title" else validate_description(message.text or "")
    await safe_delete_message(message)
    if value is None:
        await send_prompt(message, state, EVENT_BAD_TITLE_TEXT if field == "title" else EVENT_BAD_DESCRIPTION_TEXT, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
        return
    result = await update_event_text_field(event_id, field, value)
    await state.clear()
    await message.answer(result.message)


@router.callback_query(F.data.startswith("admin_events:edit_number:"))
async def admin_event_edit_number(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    field = parts[2]
    event_id = int(parts[3])
    page = int(parts[4])
    await state.update_data(event_id=event_id, page=page, field=field)
    await state.set_state(EventAdminStates.edit_number)
    await edit_or_send(callback, EVENT_TARGET_VALUE_TEXT if field == "target_value" else EVENT_REWARD_AMOUNT_TEXT, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
    await callback.answer()


@router.message(EventAdminStates.edit_number)
async def admin_event_edit_number_value(message: Message, state: FSMContext) -> None:
    if not await admin_only(message):
        return
    data = await state.get_data()
    field = str(data.get("field"))
    event_id = int(data.get("event_id", 0))
    page = int(data.get("page", 1))
    value = parse_positive_int(message.text or "")
    await safe_delete_message(message)
    if value is None:
        await send_prompt(message, state, EVENT_BAD_NUMBER_TEXT, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
        return
    result = await update_event_number_field(event_id, field, value)
    await state.clear()
    await message.answer(result.message)


@router.callback_query(F.data.startswith("admin_events:edit_target:"))
async def admin_event_edit_target(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    await edit_or_send(callback, "<b>🎯 Выбери новую цель события</b>", build_event_target_keyboard(f"admin_events:set_target:{event_id}:{page}", f"admin_events:view:{event_id}:{page}"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:set_target:"))
async def admin_event_set_target(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    target_type = parts[4]
    result = await update_event_target(event_id, target_type)
    await callback.answer(result.message)
    await show_admin_event_profile(callback, event_id, page)


@router.callback_query(F.data.startswith("admin_events:edit_end:"))
async def admin_event_edit_end(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    await state.update_data(event_id=event_id, page=page)
    await state.set_state(EventAdminStates.edit_end_at)
    await edit_or_send(callback, EVENT_END_AT_TEXT, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
    await callback.answer()


@router.message(EventAdminStates.edit_end_at)
async def admin_event_edit_end_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_id = int(data.get("event_id", 0))
    page = int(data.get("page", 1))
    await safe_delete_message(message)
    try:
        end_at = parse_msk_datetime(message.text or "")
    except ValueError:
        await send_prompt(message, state, EVENT_BAD_DATE_TEXT, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
        return
    result = await update_event_end_at(event_id, end_at)
    await state.clear()
    await message.answer(result.message)


@router.callback_query(F.data.startswith("admin_events:edit_image:"))
async def admin_event_edit_image(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    await state.update_data(event_id=event_id, page=page)
    await state.set_state(EventAdminStates.edit_image)
    await edit_or_send(callback, EVENT_IMAGE_TEXT, build_event_cancel_keyboard(f"admin_events:view:{event_id}:{page}"))
    await callback.answer()


@router.message(EventAdminStates.edit_image)
async def admin_event_edit_image_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_id = int(data.get("event_id", 0))
    image_path = await save_event_photo(message)
    await safe_delete_message(message)
    if image_path is None:
        await send_prompt(message, state, EVENT_IMAGE_TEXT, build_event_cancel_keyboard())
        return
    result = await update_event_image(event_id, image_path)
    await state.clear()
    await message.answer(result.message)


@router.callback_query(F.data.startswith("admin_events:edit_reward:"))
async def admin_event_edit_reward(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    await state.update_data(reward_context="edit", event_id=event_id, page=page)
    await edit_or_send(callback, "<b>🎁 Выбери новый тип награды</b>", build_event_reward_type_keyboard(f"admin_events:set_reward_type:{event_id}:{page}", f"admin_events:view:{event_id}:{page}"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:set_reward_type:"))
async def admin_event_set_reward_type(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    reward_type = parts[4]
    await state.update_data(reward_context="edit", event_id=event_id, page=page)
    if reward_type == "currency":
        await edit_or_send(callback, "<b>💱 Выбери валюту награды</b>", build_currency_keyboard(f"admin_events:set_currency:{event_id}:{page}", f"admin_events:view:{event_id}:{page}"))
    elif reward_type == "pack":
        await state.update_data(pack_search=None)
        await show_pack_choices(callback, state, 1)
    else:
        await state.update_data(card_search=None)
        await show_card_choices(callback, state, 1)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:set_currency:"))
async def admin_event_set_currency(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    event_id = int(parts[2])
    page = int(parts[3])
    currency_code = parts[4]
    result = await update_event_reward_currency(event_id, currency_code, 1)
    await callback.answer(result.message)
    await show_admin_event_profile(callback, event_id, page)


@router.callback_query(F.data == "events:page_info")
async def events_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Листай страницы стрелками.")

@router.callback_query(F.data.startswith("admin_events:choose_pack_page:"))
async def admin_event_choose_pack_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "").split(":")[-1]) if (callback.data or "").split(":")[-1].isdigit() else 1
    await show_pack_choices(callback, state, page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_events:choose_card_page:"))
async def admin_event_choose_card_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "").split(":")[-1]) if (callback.data or "").split(":")[-1].isdigit() else 1
    await show_card_choices(callback, state, page)
    await callback.answer()


@router.callback_query(F.data == "admin_events:search_pack")
async def admin_event_search_pack(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EventAdminStates.choose_pack_search)
    await edit_or_send(callback, "<b>🔎 Поиск пака</b>\n\nОтправь название или код пака.", build_event_cancel_keyboard())
    await callback.answer()


@router.message(EventAdminStates.choose_pack_search)
async def admin_event_search_pack_text(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    await state.update_data(pack_search=(message.text or "").strip())
    page = await get_pack_choices(page=1, per_page=5, search=(message.text or "").strip())
    await message.answer("<b>🎁 Выбери пак для награды</b>", reply_markup=build_choice_page_keyboard(page, "admin_events:choose_pack", "admin_events:main", "admin_events:search_pack"))


@router.callback_query(F.data == "admin_events:search_card")
async def admin_event_search_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EventAdminStates.choose_card_search)
    await edit_or_send(callback, "<b>🔎 Поиск карточки</b>\n\nОтправь имя, команду, страну, коллекцию или ID.", build_event_cancel_keyboard())
    await callback.answer()


@router.message(EventAdminStates.choose_card_search)
async def admin_event_search_card_text(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    await state.update_data(card_search=(message.text or "").strip())
    page = await get_card_choices(page=1, per_page=5, search=(message.text or "").strip())
    await message.answer("<b>🃏 Выбери карточку для награды</b>", reply_markup=build_choice_page_keyboard(page, "admin_events:choose_card", "admin_events:main", "admin_events:search_card"))
