from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.keyboards.community import (
    build_admin_clans_main_keyboard,
    build_admin_trades_main_keyboard,
    build_clan_kick_confirm_keyboard,
    build_clan_manage_keyboard,
    build_clan_requests_keyboard,
    build_clan_requests_shortcut_keyboard,
    build_clan_member_manage_keyboard,
    build_clan_member_stats_keyboard,
    build_clan_profile_keyboard,
    build_clans_list_keyboard,
    build_clans_main_keyboard,
    build_community_main_keyboard,
    build_currency_choice_keyboard,
    build_direct_trade_players_keyboard,
    build_player_profile_keyboard,
    build_players_keyboard,
    build_text_cancel_keyboard,
    build_trade_cards_keyboard,
    build_trade_cosmetics_keyboard,
    build_trade_offer_profile_keyboard,
    build_trade_offers_keyboard,
    build_trade_wanted_keyboard,
    build_trades_main_keyboard,
    build_wanted_cards_keyboard,
    build_wanted_cosmetics_keyboard,
)
from app.services.community import (
    COMMUNITY_PER_PAGE,
    accept_trade_offer,
    cancel_trade_offer,
    create_clan,
    count_pending_requests,
    get_clan_leaders_telegram_ids,
    get_clan_member_row_public,
    get_clan_member_telegram_id,
    get_pending_requests,
    resolve_join_request,
    kick_clan_member,
    toggle_clan_vice,
    create_trade_offer,
    decline_trade_offer,
    delete_clan,
    delete_trade_offer,
    get_available_user_cards_page,
    get_available_user_cosmetics_page,
    get_card_choices_page,
    get_cosmetic_choices_page,
    get_clan_profile,
    get_clan_war_player_rating,
    get_clan_global_rating,
    get_war2_clan_player_contribution,
    get_war2_clan_rating,
    get_clans_page,
    get_direct_trade_players_page,
    get_players_page,
    get_public_player_profile,
    get_selected_card_choices,
    get_selected_cosmetic_choices,
    get_selected_user_cards,
    get_selected_user_cosmetics,
    get_trade_offer_creator_telegram_id,
    get_trade_offer_profile,
    get_trade_offers_page,
    get_user_clan,
    get_user_id_by_telegram_id,
    join_clan,
    leave_clan,
    toggle_clan_active,
)
from app.services.currencies import get_user_balances
from app.services.card_sorting import set_user_card_sort_order
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
    TRADE_DIRECT_PLAYERS_TEXT,
    TRADE_DIRECT_SEARCH_TEXT,
    TRADE_MAIN_TEXT,
    TRADE_WANTED_CARDS_TEXT,
    TRADE_WANTED_COSMETICS_TEXT,
    TRADE_WANTED_TEXT,
    build_action_result_text,
    build_clan_member_manage_text,
    build_clan_profile_text,
    build_clan_requests_text,
    CLAN_MANAGE_TEXT,
    build_clans_page_text,
    build_players_page_text,
    build_public_player_profile_text,
    build_trade_card_choices_page_text,
    build_trade_cosmetic_choices_page_text,
    build_trade_cosmetics_page_text,
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


def build_direct_trade_notification_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять", callback_data=f"community:trade_accept:{offer_id}:incoming:1")],
            [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"community:trade_decline:{offer_id}:incoming:1")],
            [InlineKeyboardButton(text="👀 Посмотреть обмен", callback_data=f"community:trade_view:{offer_id}:incoming:1")],
        ]
    )


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


@router.callback_query(F.data == "community:trade_direct_search")
async def trade_direct_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CommunityStates.trade_direct_player_search)
    await edit_or_send(callback, TRADE_DIRECT_SEARCH_TEXT, reply_markup=build_text_cancel_keyboard("community:trades"))
    await callback.answer()


