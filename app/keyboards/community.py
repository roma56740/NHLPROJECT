from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

COMMUNITY_PER_PAGE = 5


def pagination_buttons(prefix: str, page: int, pages_count: int) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page - 1}"))
    buttons.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="noop"))
    if page < pages_count:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page + 1}"))
    return buttons


def build_community_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Игроки", callback_data="community:players:1")],
            [InlineKeyboardButton(text="🔁 Рынок обменов", callback_data="community:trades")],
            [InlineKeyboardButton(text="🏰 Кланы", callback_data="community:clans")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_players_keyboard(players, page: int, pages_count: int) -> InlineKeyboardMarkup:
    keyboard = []
    for player in players:
        keyboard.append([InlineKeyboardButton(text=f"👤 {player.nickname}", callback_data=f"community:player:{player.id}:{page}")])
    keyboard.append([InlineKeyboardButton(text="🔎 Найти игрока", callback_data="community:players_search")])
    keyboard.append(pagination_buttons("community:players", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="🤝 Сообщество", callback_data="community:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_player_profile_keyboard(player_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К игрокам", callback_data=f"community:players:{page}")],
            [InlineKeyboardButton(text="🤝 Сообщество", callback_data="community:main")],
        ]
    )


def build_text_cancel_keyboard(callback_data: str = "community:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)],
        ]
    )


def build_trades_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Открытые обмены", callback_data="community:trade_list:market:1")],
            [InlineKeyboardButton(text="➕ Создать обмен", callback_data="community:trade_create")],
            [InlineKeyboardButton(text="📦 Мои обмены", callback_data="community:trade_list:my:1")],
            [InlineKeyboardButton(text="🤝 Сообщество", callback_data="community:main")],
        ]
    )


