from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_users import AdminUserListItem
from app.services.user_cards import CardChoiceItem


ADMIN_USERS_PER_PAGE = 5
ADMIN_USER_CARDS_PER_PAGE = 5


def build_admin_users_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все игроки", callback_data="admin_users:list:1")],
            [InlineKeyboardButton(text="🔎 Найти игрока", callback_data="admin_users:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_users_list_keyboard(
    users: list[AdminUserListItem],
    page: int,
    pages_count: int,
    search: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for user in users:
        marker = "🚫" if user.is_banned else "🏒"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {user.nickname} · {user.league}",
                    callback_data=f"admin_users:view:{user.id}:{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(
            InlineKeyboardButton(text="⬅️", callback_data=(f"admin_users:search_list:{page - 1}" if search else f"admin_users:list:{page - 1}"))
        )

    navigation.append(
        InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="admin_users:page_info")
    )

    if page < pages_count:
        navigation.append(
            InlineKeyboardButton(text="➡️", callback_data=(f"admin_users:search_list:{page + 1}" if search else f"admin_users:list:{page + 1}"))
        )

    if navigation:
        keyboard.append(navigation)

    if search:
        keyboard.append([InlineKeyboardButton(text="📋 Все игроки", callback_data="admin_users:list:1")])

    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="admin_users:search")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_user_profile_keyboard(
    user_id: int,
    page: int,
    premium_pass: bool,
    is_banned: bool,
) -> InlineKeyboardMarkup:
    premium_text = "👑 Отключить Premium Pass" if premium_pass else "👑 Открыть Premium Pass"
    ban_text = "✅ Вернуть игрока" if is_banned else "🚫 Заблокировать"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🃏 Выдать карточку", callback_data=f"admin_users:give_card:{user_id}:{page}")],
            [InlineKeyboardButton(text="🎁 Выдать пак", callback_data=f"admin_users:give_pack:{user_id}:{page}")],
            [InlineKeyboardButton(text="💱 Выдать валюту", callback_data=f"admin_users:currency:{user_id}:{page}")],
            [InlineKeyboardButton(text="🏆 Изменить лигу", callback_data=f"admin_users:league:{user_id}:{page}")],
            [InlineKeyboardButton(text=premium_text, callback_data=f"admin_users:premium:{user_id}:{page}")],
            [InlineKeyboardButton(text=ban_text, callback_data=f"admin_users:ban:{user_id}:{page}")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_users:view:{user_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К игрокам", callback_data=f"admin_users:list:{page}")],
        ]
    )


def build_admin_user_currency_keyboard(user_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Coins", callback_data=f"admin_users:currency_code:{user_id}:coins:{page}")],
            [InlineKeyboardButton(text="⚡ Energy", callback_data=f"admin_users:currency_code:{user_id}:energy:{page}")],
            [InlineKeyboardButton(text="🏅 Rank-point", callback_data=f"admin_users:currency_code:{user_id}:rank_point:{page}")],
            [InlineKeyboardButton(text="⬅️ К игроку", callback_data=f"admin_users:view:{user_id}:{page}")],
        ]
    )


def build_admin_user_leagues_keyboard(user_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="NCAA", callback_data=f"admin_users:set_league:{user_id}:NCAA:{page}")],
            [InlineKeyboardButton(text="AHL", callback_data=f"admin_users:set_league:{user_id}:AHL:{page}")],
            [InlineKeyboardButton(text="NHL", callback_data=f"admin_users:set_league:{user_id}:NHL:{page}")],
            [InlineKeyboardButton(text="OLYMPICS", callback_data=f"admin_users:set_league:{user_id}:OLYMPICS:{page}")],
            [InlineKeyboardButton(text="⬅️ К игроку", callback_data=f"admin_users:view:{user_id}:{page}")],
        ]
    )


def build_admin_user_give_card_keyboard(
    user_id: int,
    user_page: int,
    cards: list[CardChoiceItem],
    card_page: int,
    pages_count: int,
    search: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for card in cards:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🃏 {card.name} · {card.overall} · {card.position}",
                    callback_data=f"admin_users:give_card_do:{user_id}:{card.id}:{user_page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if card_page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"admin_users:give_card_list:{user_id}:{card_page - 1}:{user_page}",
            )
        )

    navigation.append(
        InlineKeyboardButton(text=f"{card_page}/{pages_count}", callback_data="admin_users:page_info")
    )

    if card_page < pages_count:
        navigation.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"admin_users:give_card_list:{user_id}:{card_page + 1}:{user_page}",
            )
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🔎 Найти карточку", callback_data=f"admin_users:give_card_search:{user_id}:{user_page}")])

    if search:
        keyboard.append([InlineKeyboardButton(text="📋 Все карточки", callback_data=f"admin_users:give_card_list:{user_id}:1:{user_page}")])

    keyboard.append([InlineKeyboardButton(text="⬅️ К игроку", callback_data=f"admin_users:view:{user_id}:{user_page}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_users_cancel_keyboard(user_id: int | None = None, page: int = 1) -> InlineKeyboardMarkup:
    if user_id is None:
        callback_data = "admin_users:main"
        text = "⬅️ Назад"
    else:
        callback_data = f"admin_users:view:{user_id}:{page}"
        text = "⬅️ К игроку"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data)],
        ]
    )
