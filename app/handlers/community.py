from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.community import (
    build_admin_clans_main_keyboard,
    build_admin_trades_main_keyboard,
    build_clan_profile_keyboard,
    build_clans_list_keyboard,
    build_clans_main_keyboard,
    build_community_main_keyboard,
    build_currency_choice_keyboard,
    build_player_profile_keyboard,
    build_players_keyboard,
    build_text_cancel_keyboard,
    build_trade_cards_keyboard,
    build_trade_offer_profile_keyboard,
    build_trade_offers_keyboard,
    build_trade_wanted_keyboard,
    build_trades_main_keyboard,
    build_wanted_cards_keyboard,
)
from app.services.community import (
    COMMUNITY_PER_PAGE,
    accept_trade_offer,
    cancel_trade_offer,
    create_clan,
    create_trade_offer,
    delete_clan,
    delete_trade_offer,
    get_available_user_cards_page,
    get_card_choices_page,
    get_clan_profile,
    get_clans_page,
    get_players_page,
    get_public_player_profile,
    get_selected_card_choices,
    get_selected_user_cards,
    get_trade_offer_profile,
    get_trade_offers_page,
    get_user_clan,
    get_user_id_by_telegram_id,
    join_clan,
    leave_clan,
    toggle_clan_active,
)
from app.services.currencies import get_user_balances
from app.states.community import CommunityStates
from app.texts.community import (
    ADMIN_CLANS_TEXT,
    ADMIN_TRADES_TEXT,
    CLAN_CREATE_DESCRIPTION_TEXT,
    CLAN_CREATE_NAME_TEXT,
    CLAN_SEARCH_TEXT,
    CLANS_MAIN_TEXT,
    COMMUNITY_MAIN_TEXT,
    PLAYERS_SEARCH_TEXT,
    TRADE_CREATE_TEXT,
    TRADE_CURRENCY_AMOUNT_TEXT,
    TRADE_MAIN_TEXT,
    TRADE_WANTED_CARDS_TEXT,
    TRADE_WANTED_TEXT,
    build_action_result_text,
    build_clan_profile_text,
    build_clans_page_text,
    build_players_page_text,
    build_public_player_profile_text,
    build_trade_card_choices_page_text,
    build_trade_offer_profile_text,
    build_trade_offers_page_text,
    build_trade_user_cards_page_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin

router = Router()

COMMUNITY_BUTTON_TEXT = "🤝 Сообщество"
ADMIN_CLANS_BUTTON_TEXT = "🤝 Кланы"
ADMIN_TRADES_BUTTON_TEXT = "🔁 Обмены"


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        if message.photo:
            await message.delete()
            await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)


async def get_current_user_id(message_or_callback) -> int | None:
    from_user = getattr(message_or_callback, "from_user", None)
    if from_user is None:
        return None
    return get_user_id_by_telegram_id(from_user.id)


@router.message(F.text == COMMUNITY_BUTTON_TEXT)
async def community_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await safe_delete_message(message)
    await message.answer(COMMUNITY_MAIN_TEXT, reply_markup=build_community_main_keyboard())


@router.callback_query(F.data == "community:main")
async def community_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(callback, COMMUNITY_MAIN_TEXT, reply_markup=build_community_main_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("community:players:"))
async def players_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    players_page = await get_players_page(page=page, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(
        callback,
        build_players_page_text(players_page),
        reply_markup=build_players_keyboard(players_page.players, players_page.page, players_page.pages_count),
    )
    await callback.answer()


@router.callback_query(F.data == "community:players_search")
async def players_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CommunityStates.search_players)
    await edit_or_send(callback, PLAYERS_SEARCH_TEXT, reply_markup=build_text_cancel_keyboard("community:main"))
    await callback.answer()


@router.message(CommunityStates.search_players)
async def players_search_value(message: Message, state: FSMContext) -> None:
    search = message.text or ""
    await safe_delete_message(message)
    await state.clear()
    players_page = await get_players_page(page=1, per_page=COMMUNITY_PER_PAGE, search=search)
    await message.answer(
        build_players_page_text(players_page),
        reply_markup=build_players_keyboard(players_page.players, players_page.page, players_page.pages_count),
    )


@router.callback_query(F.data.startswith("community:player:"))
async def player_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    player_id = int(parts[2])
    page = int(parts[3])
    viewer_user_id = await get_current_user_id(callback)
    profile = await get_public_player_profile(player_id, viewer_user_id=viewer_user_id)
    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    await edit_or_send(
        callback,
        build_public_player_profile_text(profile),
        reply_markup=build_player_profile_keyboard(player_id=player_id, page=page),
    )
    await callback.answer()