def build_trade_cards_keyboard(cards, page: int, pages_count: int, selected_ids: list[int]) -> InlineKeyboardMarkup:
    keyboard = []
    for card in cards:
        keyboard.append([InlineKeyboardButton(text=f"➕ {card.name} • {card.overall} OVR", callback_data=f"community:trade_add_offer_card:{card.id}:{page}")])
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="community:trade_search_offer_card")])
    if selected_ids:
        keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="community:trade_wanted")])
    keyboard.append(pagination_buttons("community:trade_offer_cards", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_trade_wanted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎴 Хочу карточки", callback_data="community:trade_wanted_cards:1")],
            [InlineKeyboardButton(text="💰 Хочу валюту", callback_data="community:trade_wanted_currency")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")],
        ]
    )


def build_currency_choice_keyboard(currencies) -> InlineKeyboardMarkup:
    keyboard = []
    for currency in currencies:
        keyboard.append([InlineKeyboardButton(text=f"{currency.icon} {currency.name}", callback_data=f"community:trade_currency:{currency.code}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_wanted_cards_keyboard(cards, page: int, pages_count: int, selected_card_ids: list[int]) -> InlineKeyboardMarkup:
    keyboard = []
    for card in cards:
        keyboard.append([InlineKeyboardButton(text=f"➕ {card.name} • {card.overall} OVR", callback_data=f"community:trade_add_wanted_card:{card.id}:{page}")])
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="community:trade_search_wanted_card")])
    if selected_card_ids:
        keyboard.append([InlineKeyboardButton(text="✅ Опубликовать", callback_data="community:trade_publish_cards")])
    keyboard.append(pagination_buttons("community:trade_wanted_cards", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_trade_offers_keyboard(offers, mode: str, page: int, pages_count: int) -> InlineKeyboardMarkup:
    keyboard = []
    for offer in offers:
        if mode == "admin":
            keyboard.append([InlineKeyboardButton(text=f"🔁 Обмен #{offer.id}", callback_data=f"admin_trades:view:{offer.id}:{page}")])
        else:
            keyboard.append([InlineKeyboardButton(text=f"🔁 Обмен #{offer.id}", callback_data=f"community:trade_view:{offer.id}:{mode}:{page}")])
    if mode == "admin":
        keyboard.append(pagination_buttons("admin_trades:list", page, pages_count))
        keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    else:
        keyboard.append(pagination_buttons(f"community:trade_list:{mode}", page, pages_count))
        keyboard.append([InlineKeyboardButton(text="🔁 Рынок обменов", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_trade_offer_profile_keyboard(offer, viewer_user_id: int | None, mode: str, page: int, admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    if admin:
        if offer.status == "open":
            keyboard.append([InlineKeyboardButton(text="🚫 Закрыть обмен", callback_data=f"admin_trades:cancel:{offer.id}:{page}")])
        keyboard.append([InlineKeyboardButton(text="🗑 Удалить обмен", callback_data=f"admin_trades:delete:{offer.id}:{page}")])
        keyboard.append([InlineKeyboardButton(text="⬅️ К обменам", callback_data=f"admin_trades:list:{page}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    if offer.status == "open" and viewer_user_id and offer.creator_user_id != viewer_user_id:
        keyboard.append([InlineKeyboardButton(text="✅ Принять обмен", callback_data=f"community:trade_accept:{offer.id}:{mode}:{page}")])
    if offer.status == "open" and viewer_user_id and offer.creator_user_id == viewer_user_id:
        keyboard.append([InlineKeyboardButton(text="🚫 Отменить обмен", callback_data=f"community:trade_cancel:{offer.id}:{mode}:{page}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"community:trade_list:{mode}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_clans_main_keyboard(has_clan: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if has_clan:
        keyboard.append([InlineKeyboardButton(text="🏰 Мой клан", callback_data="community:my_clan")])
    else:
        keyboard.append([InlineKeyboardButton(text="➕ Создать клан", callback_data="community:clan_create")])
    keyboard.append([InlineKeyboardButton(text="📋 Все кланы", callback_data="community:clan_list:1")])
    keyboard.append([InlineKeyboardButton(text="🔎 Найти клан", callback_data="community:clan_search")])
    keyboard.append([InlineKeyboardButton(text="🤝 Сообщество", callback_data="community:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_clans_list_keyboard(clans, page: int, pages_count: int, admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    prefix = "admin_clans" if admin else "community"
    for clan in clans:
        callback = f"admin_clans:view:{clan.id}:{page}" if admin else f"community:clan_view:{clan.id}:{page}"
        keyboard.append([InlineKeyboardButton(text=f"🏰 {clan.name}", callback_data=callback)])
    list_prefix = "admin_clans:list" if admin else "community:clan_list"
    keyboard.append(pagination_buttons(list_prefix, page, pages_count))
    if admin:
        keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="admin_clans:search")])
        keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    else:
        keyboard.append([InlineKeyboardButton(text="🏰 Кланы", callback_data="community:clans")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_clan_profile_keyboard(profile, page: int, admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    if admin:
        toggle_text = "🔴 Закрыть клан" if profile.active else "🟢 Открыть клан"
        keyboard.append([InlineKeyboardButton(text=toggle_text, callback_data=f"admin_clans:toggle:{profile.id}:{page}")])
        keyboard.append([InlineKeyboardButton(text="🗑 Расформировать", callback_data=f"admin_clans:delete:{profile.id}:{page}")])
        keyboard.append([InlineKeyboardButton(text="⬅️ К кланам", callback_data=f"admin_clans:list:{page}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    if profile.viewer_role is None and profile.active:
        keyboard.append([InlineKeyboardButton(text="✅ Вступить", callback_data=f"community:clan_join:{profile.id}:{page}")])
    elif profile.viewer_role is not None:
        keyboard.append([InlineKeyboardButton(text="🚪 Покинуть клан", callback_data="community:clan_leave")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К кланам", callback_data=f"community:clan_list:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_clans_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все кланы", callback_data="admin_clans:list:1")],
            [InlineKeyboardButton(text="🔎 Найти клан", callback_data="admin_clans:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_trades_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все обмены", callback_data="admin_trades:list:1")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )
