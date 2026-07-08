from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.hockey_pass import (
    build_admin_cancel_keyboard,
    build_admin_hockey_pass_main_keyboard,
    build_admin_pass_delete_keyboard,
    build_admin_pass_profile_keyboard,
    build_admin_passes_list_keyboard,
    build_admin_reward_delete_keyboard,
    build_admin_reward_profile_keyboard,
    build_admin_rewards_list_keyboard,
    build_choice_page_keyboard,
    build_confirm_pass_keyboard,
    build_confirm_reward_keyboard,
    build_currency_choice_keyboard,
    build_premium_buy_keyboard,
    build_reward_type_keyboard,
    build_track_keyboard,
    build_user_hockey_pass_keyboard,
    build_user_hockey_pass_map_keyboard,
    build_user_reward_keyboard,
    build_user_rewards_keyboard,
)
from app.services.hockey_pass import (
    HockeyPassDraft,
    RewardDraft,
    claim_reward,
    create_pass,
    create_reward,
    delete_pass,
    delete_reward,
    get_admin_rewards_page,
    get_card_choices_page,
    get_currency_choices,
    get_pack_choices_page,
    get_pass_profile,
    get_passes_page,
    get_reward_profile,
    get_user_hockey_pass_info,
    get_user_hockey_pass_map,
    get_user_rewards_page,
    parse_moscow_datetime,
    parse_positive_int,
    purchase_premium,
    replace_reward_payload,
    toggle_pass_active,
    toggle_reward_active,
    update_pass_price,
    update_pass_text_field,
    update_reward_basic_field,
    validate_description,
    validate_title,
)
from app.states.hockey_pass import HockeyPassAdminStates
from app.texts.hockey_pass import (
    ADMIN_HPASS_BAD_DATE_TEXT,
    ADMIN_HPASS_BAD_DESCRIPTION_TEXT,
    ADMIN_HPASS_BAD_NUMBER_TEXT,
    ADMIN_HPASS_BAD_TITLE_TEXT,
    ADMIN_HPASS_CARD_SEARCH_TEXT,
    ADMIN_HPASS_DELETED_TEXT,
    ADMIN_HPASS_DESCRIPTION_TEXT,
    ADMIN_HPASS_END_TEXT,
    ADMIN_HPASS_MAIN_TEXT,
    ADMIN_HPASS_NOT_FOUND_TEXT,
    ADMIN_HPASS_PACK_SEARCH_TEXT,
    ADMIN_HPASS_PRICE_TEXT,
    ADMIN_HPASS_REWARD_AMOUNT_TEXT,
    ADMIN_HPASS_REWARD_DELETED_TEXT,
    ADMIN_HPASS_REWARD_LEVEL_TEXT,
    ADMIN_HPASS_REWARD_NOT_FOUND_TEXT,
    ADMIN_HPASS_REWARD_SAVED_TEXT,
    ADMIN_HPASS_REWARD_TITLE_TEXT,
    ADMIN_HPASS_SAVED_TEXT,
    ADMIN_HPASS_TITLE_TEXT,
    ADMIN_HPASS_UPDATED_TEXT,
    build_admin_pass_delete_text,
    build_admin_pass_profile_text,
    build_admin_passes_page_text,
    build_admin_reward_delete_text,
    build_admin_reward_profile_text,
    build_admin_rewards_page_text,
    build_choice_page_text,
    build_claim_result_text,
    build_pass_draft_text,
    build_premium_buy_text,
    build_premium_purchase_result_text,
    build_reward_draft_text,
    build_user_hockey_pass_map_text,
    build_user_hockey_pass_text,
    build_user_reward_profile_text,
    build_user_rewards_page_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()

HOCKEY_PASS_BUTTON_TEXT = "🎟 Hockey Pass"
ACTIVE_HPASS_MESSAGES: dict[int, tuple[int, int]] = {}


def existing_image_path(path: str | None) -> Path | None:
    if not path:
        return None
    image_path = Path(path)
    if image_path.exists() and image_path.is_file():
        return image_path
    return None


async def remember_message(user_id: int, message: Message) -> None:
    ACTIVE_HPASS_MESSAGES[user_id] = (message.chat.id, message.message_id)


async def delete_old_message(bot, user_id: int) -> None:
    old_message = ACTIVE_HPASS_MESSAGES.get(user_id)
    if not old_message:
        return
    try:
        await bot.delete_message(chat_id=old_message[0], message_id=old_message[1])
    except TelegramBadRequest:
        pass


async def send_clean_message(message: Message, text: str, reply_markup=None, image_path: str | None = None) -> Message:
    user_id = message.from_user.id if message.from_user else 0
    await delete_old_message(message.bot, user_id)

    image = existing_image_path(image_path)
    if image is not None:
        sent = await message.answer_photo(photo=FSInputFile(image), caption=text, reply_markup=reply_markup)
    else:
        sent = await message.answer(text, reply_markup=reply_markup)

    if message.from_user:
        await remember_message(message.from_user.id, sent)
    return sent


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None, image_path: str | None = None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    image = existing_image_path(image_path)

    try:
        if image is not None:
            await message.delete()
            sent = await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(image), caption=text, reply_markup=reply_markup)
        elif message.photo:
            await message.delete()
            sent = await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
            sent = message
        await remember_message(callback.from_user.id, sent)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        if image is not None:
            sent = await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(image), caption=text, reply_markup=reply_markup)
        else:
            sent = await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
        await remember_message(callback.from_user.id, sent)


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
        await remember_message(message.from_user.id, sent)


async def clear_prompt_from_state(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if not prompt_message_id:
        return

    if isinstance(event, Message):
        chat_id = event.chat.id
        bot = event.bot
    else:
        if not isinstance(event.message, Message):
            await state.update_data(prompt_message_id=None)
            return
        chat_id = event.message.chat.id
        bot = event.bot

    try:
        await bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
    except TelegramBadRequest:
        pass

    await state.update_data(prompt_message_id=None)


async def clear_admin_step(event: Message | CallbackQuery, state: FSMContext) -> None:
    await clear_prompt_from_state(event, state)
    if isinstance(event, Message):
        if event.from_user:
            await delete_old_message(event.bot, event.from_user.id)
    else:
        await delete_old_message(event.bot, event.from_user.id)


async def show_user_pass_page(callback: CallbackQuery, page: int = 1) -> None:
    pass_map = await get_user_hockey_pass_map(callback.from_user.id, page=page)
    if pass_map is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    await edit_or_send(
        callback,
        build_user_hockey_pass_map_text(pass_map),
        reply_markup=build_user_hockey_pass_map_keyboard(pass_map),
    )


async def show_user_main(callback: CallbackQuery) -> None:
    await show_user_pass_page(callback, 1)


async def show_admin_main(callback: CallbackQuery) -> None:
    await edit_or_send(callback, ADMIN_HPASS_MAIN_TEXT, reply_markup=build_admin_hockey_pass_main_keyboard())


async def show_admin_passes_page(callback: CallbackQuery, page: int) -> None:
    passes_page = await get_passes_page(page=page)
    await edit_or_send(callback, build_admin_passes_page_text(passes_page), reply_markup=build_admin_passes_list_keyboard(passes_page))


async def show_admin_pass_profile(callback: CallbackQuery, pass_id: int, page: int) -> None:
    profile = await get_pass_profile(pass_id)
    if profile is None:
        await callback.answer(ADMIN_HPASS_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_admin_pass_profile_text(profile), reply_markup=build_admin_pass_profile_keyboard(profile, page))


async def show_admin_rewards_page(callback: CallbackQuery, pass_id: int, page: int) -> None:
    rewards_page = await get_admin_rewards_page(pass_id=pass_id, page=page)
    if rewards_page is None:
        await callback.answer(ADMIN_HPASS_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_admin_rewards_page_text(rewards_page), reply_markup=build_admin_rewards_list_keyboard(rewards_page))


async def show_admin_reward_profile(callback: CallbackQuery, reward_id: int, page: int) -> None:
    reward = await get_reward_profile(reward_id)
    if reward is None:
        await callback.answer(ADMIN_HPASS_REWARD_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_admin_reward_profile_text(reward), reply_markup=build_admin_reward_profile_keyboard(reward, page), image_path=reward.card_image_path or reward.pack_image_path)


@router.message(F.text == HOCKEY_PASS_BUTTON_TEXT)
async def hockey_pass_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await safe_delete_message(message)

    if message.from_user is None:
        return

    if is_admin(message.from_user.id):
        await send_clean_message(message, ADMIN_HPASS_MAIN_TEXT, reply_markup=build_admin_hockey_pass_main_keyboard())
        return

    pass_map = await get_user_hockey_pass_map(message.from_user.id, page=1)
    if pass_map is None:
        await message.answer("🎟 Открой игру через /start.")
        return
    await send_clean_message(
        message,
        build_user_hockey_pass_map_text(pass_map),
        reply_markup=build_user_hockey_pass_map_keyboard(pass_map),
    )


@router.callback_query(F.data == "hpass:main")
async def user_hpass_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_user_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("hpass:levels:"))
async def user_hpass_levels(callback: CallbackQuery) -> None:
    page = int((callback.data or "").split(":")[-1])
    await show_user_pass_page(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("hpass:rewards:"))
async def user_hpass_rewards(callback: CallbackQuery) -> None:
    page = int((callback.data or "").split(":")[-1])
    rewards_page = await get_user_rewards_page(callback.from_user.id, page=page)
    if rewards_page is None:
        await callback.answer("Награды пока недоступны.", show_alert=True)
        return
    await edit_or_send(callback, build_user_rewards_page_text(rewards_page), reply_markup=build_user_rewards_keyboard(rewards_page))
    await callback.answer()


@router.callback_query(F.data.startswith("hpass:reward:"))
async def user_hpass_reward(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    reward = await get_reward_profile(int(reward_id), telegram_id=callback.from_user.id)
    if reward is None:
        await callback.answer("Награда недоступна.", show_alert=True)
        return
    await edit_or_send(callback, build_user_reward_profile_text(reward), reply_markup=build_user_reward_keyboard(reward, int(page)), image_path=reward.card_image_path or reward.pack_image_path)
    await callback.answer()


@router.callback_query(F.data.startswith("hpass:claim:"))
async def user_hpass_claim(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    result, error = await claim_reward(callback.from_user.id, int(reward_id))
    if error or result is None:
        await callback.answer(error or "Награда недоступна.", show_alert=True)
        return
    rewards_page = await get_user_rewards_page(callback.from_user.id, page=int(page))
    await edit_or_send(
        callback,
        build_claim_result_text(result),
        reply_markup=build_user_rewards_keyboard(rewards_page) if rewards_page is not None else None,
        image_path=result.image_path,
    )
    await callback.answer("Награда получена")


@router.callback_query(F.data.startswith("hpass:level_claim:"))
async def user_hpass_level_claim(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    result, error = await claim_reward(callback.from_user.id, int(reward_id))
    if error or result is None:
        await callback.answer(error or "Награда недоступна.", show_alert=True)
        return
    pass_map = await get_user_hockey_pass_map(callback.from_user.id, page=int(page))
    if pass_map is None:
        await callback.answer("Награда получена")
        return
    await edit_or_send(
        callback,
        build_user_hockey_pass_map_text(pass_map),
        reply_markup=build_user_hockey_pass_map_keyboard(pass_map),
    )
    await callback.answer("🎁 Награда получена")


@router.callback_query(F.data == "hpass:buy_ask")
async def user_hpass_buy_ask(callback: CallbackQuery) -> None:
    info = await get_user_hockey_pass_info(callback.from_user.id)
    if info is None or info.pass_id is None:
        await callback.answer("Premium пока недоступен.", show_alert=True)
        return
    if info.premium_unlocked:
        await callback.answer("Premium уже открыт.", show_alert=True)
        return
    await edit_or_send(callback, build_premium_buy_text(info), reply_markup=build_premium_buy_keyboard())
    await callback.answer()


@router.callback_query(F.data == "hpass:buy")
async def user_hpass_buy(callback: CallbackQuery) -> None:
    result, error = await purchase_premium(callback.from_user.id)
    if error or result is None:
        await callback.answer(error or "Premium пока недоступен.", show_alert=True)
        return
    pass_map = await get_user_hockey_pass_map(callback.from_user.id, page=1)
    if pass_map is not None:
        await edit_or_send(
            callback,
            build_user_hockey_pass_map_text(pass_map),
            reply_markup=build_user_hockey_pass_map_keyboard(pass_map),
        )
    else:
        info = await get_user_hockey_pass_info(callback.from_user.id)
        await edit_or_send(callback, build_premium_purchase_result_text(result), reply_markup=build_user_hockey_pass_keyboard(info))
    await callback.answer("Premium открыт")


@router.callback_query(F.data == "admin_hpass:main")
async def admin_hpass_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_admin_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:list:"))
async def admin_hpass_list(callback: CallbackQuery) -> None:
    page = int((callback.data or "").split(":")[-1])
    await show_admin_passes_page(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:view:"))
async def admin_hpass_view(callback: CallbackQuery) -> None:
    _, _, pass_id, page = (callback.data or "").split(":")
    await show_admin_pass_profile(callback, int(pass_id), int(page))
    await callback.answer()


@router.callback_query(F.data == "admin_hpass:create")
async def admin_hpass_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(HockeyPassAdminStates.create_title)
    await edit_or_send(callback, ADMIN_HPASS_TITLE_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.create_title))
async def admin_hpass_create_title(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    title = validate_title(message.text or "")
    if title is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_TITLE_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    await state.update_data(title=title)
    await state.set_state(HockeyPassAdminStates.create_description)
    await send_prompt(message, state, ADMIN_HPASS_DESCRIPTION_TEXT, reply_markup=build_admin_cancel_keyboard())


@router.message(StateFilter(HockeyPassAdminStates.create_description))
async def admin_hpass_create_description(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    description = validate_description(message.text or "")
    if description is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_DESCRIPTION_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    await state.update_data(description=description)
    await state.set_state(HockeyPassAdminStates.create_end_at)
    await send_prompt(message, state, ADMIN_HPASS_END_TEXT, reply_markup=build_admin_cancel_keyboard())


@router.message(StateFilter(HockeyPassAdminStates.create_end_at))
async def admin_hpass_create_end(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    end_at = parse_moscow_datetime(message.text or "")
    if end_at is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_DATE_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    await state.update_data(end_at=end_at)
    choices = await get_currency_choices()
    await edit_or_send_fake_prompt(message, state, "<b>👑 Валюта Premium</b>\n\nВыбери валюту для покупки Premium.", build_currency_choice_keyboard(choices, "admin_hpass:price_currency_select", "admin_hpass:main"))


async def edit_or_send_fake_prompt(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    await send_prompt(message, state, text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("admin_hpass:price_currency_select:"))
async def admin_hpass_create_price_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency_code = (callback.data or "").split(":")[-1]
    if currency_code == "none":
        data = await state.get_data()
        draft = HockeyPassDraft(data["title"], data.get("description", ""), data["end_at"], None, 0)
        await state.update_data(premium_currency_code=None, premium_price_amount=0)
        await state.set_state(None)
        await edit_or_send(callback, build_pass_draft_text(draft), reply_markup=build_confirm_pass_keyboard())
        await callback.answer()
        return

    await state.update_data(premium_currency_code=currency_code)
    await state.set_state(HockeyPassAdminStates.create_price_amount)
    await edit_or_send(callback, ADMIN_HPASS_PRICE_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.create_price_amount))
async def admin_hpass_create_price_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    amount = parse_positive_int(message.text or "", min_value=0)
    if amount is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_NUMBER_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    data = await state.get_data()
    await state.update_data(premium_price_amount=amount)
    draft = HockeyPassDraft(data["title"], data.get("description", ""), data["end_at"], data.get("premium_currency_code"), amount)
    await state.set_state(None)
    await send_prompt(message, state, build_pass_draft_text(draft), reply_markup=build_confirm_pass_keyboard())


@router.callback_query(F.data == "admin_hpass:create_confirm")
async def admin_hpass_create_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not {"title", "end_at"}.issubset(data):
        await callback.answer("Обнови раздел и создай Pass заново.", show_alert=True)
        return

    draft = HockeyPassDraft(
        data["title"],
        data.get("description", ""),
        data["end_at"],
        data.get("premium_currency_code"),
        int(data.get("premium_price_amount", 0)),
    )
    pass_id = await create_pass(draft)
    await clear_admin_step(callback, state)
    await state.clear()
    await callback.answer(ADMIN_HPASS_SAVED_TEXT)
    await show_admin_pass_profile(callback, pass_id, 1)


@router.callback_query(F.data.startswith("admin_hpass:toggle:"))
async def admin_hpass_toggle(callback: CallbackQuery) -> None:
    _, _, pass_id, page = (callback.data or "").split(":")
    result = await toggle_pass_active(int(pass_id))
    if result is None:
        await callback.answer(ADMIN_HPASS_NOT_FOUND_TEXT, show_alert=True)
        return
    await callback.answer(ADMIN_HPASS_UPDATED_TEXT)
    await show_admin_pass_profile(callback, int(pass_id), int(page))


@router.callback_query(F.data.startswith("admin_hpass:delete_ask:"))
async def admin_hpass_delete_ask(callback: CallbackQuery) -> None:
    _, _, pass_id, page = (callback.data or "").split(":")
    profile = await get_pass_profile(int(pass_id))
    if profile is None:
        await callback.answer(ADMIN_HPASS_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_admin_pass_delete_text(profile), reply_markup=build_admin_pass_delete_keyboard(int(pass_id), int(page)))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:delete:"))
async def admin_hpass_delete(callback: CallbackQuery) -> None:
    _, _, pass_id, page = (callback.data or "").split(":")
    await delete_pass(int(pass_id))
    await callback.answer(ADMIN_HPASS_DELETED_TEXT)
    await show_admin_passes_page(callback, int(page))


@router.callback_query(F.data.startswith("admin_hpass:edit:"))
async def admin_hpass_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, field, pass_id, page = (callback.data or "").split(":")
    prompt = ADMIN_HPASS_TITLE_TEXT if field == "title" else ADMIN_HPASS_DESCRIPTION_TEXT if field == "description" else ADMIN_HPASS_END_TEXT
    await state.update_data(edit_target="pass", field=field, pass_id=int(pass_id), page=int(page))
    await state.set_state(HockeyPassAdminStates.edit_text)
    await edit_or_send(callback, prompt, reply_markup=build_admin_cancel_keyboard(f"admin_hpass:view:{pass_id}:{page}"))
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.edit_text))
async def admin_hpass_edit_text(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    data = await state.get_data()
    field = data.get("field")
    value = message.text or ""
    if field == "title":
        clean = validate_title(value)
        bad_text = ADMIN_HPASS_BAD_TITLE_TEXT
    elif field == "description":
        clean = validate_description(value)
        bad_text = ADMIN_HPASS_BAD_DESCRIPTION_TEXT
    else:
        clean = parse_moscow_datetime(value)
        bad_text = ADMIN_HPASS_BAD_DATE_TEXT
    if clean is None:
        await send_prompt(message, state, bad_text, reply_markup=build_admin_cancel_keyboard(f"admin_hpass:view:{data['pass_id']}:{data['page']}"))
        return
    await update_pass_text_field(int(data["pass_id"]), field, clean)
    profile = await get_pass_profile(int(data["pass_id"]))
    await state.clear()
    if profile is not None:
        await send_clean_message(
            message,
            build_admin_pass_profile_text(profile),
            reply_markup=build_admin_pass_profile_keyboard(profile, int(data["page"])),
        )
    else:
        await send_clean_message(message, ADMIN_HPASS_UPDATED_TEXT)


@router.callback_query(F.data.startswith("admin_hpass:price_currency:"))
async def admin_hpass_edit_price_currency(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, pass_id, page = (callback.data or "").split(":")
    await state.update_data(pass_id=int(pass_id), page=int(page))
    choices = await get_currency_choices()
    await edit_or_send(callback, "<b>👑 Валюта Premium</b>\n\nВыбери валюту для покупки Premium.", reply_markup=build_currency_choice_keyboard(choices, "admin_hpass:edit_price_currency_select", f"admin_hpass:view:{pass_id}:{page}"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:edit_price_currency_select:"))
async def admin_hpass_edit_price_currency_select(callback: CallbackQuery, state: FSMContext) -> None:
    currency_code = (callback.data or "").split(":")[-1]
    data = await state.get_data()
    if currency_code == "none":
        await update_pass_price(int(data["pass_id"]), None, 0)
        await state.clear()
        await callback.answer(ADMIN_HPASS_UPDATED_TEXT)
        await show_admin_pass_profile(callback, int(data["pass_id"]), int(data["page"]))
        return
    await state.update_data(premium_currency_code=currency_code)
    await state.set_state(HockeyPassAdminStates.edit_price_amount)
    await edit_or_send(callback, ADMIN_HPASS_PRICE_TEXT, reply_markup=build_admin_cancel_keyboard(f"admin_hpass:view:{data['pass_id']}:{data['page']}"))
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.edit_price_amount))
async def admin_hpass_edit_price_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    amount = parse_positive_int(message.text or "", min_value=0)
    data = await state.get_data()
    if amount is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_NUMBER_TEXT, reply_markup=build_admin_cancel_keyboard(f"admin_hpass:view:{data['pass_id']}:{data['page']}"))
        return
    await update_pass_price(int(data["pass_id"]), data.get("premium_currency_code"), amount)
    profile = await get_pass_profile(int(data["pass_id"]))
    await state.clear()
    if profile is not None:
        await send_clean_message(
            message,
            build_admin_pass_profile_text(profile),
            reply_markup=build_admin_pass_profile_keyboard(profile, int(data["page"])),
        )
    else:
        await send_clean_message(message, ADMIN_HPASS_UPDATED_TEXT)


@router.callback_query(F.data.startswith("admin_hpass:rewards:"))
async def admin_hpass_rewards(callback: CallbackQuery) -> None:
    _, _, pass_id, page = (callback.data or "").split(":")
    await show_admin_rewards_page(callback, int(pass_id), int(page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward:"))
async def admin_hpass_reward(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    await show_admin_reward_profile(callback, int(reward_id), int(page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:add_reward:"))
async def admin_hpass_add_reward(callback: CallbackQuery, state: FSMContext) -> None:
    pass_id = int((callback.data or "").split(":")[-1])
    await state.clear()
    await state.update_data(pass_id=pass_id, mode="create")
    await state.set_state(HockeyPassAdminStates.reward_level)
    await edit_or_send(callback, ADMIN_HPASS_REWARD_LEVEL_TEXT, reply_markup=build_admin_cancel_keyboard(f"admin_hpass:rewards:{pass_id}:1"))
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.reward_level))
async def admin_hpass_reward_level(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    level = parse_positive_int(message.text or "", min_value=1, max_value=40)
    data = await state.get_data()
    if level is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_NUMBER_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    if data.get("edit_field") == "level":
        await update_reward_basic_field(int(data["reward_id"]), "level", level)
        reward = await get_reward_profile(int(data["reward_id"]))
        await state.clear()
        if reward is not None:
            await send_clean_message(
                message,
                build_admin_reward_profile_text(reward),
                reply_markup=build_admin_reward_profile_keyboard(reward, int(data["page"])),
                image_path=reward.card_image_path or reward.pack_image_path,
            )
        else:
            await send_clean_message(message, ADMIN_HPASS_UPDATED_TEXT)
        return
    await state.update_data(level=level)
    await state.set_state(None)
    await send_prompt(message, state, "<b>🌿 Ветка награды</b>\n\nВыбери, где будет награда.", reply_markup=build_track_keyboard("admin_hpass:reward_track_select", "admin_hpass:main"))


@router.callback_query(F.data.startswith("admin_hpass:reward_track_select:"))
async def admin_hpass_reward_track_select(callback: CallbackQuery, state: FSMContext) -> None:
    track = (callback.data or "").split(":")[-1]
    await state.update_data(track=track)
    await edit_or_send(callback, "<b>🎁 Тип награды</b>\n\nВыбери, что получит игрок.", reply_markup=build_reward_type_keyboard("admin_hpass:reward_type_select", "admin_hpass:main"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward_type_select:"))
async def admin_hpass_reward_type_select(callback: CallbackQuery, state: FSMContext) -> None:
    reward_type = (callback.data or "").split(":")[-1]
    await state.update_data(reward_type=reward_type)
    if reward_type == "currency":
        choices = await get_currency_choices()
        await edit_or_send(callback, "<b>💱 Валюта награды</b>\n\nВыбери валюту.", reply_markup=build_currency_choice_keyboard(choices, "admin_hpass:reward_currency", "admin_hpass:main"))
    elif reward_type == "pack":
        await show_pack_choices(callback, state, page=1)
    else:
        await show_card_choices(callback, state, page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward_currency:"))
async def admin_hpass_reward_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency_code = (callback.data or "").split(":")[-1]
    if currency_code == "none":
        await callback.answer("Для награды выбери валюту.", show_alert=True)
        return
    await state.update_data(currency_code=currency_code)
    await state.set_state(HockeyPassAdminStates.reward_amount)
    await edit_or_send(callback, ADMIN_HPASS_REWARD_AMOUNT_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


async def show_pack_choices(callback: CallbackQuery, state: FSMContext, page: int, search: str | None = None) -> None:
    await state.update_data(choice_type="pack", choice_search=search)
    choice_page = await get_pack_choices_page(page=page, search=search)
    await edit_or_send(callback, build_choice_page_text("🎁 Выбор пака", choice_page), reply_markup=build_choice_page_keyboard(choice_page, "admin_hpass:reward_pack", "admin_hpass:reward_pack_search", "admin_hpass:main"))


async def show_card_choices(callback: CallbackQuery, state: FSMContext, page: int, search: str | None = None) -> None:
    await state.update_data(choice_type="card", choice_search=search)
    choice_page = await get_card_choices_page(page=page, search=search)
    await edit_or_send(callback, build_choice_page_text("🃏 Выбор карточки", choice_page), reply_markup=build_choice_page_keyboard(choice_page, "admin_hpass:reward_card", "admin_hpass:reward_card_search", "admin_hpass:main"))


@router.callback_query(F.data.startswith("admin_hpass:reward_pack_page:"))
async def admin_hpass_reward_pack_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    await show_pack_choices(callback, state, page=page, search=data.get("choice_search"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward_card_page:"))
async def admin_hpass_reward_card_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    await show_card_choices(callback, state, page=page, search=data.get("choice_search"))
    await callback.answer()


@router.callback_query(F.data == "admin_hpass:reward_pack_search")
async def admin_hpass_reward_pack_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HockeyPassAdminStates.reward_search_pack)
    await edit_or_send(callback, ADMIN_HPASS_PACK_SEARCH_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_hpass:reward_card_search")
async def admin_hpass_reward_card_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HockeyPassAdminStates.reward_search_card)
    await edit_or_send(callback, ADMIN_HPASS_CARD_SEARCH_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.reward_search_pack))
async def admin_hpass_reward_pack_search_message(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    search = message.text or ""
    await state.update_data(choice_search=search)
    await state.set_state(None)
    choice_page = await get_pack_choices_page(page=1, search=search)
    await send_clean_message(
        message,
        build_choice_page_text("🎁 Выбор пака", choice_page),
        reply_markup=build_choice_page_keyboard(choice_page, "admin_hpass:reward_pack", "admin_hpass:reward_pack_search", "admin_hpass:main"),
    )


@router.message(StateFilter(HockeyPassAdminStates.reward_search_card))
async def admin_hpass_reward_card_search_message(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    search = message.text or ""
    await state.update_data(choice_search=search)
    await state.set_state(None)
    choice_page = await get_card_choices_page(page=1, search=search)
    await send_clean_message(
        message,
        build_choice_page_text("🃏 Выбор карточки", choice_page),
        reply_markup=build_choice_page_keyboard(choice_page, "admin_hpass:reward_card", "admin_hpass:reward_card_search", "admin_hpass:main"),
    )


@router.callback_query(F.data.startswith("admin_hpass:reward_pack:"))
async def admin_hpass_reward_pack_select(callback: CallbackQuery, state: FSMContext) -> None:
    pack_id = int((callback.data or "").split(":")[-1])
    await state.update_data(pack_id=pack_id, amount=1)
    await state.set_state(HockeyPassAdminStates.reward_title)
    await edit_or_send(callback, ADMIN_HPASS_REWARD_TITLE_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward_card:"))
async def admin_hpass_reward_card_select(callback: CallbackQuery, state: FSMContext) -> None:
    card_id = int((callback.data or "").split(":")[-1])
    await state.update_data(card_id=card_id, amount=1)
    await state.set_state(HockeyPassAdminStates.reward_title)
    await edit_or_send(callback, ADMIN_HPASS_REWARD_TITLE_TEXT, reply_markup=build_admin_cancel_keyboard())
    await callback.answer()


@router.message(StateFilter(HockeyPassAdminStates.reward_amount))
async def admin_hpass_reward_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    amount = parse_positive_int(message.text or "", min_value=1)
    if amount is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_NUMBER_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    data = await state.get_data()
    if data.get("edit_field") == "amount":
        await update_reward_basic_field(int(data["reward_id"]), "amount", amount)
        reward = await get_reward_profile(int(data["reward_id"]))
        await state.clear()
        if reward is not None:
            await send_clean_message(
                message,
                build_admin_reward_profile_text(reward),
                reply_markup=build_admin_reward_profile_keyboard(reward, int(data["page"])),
                image_path=reward.card_image_path or reward.pack_image_path,
            )
        else:
            await send_clean_message(message, ADMIN_HPASS_UPDATED_TEXT)
        return
    await state.update_data(amount=amount)
    await state.set_state(HockeyPassAdminStates.reward_title)
    await send_prompt(message, state, ADMIN_HPASS_REWARD_TITLE_TEXT, reply_markup=build_admin_cancel_keyboard())


@router.message(StateFilter(HockeyPassAdminStates.reward_title))
async def admin_hpass_reward_title(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw_title = message.text or ""
    title = "" if raw_title.strip() == "-" else validate_title(raw_title)
    if title is None:
        await send_prompt(message, state, ADMIN_HPASS_BAD_TITLE_TEXT, reply_markup=build_admin_cancel_keyboard())
        return
    data = await state.get_data()
    if data.get("edit_field") == "title":
        await update_reward_basic_field(int(data["reward_id"]), "title", title)
        reward = await get_reward_profile(int(data["reward_id"]))
        await state.clear()
        if reward is not None:
            await send_clean_message(
                message,
                build_admin_reward_profile_text(reward),
                reply_markup=build_admin_reward_profile_keyboard(reward, int(data["page"])),
                image_path=reward.card_image_path or reward.pack_image_path,
            )
        else:
            await send_clean_message(message, ADMIN_HPASS_UPDATED_TEXT)
        return
    await state.update_data(title=title)
    draft = build_reward_draft_from_state(await state.get_data())
    await state.set_state(None)
    await send_prompt(message, state, build_reward_draft_text(draft), reply_markup=build_confirm_reward_keyboard())


def build_reward_draft_from_state(data: dict) -> RewardDraft:
    return RewardDraft(
        pass_id=int(data["pass_id"]),
        level=int(data["level"]),
        track=data["track"],
        reward_type=data["reward_type"],
        title=data.get("title", ""),
        amount=int(data.get("amount", 0)),
        currency_code=data.get("currency_code"),
        pack_id=data.get("pack_id"),
        card_id=data.get("card_id"),
    )


@router.callback_query(F.data == "admin_hpass:reward_confirm")
async def admin_hpass_reward_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        draft = build_reward_draft_from_state(data)
    except (KeyError, TypeError, ValueError):
        await callback.answer("Обнови раздел и добавь награду заново.", show_alert=True)
        return

    if await get_pass_profile(draft.pass_id) is None:
        await callback.answer("Обнови раздел и выбери Pass заново.", show_alert=True)
        return

    if data.get("replace_reward_id"):
        reward_id = int(data["replace_reward_id"])
        saved = await replace_reward_payload(draft, reward_id)
        if not saved:
            await callback.answer("Обнови раздел и выбери награду заново.", show_alert=True)
            return
    else:
        created_reward_id = await create_reward(draft)
        if created_reward_id is None:
            await callback.answer("Обнови раздел и выбери Pass заново.", show_alert=True)
            return
        reward_id = int(created_reward_id)

    await clear_admin_step(callback, state)
    await state.clear()
    await callback.answer(ADMIN_HPASS_REWARD_SAVED_TEXT)
    await show_admin_reward_profile(callback, reward_id, 1)


@router.callback_query(F.data.startswith("admin_hpass:reward_toggle:"))
async def admin_hpass_reward_toggle(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    result = await toggle_reward_active(int(reward_id))
    if result is None:
        await callback.answer(ADMIN_HPASS_REWARD_NOT_FOUND_TEXT, show_alert=True)
        return
    await callback.answer(ADMIN_HPASS_UPDATED_TEXT)
    await show_admin_reward_profile(callback, int(reward_id), int(page))


@router.callback_query(F.data.startswith("admin_hpass:reward_delete_ask:"))
async def admin_hpass_reward_delete_ask(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    reward = await get_reward_profile(int(reward_id))
    if reward is None:
        await callback.answer(ADMIN_HPASS_REWARD_NOT_FOUND_TEXT, show_alert=True)
        return
    await edit_or_send(callback, build_admin_reward_delete_text(reward), reply_markup=build_admin_reward_delete_keyboard(reward, int(page)))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward_delete:"))
async def admin_hpass_reward_delete(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    reward = await get_reward_profile(int(reward_id))
    pass_id = reward.pass_id if reward else None
    await delete_reward(int(reward_id))
    await callback.answer(ADMIN_HPASS_REWARD_DELETED_TEXT)
    if pass_id:
        await show_admin_rewards_page(callback, pass_id, int(page))
    else:
        await show_admin_main(callback)


@router.callback_query(F.data.startswith("admin_hpass:reward_edit:"))
async def admin_hpass_reward_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, field, reward_id, page = (callback.data or "").split(":")
    reward = await get_reward_profile(int(reward_id))
    if reward is None:
        await callback.answer(ADMIN_HPASS_REWARD_NOT_FOUND_TEXT, show_alert=True)
        return
    await state.update_data(edit_field=field, reward_id=int(reward_id), pass_id=reward.pass_id, page=int(page))
    if field == "level":
        await state.set_state(HockeyPassAdminStates.reward_level)
        prompt = ADMIN_HPASS_REWARD_LEVEL_TEXT
    elif field == "amount":
        await state.set_state(HockeyPassAdminStates.reward_amount)
        prompt = ADMIN_HPASS_REWARD_AMOUNT_TEXT
    else:
        await state.set_state(HockeyPassAdminStates.reward_title)
        prompt = ADMIN_HPASS_REWARD_TITLE_TEXT
    await edit_or_send(callback, prompt, reply_markup=build_admin_cancel_keyboard(f"admin_hpass:reward:{reward_id}:{page}"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:reward_track:"))
async def admin_hpass_reward_track_edit(callback: CallbackQuery) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    await edit_or_send(callback, "<b>🌿 Ветка награды</b>\n\nВыбери новое место награды.", reply_markup=build_track_keyboard(f"admin_hpass:set_reward_track:{reward_id}:{page}", f"admin_hpass:reward:{reward_id}:{page}"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hpass:set_reward_track:"))
async def admin_hpass_set_reward_track(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    reward_id = int(parts[2])
    page = int(parts[3])
    track = parts[4]
    await update_reward_basic_field(reward_id, "track", track)
    await callback.answer(ADMIN_HPASS_UPDATED_TEXT)
    await show_admin_reward_profile(callback, reward_id, page)


@router.callback_query(F.data.startswith("admin_hpass:reward_replace:"))
async def admin_hpass_reward_replace(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, reward_id, page = (callback.data or "").split(":")
    reward = await get_reward_profile(int(reward_id))
    if reward is None:
        await callback.answer(ADMIN_HPASS_REWARD_NOT_FOUND_TEXT, show_alert=True)
        return
    await state.update_data(
        mode="replace",
        replace_reward_id=int(reward_id),
        pass_id=reward.pass_id,
        level=reward.level,
        track=reward.track,
        page=int(page),
    )
    await edit_or_send(callback, "<b>🎁 Новая награда</b>\n\nВыбери тип новой награды.", reply_markup=build_reward_type_keyboard("admin_hpass:reward_type_select", f"admin_hpass:reward:{reward_id}:{page}"))
    await callback.answer()


@router.callback_query(F.data == "admin_hpass:page_info")
@router.callback_query(F.data == "hpass:page_info")
async def hpass_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Используй стрелки для навигации.")