@router.callback_query(F.data == "community:trades")
async def trades_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(callback, TRADE_MAIN_TEXT, reply_markup=build_trades_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "community:trade_create")
async def trade_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    await state.update_data(offered_user_card_ids=[], wanted_card_ids=[], offer_card_search=None, wanted_card_search=None)
    page = await get_available_user_cards_page(user_id=user_id, page=1, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(
        callback,
        TRADE_CREATE_TEXT + "\n\n" + build_trade_user_cards_page_text(page),
        reply_markup=build_trade_cards_keyboard(page.cards, page.page, page.pages_count, page.selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_offer_cards:"))
async def trade_offer_cards(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    data = await state.get_data()
    selected_ids = data.get("offered_user_card_ids", [])
    search = data.get("offer_card_search")
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    page = await get_available_user_cards_page(user_id=user_id, page=page_num, per_page=COMMUNITY_PER_PAGE, search=search, selected_ids=selected_ids)
    await edit_or_send(
        callback,
        build_trade_user_cards_page_text(page),
        reply_markup=build_trade_cards_keyboard(page.cards, page.page, page.pages_count, page.selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_add_offer_card:"))
async def trade_add_offer_card(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    user_card_id = int(parts[2])
    page_num = int(parts[3])
    data = await state.get_data()
    selected_ids = list(data.get("offered_user_card_ids", []))
    if len(selected_ids) >= 3:
        await callback.answer("Можно выбрать до 3 карточек", show_alert=True)
        return
    if user_card_id not in selected_ids:
        selected_ids.append(user_card_id)
    await state.update_data(offered_user_card_ids=selected_ids)
    page = await get_available_user_cards_page(
        user_id=user_id,
        page=page_num,
        per_page=COMMUNITY_PER_PAGE,
        search=data.get("offer_card_search"),
        selected_ids=selected_ids,
    )
    selected_cards = await get_selected_user_cards(user_id=user_id, selected_ids=selected_ids)
    selected_text = "\n".join(f"✅ {card.name} • {card.overall} OVR" for card in selected_cards)
    await edit_or_send(
        callback,
        build_trade_user_cards_page_text(page) + (f"\n\n<b>Выбрано</b>\n{selected_text}" if selected_text else ""),
        reply_markup=build_trade_cards_keyboard(page.cards, page.page, page.pages_count, selected_ids),
    )
    await callback.answer("Карточка добавлена")


@router.callback_query(F.data == "community:trade_search_offer_card")
async def trade_search_offer_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CommunityStates.trade_search_offer_card)
    await edit_or_send(callback, "<b>🔎 Поиск карточки</b>\n\nВведи имя, команду, редкость или позицию.", reply_markup=build_text_cancel_keyboard("community:trade_create"))
    await callback.answer()


@router.message(CommunityStates.trade_search_offer_card)
async def trade_search_offer_card_value(message: Message, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(message.from_user.id) if message.from_user else None
    if user_id is None:
        return
    search = message.text or ""
    await safe_delete_message(message)
    await state.update_data(offer_card_search=search)
    await state.set_state(None)
    data = await state.get_data()
    selected_ids = data.get("offered_user_card_ids", [])
    page = await get_available_user_cards_page(user_id=user_id, page=1, per_page=COMMUNITY_PER_PAGE, search=search, selected_ids=selected_ids)
    await message.answer(
        build_trade_user_cards_page_text(page),
        reply_markup=build_trade_cards_keyboard(page.cards, page.page, page.pages_count, selected_ids),
    )


@router.callback_query(F.data == "community:trade_wanted")
async def trade_wanted(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("offered_user_card_ids"):
        await callback.answer("Сначала выбери карточки", show_alert=True)
        return
    await edit_or_send(callback, TRADE_WANTED_TEXT, reply_markup=build_trade_wanted_keyboard())
    await callback.answer()


@router.callback_query(F.data == "community:trade_wanted_currency")
async def trade_wanted_currency(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    balances = await get_user_balances(user_id)
    await edit_or_send(callback, "<b>💰 Валюта обмена</b>\n\nВыбери валюту, которую хочешь получить.", reply_markup=build_currency_choice_keyboard(balances))
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_currency:"))
async def trade_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency_code = callback.data.split(":")[-1]
    await state.update_data(wanted_currency_code=currency_code)
    await state.set_state(CommunityStates.trade_currency_amount)
    await edit_or_send(callback, TRADE_CURRENCY_AMOUNT_TEXT, reply_markup=build_text_cancel_keyboard("community:trades"))
    await callback.answer()


@router.message(CommunityStates.trade_currency_amount)
async def trade_currency_amount(message: Message, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(message.from_user.id) if message.from_user else None
    if user_id is None:
        return
    raw_amount = (message.text or "").replace(" ", "")
    await safe_delete_message(message)
    if not raw_amount.isdigit() or int(raw_amount) <= 0:
        await message.answer("🏒 Введи сумму числом больше нуля.", reply_markup=build_text_cancel_keyboard("community:trades"))
        return
    data = await state.get_data()
    result = await create_trade_offer(
        creator_user_id=user_id,
        offered_user_card_ids=data.get("offered_user_card_ids", []),
        wanted_type="currency",
        wanted_currency_code=data.get("wanted_currency_code"),
        wanted_currency_amount=int(raw_amount),
    )
    await state.clear()
    await message.answer(build_action_result_text(result.title, result.description), reply_markup=build_trades_main_keyboard())


@router.callback_query(F.data.startswith("community:trade_wanted_cards:"))
async def trade_wanted_cards(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    selected_card_ids = data.get("wanted_card_ids", [])
    page = await get_card_choices_page(page=page_num, per_page=COMMUNITY_PER_PAGE, search=data.get("wanted_card_search"), selected_card_ids=selected_card_ids)
    await edit_or_send(
        callback,
        TRADE_WANTED_CARDS_TEXT + "\n\n" + build_trade_card_choices_page_text(page),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_add_wanted_card:"))
async def trade_add_wanted_card(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page_num = int(parts[3])
    data = await state.get_data()
    selected_card_ids = list(data.get("wanted_card_ids", []))
    if len(selected_card_ids) >= 3:
        await callback.answer("Можно выбрать до 3 карточек", show_alert=True)
        return
    selected_card_ids.append(card_id)
    await state.update_data(wanted_card_ids=selected_card_ids)
    page = await get_card_choices_page(page=page_num, per_page=COMMUNITY_PER_PAGE, search=data.get("wanted_card_search"), selected_card_ids=selected_card_ids)
    selected_cards = await get_selected_card_choices(selected_card_ids)
    selected_text = "\n".join(f"✅ {card.name} • {card.overall} OVR" for card in selected_cards)
    await edit_or_send(
        callback,
        build_trade_card_choices_page_text(page) + (f"\n\n<b>Выбрано</b>\n{selected_text}" if selected_text else ""),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids),
    )
    await callback.answer("Карточка добавлена")


@router.callback_query(F.data == "community:trade_search_wanted_card")
async def trade_search_wanted_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CommunityStates.trade_search_wanted_card)
    await edit_or_send(callback, "<b>🔎 Поиск карточки</b>\n\nВведи имя, команду, редкость или позицию.", reply_markup=build_text_cancel_keyboard("community:trade_wanted_cards:1"))
    await callback.answer()


@router.message(CommunityStates.trade_search_wanted_card)
async def trade_search_wanted_card_value(message: Message, state: FSMContext) -> None:
    search = message.text or ""
    await safe_delete_message(message)
    await state.update_data(wanted_card_search=search)
    await state.set_state(None)
    data = await state.get_data()
    selected_card_ids = data.get("wanted_card_ids", [])
    page = await get_card_choices_page(page=1, per_page=COMMUNITY_PER_PAGE, search=search, selected_card_ids=selected_card_ids)
    await message.answer(
        build_trade_card_choices_page_text(page),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids),
    )


@router.callback_query(F.data == "community:trade_publish_cards")
async def trade_publish_cards(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    data = await state.get_data()
    result = await create_trade_offer(
        creator_user_id=user_id,
        offered_user_card_ids=data.get("offered_user_card_ids", []),
        wanted_type="cards",
        wanted_card_ids=data.get("wanted_card_ids", []),
    )
    await state.clear()
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_trades_main_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_list:"))
async def trade_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    mode = parts[2]
    page_num = int(parts[3])
    user_id = await get_current_user_id(callback)
    page = await get_trade_offers_page(mode=mode, user_id=user_id, page=page_num, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(callback, build_trade_offers_page_text(page), reply_markup=build_trade_offers_keyboard(page.offers, mode, page.page, page.pages_count))
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_view:"))
async def trade_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    mode = parts[3]
    page_num = int(parts[4])
    offer = await get_trade_offer_profile(offer_id)
    if offer is None:
        await callback.answer("Обмен не найден", show_alert=True)
        return
    user_id = await get_current_user_id(callback)
    await edit_or_send(callback, build_trade_offer_profile_text(offer), reply_markup=build_trade_offer_profile_keyboard(offer, user_id, mode, page_num))
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_accept:"))
async def trade_accept(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    mode = parts[3]
    page_num = int(parts[4])
    result = await accept_trade_offer(offer_id, user_id)
    offer = await get_trade_offer_profile(offer_id)
    if offer:
        await edit_or_send(callback, build_trade_offer_profile_text(offer) + f"\n\n{result.description}", reply_markup=build_trade_offer_profile_keyboard(offer, user_id, mode, page_num))
    else:
        await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_trades_main_keyboard())
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("community:trade_cancel:"))
async def trade_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    result = await cancel_trade_offer(offer_id, user_id=user_id)
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_trades_main_keyboard())
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data == "community:clans")
async def clans_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    clan = await get_user_clan(user_id) if user_id else None
    await edit_or_send(callback, CLANS_MAIN_TEXT, reply_markup=build_clans_main_keyboard(has_clan=clan is not None))
    await callback.answer()


@router.callback_query(F.data.startswith("community:clan_list:"))
async def clan_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    page = await get_clans_page(page=page_num, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(callback, build_clans_page_text(page), reply_markup=build_clans_list_keyboard(page.clans, page.page, page.pages_count))
    await callback.answer()


@router.callback_query(F.data == "community:clan_search")
async def clan_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CommunityStates.clan_search)
    await edit_or_send(callback, CLAN_SEARCH_TEXT, reply_markup=build_text_cancel_keyboard("community:clans"))
    await callback.answer()


@router.message(CommunityStates.clan_search)
async def clan_search_value(message: Message, state: FSMContext) -> None:
    search = message.text or ""
    await safe_delete_message(message)
    await state.clear()
    page = await get_clans_page(page=1, per_page=COMMUNITY_PER_PAGE, search=search)
    await message.answer(build_clans_page_text(page), reply_markup=build_clans_list_keyboard(page.clans, page.page, page.pages_count))


@router.callback_query(F.data.startswith("community:clan_view:"))
async def clan_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    clan_id = int(parts[2])
    page_num = int(parts[3])
    user_id = await get_current_user_id(callback)
    profile = await get_clan_profile(clan_id, viewer_user_id=user_id)
    if profile is None:
        await callback.answer("Клан не найден", show_alert=True)
        return
    await edit_or_send(callback, build_clan_profile_text(profile), reply_markup=build_clan_profile_keyboard(profile, page_num))
    await callback.answer()


@router.callback_query(F.data == "community:my_clan")
async def my_clan(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    profile = await get_user_clan(user_id) if user_id else None
    if profile is None:
        await callback.answer("Ты пока не состоишь в клане", show_alert=True)
        return
    await edit_or_send(callback, build_clan_profile_text(profile), reply_markup=build_clan_profile_keyboard(profile, 1))
    await callback.answer()


@router.callback_query(F.data == "community:clan_create")
async def clan_create(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    if await get_user_clan(user_id):
        await callback.answer("Ты уже состоишь в клане", show_alert=True)
        return
    await state.clear()
    await state.set_state(CommunityStates.clan_create_name)
    await edit_or_send(callback, CLAN_CREATE_NAME_TEXT, reply_markup=build_text_cancel_keyboard("community:clans"))
    await callback.answer()


@router.message(CommunityStates.clan_create_name)
async def clan_create_name(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    await state.update_data(clan_name=message.text or "")
    await state.set_state(CommunityStates.clan_create_description)
    await message.answer(CLAN_CREATE_DESCRIPTION_TEXT, reply_markup=build_text_cancel_keyboard("community:clans"))


@router.message(CommunityStates.clan_create_description)
async def clan_create_description(message: Message, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(message.from_user.id) if message.from_user else None
    if user_id is None:
        return
    await safe_delete_message(message)
    data = await state.get_data()
    result = await create_clan(user_id=user_id, name=data.get("clan_name", ""), description=message.text or "")
    await state.clear()
    await message.answer(build_action_result_text(result.title, result.description), reply_markup=build_clans_main_keyboard(has_clan=result.ok))


@router.callback_query(F.data.startswith("community:clan_join:"))
async def clan_join(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    clan_id = int(parts[2])
    result = await join_clan(user_id, clan_id)
    profile = await get_clan_profile(clan_id, viewer_user_id=user_id)
    if profile:
        await edit_or_send(callback, build_clan_profile_text(profile) + f"\n\n{result.description}", reply_markup=build_clan_profile_keyboard(profile, 1))
    else:
        await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_clans_main_keyboard(has_clan=False))
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data == "community:clan_leave")
async def clan_leave(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    result = await leave_clan(user_id)
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_clans_main_keyboard(has_clan=False))
    await callback.answer(result.title, show_alert=not result.ok)


@router.message(F.text == ADMIN_CLANS_BUTTON_TEXT)
async def admin_clans_button(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await safe_delete_message(message)
    await message.answer(ADMIN_CLANS_TEXT, reply_markup=build_admin_clans_main_keyboard())


@router.callback_query(F.data.startswith("admin_clans:list:"))
async def admin_clans_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    page = await get_clans_page(page=page_num, per_page=COMMUNITY_PER_PAGE, include_inactive=True)
    await edit_or_send(callback, build_clans_page_text(page, admin=True), reply_markup=build_clans_list_keyboard(page.clans, page.page, page.pages_count, admin=True))
    await callback.answer()


@router.callback_query(F.data == "admin_clans:search")
async def admin_clans_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CommunityStates.admin_clan_search)
    await edit_or_send(callback, CLAN_SEARCH_TEXT, reply_markup=build_text_cancel_keyboard("admin_clans:list:1"))
    await callback.answer()


@router.message(CommunityStates.admin_clan_search)
async def admin_clans_search_value(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    search = message.text or ""
    await safe_delete_message(message)
    await state.clear()
    page = await get_clans_page(page=1, per_page=COMMUNITY_PER_PAGE, search=search, include_inactive=True)
    await message.answer(build_clans_page_text(page, admin=True), reply_markup=build_clans_list_keyboard(page.clans, page.page, page.pages_count, admin=True))


@router.callback_query(F.data.startswith("admin_clans:view:"))
async def admin_clans_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    clan_id = int(parts[2])
    page_num = int(parts[3])
    profile = await get_clan_profile(clan_id)
    if profile is None:
        await callback.answer("Клан не найден", show_alert=True)
        return
    await edit_or_send(callback, build_clan_profile_text(profile, admin=True), reply_markup=build_clan_profile_keyboard(profile, page_num, admin=True))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_clans:toggle:"))
async def admin_clans_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    clan_id = int(parts[2])
    page_num = int(parts[3])
    result = await toggle_clan_active(clan_id)
    profile = await get_clan_profile(clan_id)
    if profile:
        await edit_or_send(callback, build_clan_profile_text(profile, admin=True) + f"\n\n{result.description}", reply_markup=build_clan_profile_keyboard(profile, page_num, admin=True))
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("admin_clans:delete:"))
async def admin_clans_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    clan_id = int(parts[2])
    result = await delete_clan(clan_id)
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_admin_clans_main_keyboard())
    await callback.answer(result.title, show_alert=not result.ok)


@router.message(F.text == ADMIN_TRADES_BUTTON_TEXT)
async def admin_trades_button(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await safe_delete_message(message)
    await message.answer(ADMIN_TRADES_TEXT, reply_markup=build_admin_trades_main_keyboard())


@router.callback_query(F.data.startswith("admin_trades:list:"))
async def admin_trades_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    page = await get_trade_offers_page(mode="admin", page=page_num, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(callback, build_trade_offers_page_text(page), reply_markup=build_trade_offers_keyboard(page.offers, "admin", page.page, page.pages_count))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_trades:cancel:"))
async def admin_trade_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    result = await cancel_trade_offer(offer_id, admin=True)
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_admin_trades_main_keyboard())
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("admin_trades:delete:"))
async def admin_trade_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    result = await delete_trade_offer(offer_id)
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_admin_trades_main_keyboard())
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("admin_trades:view:"))
async def admin_trade_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    page_num = int(parts[3])
    offer = await get_trade_offer_profile(offer_id)
    if offer is None:
        await callback.answer("Обмен не найден", show_alert=True)
        return
    await edit_or_send(callback, build_trade_offer_profile_text(offer), reply_markup=build_trade_offer_profile_keyboard(offer, None, "admin", page_num, admin=True))
    await callback.answer()
