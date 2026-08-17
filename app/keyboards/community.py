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


def build_direct_trade_players_keyboard(players, page: int, pages_count: int) -> InlineKeyboardMarkup:
    keyboard = []
    for player in players:
        keyboard.append([InlineKeyboardButton(text=f"🎯 {player.nickname} · {player.league}", callback_data=f"community:trade_direct_player:{player.id}:{page}")])
    keyboard.append(pagination_buttons("community:trade_direct_players", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="community:trade_direct_search")])
    keyboard.append([InlineKeyboardButton(text="🔁 Обмены", callback_data="community:trades")])
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
            [InlineKeyboardButton(text="📈 Рынок обменов", callback_data="community:trade_list:market:1")],
            [InlineKeyboardButton(text="➕ На рынок", callback_data="community:trade_create")],
            [InlineKeyboardButton(text="🎯 Игроку", callback_data="community:trade_direct_search")],
            [InlineKeyboardButton(text="📥 Личные предложения", callback_data="community:trade_list:incoming:1")],
            [InlineKeyboardButton(text="📦 Мои обмены", callback_data="community:trade_list:my:1")],
            [InlineKeyboardButton(text="🤝 Сообщество", callback_data="community:main")],
        ]
    )


def _sort_toggle(sort_order: str, callback_prefix: str) -> InlineKeyboardButton:
    if sort_order == "ovr_asc":
        return InlineKeyboardButton(text="↘️ Сильные → слабые", callback_data=f"{callback_prefix}:ovr_desc")
    return InlineKeyboardButton(text="↗️ Слабые → сильные", callback_data=f"{callback_prefix}:ovr_asc")


def build_trade_cards_keyboard(cards, page: int, pages_count: int, selected_ids: list[int], sort_order: str = "ovr_desc", has_any_selected: bool | None = None) -> InlineKeyboardMarkup:
    keyboard = []
    for card in cards:
        keyboard.append([InlineKeyboardButton(text=f"➕ {card.name} • {card.overall} OVR", callback_data=f"community:trade_add_offer_card:{card.id}:{page}")])
    keyboard.append([_sort_toggle(sort_order, "community:trade_sort_offer")])
    keyboard.append([
        InlineKeyboardButton(text="🔎 Поиск карт", callback_data="community:trade_search_offer_card"),
        InlineKeyboardButton(text="🎨 Выбрать косметику", callback_data="community:trade_offer_cosmetics:1"),
    ])
    if has_any_selected is None:
        has_any_selected = bool(selected_ids)
    if has_any_selected:
        keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="community:trade_wanted")])
    keyboard.append(pagination_buttons("community:trade_offer_cards", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_trade_cosmetics_keyboard(items, page: int, pages_count: int, selected_ids: list[int], has_any_selected: bool) -> InlineKeyboardMarkup:
    keyboard = []
    for item in items:
        suffix = f" · {item.badge_text}" if item.badge_text else ""
        keyboard.append([InlineKeyboardButton(
            text=f"➕ {item.title}{suffix} · #{item.id}",
            callback_data=f"community:trade_add_offer_cosmetic:{item.id}:{page}",
        )])
    keyboard.append([InlineKeyboardButton(text="🎴 Выбрать карточки", callback_data="community:trade_offer_cards:1")])
    if has_any_selected:
        keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="community:trade_wanted")])
    keyboard.append(pagination_buttons("community:trade_offer_cosmetics", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_trade_wanted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎴 Хочу карточки", callback_data="community:trade_wanted_cards:1")],
            [InlineKeyboardButton(text="🎨 Хочу косметику", callback_data="community:trade_wanted_cosmetics:1")],
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


def build_wanted_cards_keyboard(cards, page: int, pages_count: int, selected_card_ids: list[int], sort_order: str = "ovr_desc") -> InlineKeyboardMarkup:
    keyboard = []
    for card in cards:
        keyboard.append([InlineKeyboardButton(text=f"➕ {card.name} • {card.overall} OVR", callback_data=f"community:trade_add_wanted_card:{card.id}:{page}")])
    keyboard.append([_sort_toggle(sort_order, "community:trade_sort_wanted")])
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="community:trade_search_wanted_card")])
    if selected_card_ids:
        keyboard.append([InlineKeyboardButton(text="✅ Опубликовать", callback_data="community:trade_publish_cards")])
    keyboard.append(pagination_buttons("community:trade_wanted_cards", page, pages_count))
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="community:trades")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_wanted_cosmetics_keyboard(items, page: int, pages_count: int, selected_item_ids: list[int]) -> InlineKeyboardMarkup:
    keyboard = []
    for item in items:
        suffix = f" · {item.badge_text}" if item.badge_text else ""
        keyboard.append([InlineKeyboardButton(
            text=f"➕ {item.title}{suffix}",
            callback_data=f"community:trade_add_wanted_cosmetic:{item.id}:{page}",
        )])
    if selected_item_ids:
        keyboard.append([InlineKeyboardButton(text="✅ Опубликовать", callback_data="community:trade_publish_cosmetics")])
    keyboard.append(pagination_buttons("community:trade_wanted_cosmetics", page, pages_count))
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
        if offer.target_user_id == viewer_user_id:
            keyboard.append([InlineKeyboardButton(text="❌ Отказаться", callback_data=f"community:trade_decline:{offer.id}:{mode}:{page}")])
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
    keyboard.append([InlineKeyboardButton(text="🏟 Войны кланов", callback_data="wars:main")])
    keyboard.append([InlineKeyboardButton(text="🏆 Рейтинг кланов", callback_data="community:clan_global_rating")])
    if has_clan:
        keyboard.append([InlineKeyboardButton(text="🥇 Вклад игроков", callback_data="community:clan_player_rating")])
    keyboard.append([InlineKeyboardButton(text="⚔️ CLAN WAR 2.0", callback_data="war2:main")])
    keyboard.append([InlineKeyboardButton(text="🏆 Рейтинг CLAN WAR 2.0", callback_data="community:war2_clan_rating")])
    if has_clan:
        keyboard.append([InlineKeyboardButton(text="🥇 Вклад игроков CW 2.0", callback_data="community:war2_player_contribution")])
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
        if profile.viewer_role in ("leader", "officer"):
            keyboard.append([InlineKeyboardButton(text="⚙️ Управление составом", callback_data="community:clan_manage")])
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