@router.message(CommunityStates.trade_direct_player_search)
async def trade_direct_search_value(message: Message, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(message.from_user.id) if message.from_user else None
    if user_id is None:
        return
    search = message.text or ""
    await safe_delete_message(message)
    await state.clear()
    page = await get_direct_trade_players_page(user_id=user_id, page=1, per_page=COMMUNITY_PER_PAGE, search=search)
    await message.answer(
        TRADE_DIRECT_PLAYERS_TEXT + "\n\n" + build_players_page_text(page),
        reply_markup=build_direct_trade_players_keyboard(page.players, page.page, page.pages_count),
    )


@router.callback_query(F.data.startswith("community:trade_direct_players:"))
async def trade_direct_players_page(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    page = await get_direct_trade_players_page(user_id=user_id, page=page_num, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(
        callback,
        TRADE_DIRECT_PLAYERS_TEXT + "\n\n" + build_players_page_text(page),
        reply_markup=build_direct_trade_players_keyboard(page.players, page.page, page.pages_count),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_direct_player:"))
async def trade_direct_player_select(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    target_user_id = int(parts[2])
    await state.update_data(
        offered_user_card_ids=[],
        offered_user_cosmetic_ids=[],
        wanted_card_ids=[],
        wanted_cosmetic_item_ids=[],
        offer_card_search=None,
        wanted_card_search=None,
        target_user_id=target_user_id,
    )
    page = await get_available_user_cards_page(user_id=user_id, page=1, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(
        callback,
        TRADE_CREATE_TEXT + "\n\n🎯 Личное предложение выбранному игроку.\n\n" + build_trade_user_cards_page_text(page),
        reply_markup=build_trade_cards_keyboard(page.cards, page.page, page.pages_count, page.selected_ids, page.sort_order),
    )
    await callback.answer("Игрок выбран")


@router.callback_query(F.data == "community:trade_create")
async def trade_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    await state.update_data(
        offered_user_card_ids=[], offered_user_cosmetic_ids=[], wanted_card_ids=[],
        wanted_cosmetic_item_ids=[], offer_card_search=None, wanted_card_search=None, target_user_id=None
    )
    page = await get_available_user_cards_page(user_id=user_id, page=1, per_page=COMMUNITY_PER_PAGE)
    await edit_or_send(
        callback,
        TRADE_CREATE_TEXT + "\n\n" + build_trade_user_cards_page_text(page),
        reply_markup=build_trade_cards_keyboard(page.cards, page.page, page.pages_count, page.selected_ids, page.sort_order),
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
        reply_markup=build_trade_cards_keyboard(
            page.cards, page.page, page.pages_count, page.selected_ids, page.sort_order,
            bool(page.selected_ids or data.get("offered_user_cosmetic_ids")),
        ),
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
        reply_markup=build_trade_cards_keyboard(
            page.cards, page.page, page.pages_count, selected_ids, page.sort_order,
            bool(selected_ids or data.get("offered_user_cosmetic_ids")),
        ),
    )
    await callback.answer("Карточка добавлена")


@router.callback_query(F.data.startswith("community:trade_sort_offer:"))
async def trade_sort_offer(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    sort_order = (callback.data or "").split(":")[-1]
    await set_user_card_sort_order(user_id, sort_order)
    data = await state.get_data()
    selected_ids = data.get("offered_user_card_ids", [])
    page = await get_available_user_cards_page(
        user_id=user_id, page=1, per_page=COMMUNITY_PER_PAGE,
        search=data.get("offer_card_search"), selected_ids=selected_ids,
    )
    await edit_or_send(
        callback, build_trade_user_cards_page_text(page),
        reply_markup=build_trade_cards_keyboard(
            page.cards, page.page, page.pages_count, selected_ids, page.sort_order,
            bool(selected_ids or data.get("offered_user_cosmetic_ids")),
        ),
    )
    await callback.answer("Сортировка изменена")


@router.callback_query(F.data.startswith("community:trade_offer_cosmetics:"))
async def trade_offer_cosmetics(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    data = await state.get_data()
    selected_ids = data.get("offered_user_cosmetic_ids", [])
    page_num = int((callback.data or "").split(":")[-1])
    page = await get_available_user_cosmetics_page(
        user_id=user_id, page=page_num, per_page=COMMUNITY_PER_PAGE, selected_ids=selected_ids,
    )
    selected = await get_selected_user_cosmetics(user_id, selected_ids)
    selected_text = "\n".join(f"✅ {item.title} · экземпляр #{item.id}" for item in selected)
    text = build_trade_cosmetics_page_text(page)
    if selected_text:
        text += f"\n\n<b>Выбрано</b>\n{selected_text}"
    has_any = bool(selected_ids or data.get("offered_user_card_ids"))
    await edit_or_send(
        callback, text,
        reply_markup=build_trade_cosmetics_keyboard(page.items, page.page, page.pages_count, selected_ids, has_any),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_add_offer_cosmetic:"))
async def trade_add_offer_cosmetic(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    owned_id = int(parts[2])
    page_num = int(parts[3])
    data = await state.get_data()
    selected_ids = list(data.get("offered_user_cosmetic_ids", []))
    if len(selected_ids) >= 3:
        await callback.answer("Можно выбрать до 3 экземпляров косметики", show_alert=True)
        return
    if owned_id not in selected_ids:
        selected_ids.append(owned_id)
    await state.update_data(offered_user_cosmetic_ids=selected_ids)
    page = await get_available_user_cosmetics_page(
        user_id=user_id, page=page_num, per_page=COMMUNITY_PER_PAGE, selected_ids=selected_ids,
    )
    selected = await get_selected_user_cosmetics(user_id, selected_ids)
    selected_text = "\n".join(f"✅ {item.title} · экземпляр #{item.id}" for item in selected)
    await edit_or_send(
        callback,
        build_trade_cosmetics_page_text(page) + (f"\n\n<b>Выбрано</b>\n{selected_text}" if selected_text else ""),
        reply_markup=build_trade_cosmetics_keyboard(page.items, page.page, page.pages_count, selected_ids, True),
    )
    await callback.answer("Экземпляр косметики добавлен")


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
        reply_markup=build_trade_cards_keyboard(
            page.cards, page.page, page.pages_count, selected_ids, page.sort_order,
            bool(selected_ids or data.get("offered_user_cosmetic_ids")),
        ),
    )


@router.callback_query(F.data == "community:trade_wanted")
async def trade_wanted(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("offered_user_card_ids") and not data.get("offered_user_cosmetic_ids"):
        await callback.answer("Сначала выбери карточки или косметику", show_alert=True)
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
        offered_user_cosmetic_ids=data.get("offered_user_cosmetic_ids", []),
        wanted_type="currency",
        wanted_currency_code=data.get("wanted_currency_code"),
        wanted_currency_amount=int(raw_amount),
        target_user_id=data.get("target_user_id"),
    )
    await state.clear()
    if result.ok and result.target_telegram_id and result.offer_id:
        try:
            await message.bot.send_message(
                result.target_telegram_id,
                f"<b>🔁 Новое предложение обмена</b>\n\nТебе отправили личный обмен. Можно сразу принять, отказаться или посмотреть детали.",
                reply_markup=build_direct_trade_notification_keyboard(result.offer_id),
            )
        except Exception:
            pass
    await message.answer(build_action_result_text(result.title, result.description), reply_markup=build_trades_main_keyboard())


@router.callback_query(F.data.startswith("community:trade_wanted_cards:"))
async def trade_wanted_cards(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    page_num = int(callback.data.split(":")[-1]) if callback.data else 1
    selected_card_ids = data.get("wanted_card_ids", [])
    page = await get_card_choices_page(page=page_num, per_page=COMMUNITY_PER_PAGE, search=data.get("wanted_card_search"), selected_card_ids=selected_card_ids, user_id=await get_current_user_id(callback))
    await edit_or_send(
        callback,
        TRADE_WANTED_CARDS_TEXT + "\n\n" + build_trade_card_choices_page_text(page),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids, page.sort_order),
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
    page = await get_card_choices_page(page=page_num, per_page=COMMUNITY_PER_PAGE, search=data.get("wanted_card_search"), selected_card_ids=selected_card_ids, user_id=await get_current_user_id(callback))
    selected_cards = await get_selected_card_choices(selected_card_ids, user_id=await get_current_user_id(callback))
    selected_text = "\n".join(f"✅ {card.name} • {card.overall} OVR" for card in selected_cards)
    await edit_or_send(
        callback,
        build_trade_card_choices_page_text(page) + (f"\n\n<b>Выбрано</b>\n{selected_text}" if selected_text else ""),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids, page.sort_order),
    )
    await callback.answer("Карточка добавлена")


@router.callback_query(F.data.startswith("community:trade_sort_wanted:"))
async def trade_sort_wanted(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    sort_order = (callback.data or "").split(":")[-1]
    await set_user_card_sort_order(user_id, sort_order)
    data = await state.get_data()
    selected_card_ids = data.get("wanted_card_ids", [])
    page = await get_card_choices_page(
        page=1, per_page=COMMUNITY_PER_PAGE, search=data.get("wanted_card_search"),
        selected_card_ids=selected_card_ids, user_id=user_id,
    )
    await edit_or_send(
        callback, TRADE_WANTED_CARDS_TEXT + "\n\n" + build_trade_card_choices_page_text(page),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids, page.sort_order),
    )
    await callback.answer("Сортировка изменена")


@router.callback_query(F.data.startswith("community:trade_wanted_cosmetics:"))
async def trade_wanted_cosmetics(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected_ids = data.get("wanted_cosmetic_item_ids", [])
    page_num = int((callback.data or "").split(":")[-1])
    page = await get_cosmetic_choices_page(
        page=page_num, per_page=COMMUNITY_PER_PAGE, selected_item_ids=selected_ids,
    )
    await edit_or_send(
        callback, TRADE_WANTED_COSMETICS_TEXT + "\n\n" + build_trade_cosmetic_choices_page_text(page),
        reply_markup=build_wanted_cosmetics_keyboard(page.items, page.page, page.pages_count, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:trade_add_wanted_cosmetic:"))
async def trade_add_wanted_cosmetic(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    cosmetic_item_id = int(parts[2])
    page_num = int(parts[3])
    data = await state.get_data()
    selected_ids = list(data.get("wanted_cosmetic_item_ids", []))
    if len(selected_ids) >= 3:
        await callback.answer("Можно выбрать до 3 предметов косметики", show_alert=True)
        return
    if cosmetic_item_id not in selected_ids:
        selected_ids.append(cosmetic_item_id)
    await state.update_data(wanted_cosmetic_item_ids=selected_ids)
    page = await get_cosmetic_choices_page(
        page=page_num, per_page=COMMUNITY_PER_PAGE, selected_item_ids=selected_ids,
    )
    selected = await get_selected_cosmetic_choices(selected_ids)
    selected_text = "\n".join(f"✅ {item.title}" for item in selected)
    await edit_or_send(
        callback,
        build_trade_cosmetic_choices_page_text(page) + (f"\n\n<b>Выбрано</b>\n{selected_text}" if selected_text else ""),
        reply_markup=build_wanted_cosmetics_keyboard(page.items, page.page, page.pages_count, selected_ids),
    )
    await callback.answer("Косметика добавлена")


@router.callback_query(F.data == "community:trade_publish_cosmetics")
async def trade_publish_cosmetics(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    data = await state.get_data()
    result = await create_trade_offer(
        creator_user_id=user_id,
        offered_user_card_ids=data.get("offered_user_card_ids", []),
        offered_user_cosmetic_ids=data.get("offered_user_cosmetic_ids", []),
        wanted_type="cards",
        wanted_asset_type="cosmetics",
        wanted_cosmetic_item_ids=data.get("wanted_cosmetic_item_ids", []),
        target_user_id=data.get("target_user_id"),
    )
    await state.clear()
    if result.ok and result.target_telegram_id and result.offer_id:
        try:
            await callback.bot.send_message(
                result.target_telegram_id,
                "<b>🔁 Новое предложение обмена</b>\n\nТебе отправили личный обмен косметикой.",
                reply_markup=build_direct_trade_notification_keyboard(result.offer_id),
            )
        except Exception:
            pass
    await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_trades_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "community:trade_search_wanted_card")
async def trade_search_wanted_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CommunityStates.trade_search_wanted_card)
    await edit_or_send(callback, "<b>🔎 Поиск карточки</b>\n\nВведи имя, команду, редкость или позицию.", reply_markup=build_text_cancel_keyboard("community:trade_wanted_cards:1"))
    await callback.answer()


@router.message(CommunityStates.trade_search_wanted_card)
async def trade_search_wanted_card_value(message: Message, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(message.from_user.id) if message.from_user else None
    if user_id is None:
        return
    search = message.text or ""
    await safe_delete_message(message)
    await state.update_data(wanted_card_search=search)
    await state.set_state(None)
    data = await state.get_data()
    selected_card_ids = data.get("wanted_card_ids", [])
    page = await get_card_choices_page(page=1, per_page=COMMUNITY_PER_PAGE, search=search, selected_card_ids=selected_card_ids, user_id=user_id)
    await message.answer(
        build_trade_card_choices_page_text(page),
        reply_markup=build_wanted_cards_keyboard(page.cards, page.page, page.pages_count, selected_card_ids, page.sort_order),
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
        offered_user_cosmetic_ids=data.get("offered_user_cosmetic_ids", []),
        wanted_type="cards",
        wanted_asset_type="cards",
        wanted_card_ids=data.get("wanted_card_ids", []),
        target_user_id=data.get("target_user_id"),
    )
    await state.clear()
    if result.ok and result.target_telegram_id and result.offer_id:
        try:
            await callback.bot.send_message(
                result.target_telegram_id,
                f"<b>🔁 Новое предложение обмена</b>\n\nТебе отправили личный обмен. Можно сразу принять, отказаться или посмотреть детали.",
                reply_markup=build_direct_trade_notification_keyboard(result.offer_id),
            )
        except Exception:
            pass
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


@router.callback_query(F.data.startswith("community:trade_decline:"))
async def trade_decline(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    offer_id = int(parts[2])
    mode = parts[3]
    page_num = int(parts[4])
    result = await decline_trade_offer(offer_id, user_id)
    creator_telegram_id = await get_trade_offer_creator_telegram_id(offer_id)
    if result.ok and creator_telegram_id:
        try:
            await callback.bot.send_message(creator_telegram_id, "<b>🔁 Личный обмен отклонён</b>\n\nИгрок отказался от предложения.")
        except Exception:
            pass
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




@router.callback_query(F.data == "community:clan_player_rating")
async def clan_player_rating(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    profile = await get_user_clan(user_id) if user_id else None
    if profile is None:
        await callback.answer("Ты не состоишь в клане", show_alert=True)
        return
    rows = await get_clan_war_player_rating(profile.id)
    lines = [f"🥇 <b>Вклад игроков — {escape(profile.name, quote=False)}</b>", "", "Победы, принесённые клану в активных клановых атаках:"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. <b>{escape(row['nickname'], quote=False)}</b> — {int(row['wins_contributed'])} побед")
    await edit_or_send(callback, "\n".join(lines), reply_markup=build_clans_main_keyboard(has_clan=True))
    await callback.answer()


@router.callback_query(F.data == "community:clan_global_rating")
async def clan_global_rating(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    has_clan = bool(await get_user_clan(user_id)) if user_id else False
    rows = await get_clan_global_rating()
    lines = ["🏆 <b>Общий рейтинг кланов</b>", "", "Сортировка: рейтинг клана → победы игроков для клана."]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. <b>{escape(row['name'], quote=False)}</b> — ⭐ {int(row['rating_points'])} • 🏒 {int(row['war_wins_contributed'])} побед")
    await edit_or_send(callback, "\n".join(lines), reply_markup=build_clans_main_keyboard(has_clan=has_clan))
    await callback.answer()


@router.callback_query(F.data == "community:war2_player_contribution")
async def war2_player_contribution(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    profile = await get_user_clan(user_id) if user_id else None
    if profile is None:
        await callback.answer("Ты не состоишь в клане", show_alert=True)
        return
    rows = await get_war2_clan_player_contribution(profile.id)
    lines = [f"🥇 <b>Вклад игроков CLAN WAR 2.0 — {escape(profile.name, quote=False)}</b>", "", "Текущий активный сезон:"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. <b>{escape(row['nickname'], quote=False)}</b> — ⭐ {int(row['rating_contributed'])} • 🏒 {int(row['wins_contributed'])} побед • 🎮 {int(row['matches_played'])}")
    await edit_or_send(callback, "\n".join(lines), reply_markup=build_clans_main_keyboard(has_clan=True))
    await callback.answer()


@router.callback_query(F.data == "community:war2_clan_rating")
async def war2_clan_rating(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await get_current_user_id(callback)
    has_clan = bool(await get_user_clan(user_id)) if user_id else False
    rows = await get_war2_clan_rating()
    lines = ["🏆 <b>Рейтинг кланов CLAN WAR 2.0</b>", "", "Текущий активный сезон."]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. <b>{escape(row['name'], quote=False)}</b> — ⭐ {int(row['rating_points'])} • 🏒 {int(row['wins_contributed'])} побед • 🎮 {int(row['matches_played'])}")
    await edit_or_send(callback, "\n".join(lines), reply_markup=build_clans_main_keyboard(has_clan=has_clan))
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

    # Уведомляем президента и вице о новой заявке.
    if result.ok:
        applicant = await get_clan_member_row_public(user_id)
        applicant_name = applicant["nickname"] if applicant else "Игрок"
        for leader_tg in await get_clan_leaders_telegram_ids(clan_id):
            try:
                await callback.bot.send_message(
                    chat_id=leader_tg,
                    text=(
                        f"📥 <b>Новая заявка в клан</b>\n\n"
                        f"👤 <b>{escape(applicant_name, quote=False)}</b> хочет вступить.\n\n"
                        f"Открой «Управление составом» → «Заявки», чтобы принять или отклонить."
                    ),
                    reply_markup=build_clan_requests_shortcut_keyboard(),
                )
            except Exception:
                pass

    profile = await get_clan_profile(clan_id, viewer_user_id=user_id)
    if profile:
        await edit_or_send(callback, build_clan_profile_text(profile) + f"\n\n{result.description}", reply_markup=build_clan_profile_keyboard(profile, 1))
    else:
        await edit_or_send(callback, build_action_result_text(result.title, result.description), reply_markup=build_clans_main_keyboard(has_clan=False))
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data == "community:clan_requests")
async def clan_requests(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    requests = await get_pending_requests(profile.id)
    await edit_or_send(
        callback,
        build_clan_requests_text(requests),
        reply_markup=build_clan_requests_keyboard(requests),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:clan_req_approve:"))
async def clan_req_approve(callback: CallbackQuery, state: FSMContext) -> None:
    await _resolve_clan_request(callback, approve=True)


@router.callback_query(F.data.startswith("community:clan_req_reject:"))
async def clan_req_reject(callback: CallbackQuery, state: FSMContext) -> None:
    await _resolve_clan_request(callback, approve=False)


async def _resolve_clan_request(callback: CallbackQuery, approve: bool) -> None:
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    request_id = int(raw) if raw.isdigit() else 0
    result, applicant_tg = await resolve_join_request(user_id, request_id, approve)

    if result.ok and applicant_tg:
        text = (
            "✅ <b>Заявка одобрена</b>\n\nТебя приняли в клан! Загляни в раздел «Сообщество»."
            if approve
            else "❌ <b>Заявка отклонена</b>\n\nПрезидент клана отклонил твою заявку."
        )
        try:
            await callback.bot.send_message(chat_id=applicant_tg, text=text)
        except Exception:
            pass

    profile = await get_user_clan(user_id)
    if profile is not None:
        requests = await get_pending_requests(profile.id)
        await edit_or_send(callback, build_clan_requests_text(requests), reply_markup=build_clan_requests_keyboard(requests))
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


async def get_actor_clan_context(callback: CallbackQuery):
    """Возвращает (user_id, ClanProfile) для управляющего составом или (None, None)."""
    user_id = await get_current_user_id(callback)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return None, None
    profile = await get_user_clan(user_id)
    if profile is None:
        await callback.answer("Ты пока не состоишь в клане", show_alert=True)
        return None, None
    if profile.viewer_role not in ("leader", "officer"):
        await callback.answer("Управлять составом могут президент и вице-президент", show_alert=True)
        return None, None
    return user_id, profile


@router.callback_query(F.data == "community:clan_manage")
async def clan_manage(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    pending_count = await count_pending_requests(profile.id)
    await edit_or_send(
        callback,
        CLAN_MANAGE_TEXT,
        reply_markup=build_clan_manage_keyboard(profile.members, actor_user_id=user_id, actor_role=profile.viewer_role, pending_count=pending_count),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:clan_member:"))
async def clan_member_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    member_user_id = int(raw_id) if raw_id.isdigit() else 0
    member = next((item for item in profile.members if item.user_id == member_user_id), None)
    if member is None or member.role == "leader" or member.user_id == user_id:
        await callback.answer("Игрок недоступен для управления", show_alert=True)
        return
    if profile.viewer_role == "officer" and member.role == "officer":
        await callback.answer("Вице-президент может управлять только участниками", show_alert=True)
        return
    await edit_or_send(
        callback,
        build_clan_member_manage_text(member.nickname, member.role),
        reply_markup=build_clan_member_manage_keyboard(member.user_id, member.role, actor_role=profile.viewer_role),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:clan_member_stats:"))
async def clan_member_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    member_user_id = int(raw_id) if raw_id.isdigit() else 0
    member = next((item for item in profile.members if item.user_id == member_user_id), None)
    if member is None:
        await callback.answer("Игрок не найден в клане", show_alert=True)
        return
    player_profile = await get_public_player_profile(member_user_id, viewer_user_id=user_id)
    if player_profile is None:
        await callback.answer("Статистика игрока не найдена", show_alert=True)
        return
    await edit_or_send(
        callback,
        build_public_player_profile_text(player_profile),
        reply_markup=build_clan_member_stats_keyboard(member_user_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:clan_vice:"))
async def clan_vice(callback: CallbackQuery, state: FSMContext) -> None:
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    member_user_id = int(raw_id) if raw_id.isdigit() else 0
    result = await toggle_clan_vice(user_id, member_user_id)

    if result.ok:
        target_telegram_id = await get_clan_member_telegram_id(member_user_id)
        if target_telegram_id:
            notify_text = (
                "🥈 <b>Новая роль в клане</b>\n\nТебя назначили вице-президентом клана. Теперь ты можешь управлять составом."
                if "назначен" in result.title.lower()
                else "🏒 <b>Роль в клане обновлена</b>\n\nТы снова обычный участник клана."
            )
            try:
                await callback.bot.send_message(chat_id=target_telegram_id, text=notify_text)
            except Exception:
                pass

    updated_profile = await get_user_clan(user_id)
    if updated_profile is not None:
        await edit_or_send(
            callback,
            CLAN_MANAGE_TEXT,
            reply_markup=build_clan_manage_keyboard(updated_profile.members, actor_user_id=user_id, actor_role=updated_profile.viewer_role),
        )
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data.startswith("community:clan_kick_confirm:"))
async def clan_kick_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    member_user_id = int(raw_id) if raw_id.isdigit() else 0
    member = next((item for item in profile.members if item.user_id == member_user_id), None)
    if member is None:
        await callback.answer("Игрок уже не в клане", show_alert=True)
        return
    await edit_or_send(
        callback,
        f"<b>🚫 Исключить игрока?</b>\n\n👤 <b>{escape(member.nickname, quote=False)}</b> покинет клан, место освободится.",
        reply_markup=build_clan_kick_confirm_keyboard(member_user_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("community:clan_kick:"))
async def clan_kick(callback: CallbackQuery, state: FSMContext) -> None:
    user_id, profile = await get_actor_clan_context(callback)
    if profile is None:
        return
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    member_user_id = int(raw_id) if raw_id.isdigit() else 0
    result = await kick_clan_member(user_id, member_user_id)

    if result.ok:
        target_telegram_id = await get_clan_member_telegram_id(member_user_id)
        if target_telegram_id:
            try:
                await callback.bot.send_message(
                    chat_id=target_telegram_id,
                    text="🚫 <b>Клан покинут</b>\n\nТебя исключили из клана. Ты можешь вступить в другую команду в разделе «Сообщество».",
                )
            except Exception:
                pass

    updated_profile = await get_user_clan(user_id)
    if updated_profile is not None:
        await edit_or_send(
            callback,
            CLAN_MANAGE_TEXT,
            reply_markup=build_clan_manage_keyboard(updated_profile.members, actor_user_id=user_id, actor_role=updated_profile.viewer_role),
        )
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