def build_clan_manage_keyboard(members, actor_user_id: int, actor_role: str, pending_count: int = 0) -> InlineKeyboardMarkup:
    keyboard = []
    req_label = f"📥 Заявки ({pending_count})" if pending_count else "📥 Заявки"
    keyboard.append([InlineKeyboardButton(text=req_label, callback_data="community:clan_requests")])
    role_icons = {"leader": "👑", "officer": "🥈", "member": "🏒"}

    for member in members:
        if member.user_id == actor_user_id:
            continue
        if member.role == "leader":
            continue
        if actor_role == "officer" and member.role == "officer":
            continue
        icon = role_icons.get(member.role, "🏒")
        keyboard.append([
            InlineKeyboardButton(
                text=f"{icon} {member.nickname}",
                callback_data=f"community:clan_member:{member.user_id}",
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅️ К клану", callback_data="community:my_clan")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_clan_member_manage_keyboard(member_user_id: int, member_role: str, actor_role: str) -> InlineKeyboardMarkup:
    keyboard = []

    keyboard.append([InlineKeyboardButton(text="📊 Статистика игрока", callback_data=f"community:clan_member_stats:{member_user_id}")])

    if actor_role == "leader":
        vice_text = "🥈 Снять вице-президента" if member_role == "officer" else "🥈 Назначить вице-президентом"
        keyboard.append([InlineKeyboardButton(text=vice_text, callback_data=f"community:clan_vice:{member_user_id}")])

    keyboard.append([InlineKeyboardButton(text="🚫 Исключить из клана", callback_data=f"community:clan_kick_confirm:{member_user_id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К составу", callback_data="community:clan_manage")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_clan_kick_confirm_keyboard(member_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Да, исключить", callback_data=f"community:clan_kick:{member_user_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"community:clan_member:{member_user_id}")],
        ]
    )


def build_clan_requests_keyboard(requests) -> InlineKeyboardMarkup:
    keyboard = []
    for req in requests:
        keyboard.append([
            InlineKeyboardButton(text=f"✅ {req['nickname']}", callback_data=f"community:clan_req_approve:{req['id']}"),
            InlineKeyboardButton(text="❌", callback_data=f"community:clan_req_reject:{req['id']}"),
        ])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="community:clan_requests")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К составу", callback_data="community:clan_manage")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_clan_requests_shortcut_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Открыть заявки", callback_data="community:clan_requests")]])



def build_clan_member_stats_keyboard(member_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К игроку клана", callback_data=f"community:clan_member:{member_user_id}")],
            [InlineKeyboardButton(text="⬅️ К составу", callback_data="community:clan_manage")],
        ]
    )
