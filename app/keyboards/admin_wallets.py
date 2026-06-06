from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_wallets import WalletCurrency, WalletUserListItem


ADMIN_WALLETS_USERS_PER_PAGE = 5


def build_admin_wallets_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все игроки", callback_data="admin_wallets:users:1")],
            [InlineKeyboardButton(text="🔎 Найти игрока", callback_data="admin_wallets:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_wallets_users_keyboard(
    users: list[WalletUserListItem],
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
                    callback_data=f"admin_wallets:view:{user.id}:{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=(f"admin_wallets:search_users:{page - 1}" if search else f"admin_wallets:users:{page - 1}"),
            )
        )

    navigation.append(
        InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="admin_wallets:page_info")
    )

    if page < pages_count:
        navigation.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(f"admin_wallets:search_users:{page + 1}" if search else f"admin_wallets:users:{page + 1}"),
            )
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="admin_wallets:search")])

    if search:
        keyboard.append([InlineKeyboardButton(text="📋 Все игроки", callback_data="admin_wallets:users:1")])

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_wallets:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_wallet_user_keyboard(user_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💱 Выбрать валюту", callback_data=f"admin_wallets:currencies:{user_id}:{page}")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_wallets:view:{user_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К игрокам", callback_data=f"admin_wallets:users:{page}")],
        ]
    )


def build_admin_wallet_currencies_keyboard(
    user_id: int,
    page: int,
    currencies: list[WalletCurrency],
) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"{currency.icon} {currency.name}",
                callback_data=f"admin_wallets:currency:{user_id}:{currency.code}:{page}",
            )
        ]
        for currency in currencies
    ]
    keyboard.append([InlineKeyboardButton(text="⬅️ К кошельку", callback_data=f"admin_wallets:view:{user_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_wallet_action_keyboard(user_id: int, currency_code: str, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Начислить", callback_data=f"admin_wallets:action:{user_id}:{currency_code}:add:{page}")],
            [InlineKeyboardButton(text="➖ Списать", callback_data=f"admin_wallets:action:{user_id}:{currency_code}:remove:{page}")],
            [InlineKeyboardButton(text="⬅️ К валютам", callback_data=f"admin_wallets:currencies:{user_id}:{page}")],
        ]
    )


def build_admin_wallet_cancel_keyboard(user_id: int | None = None, page: int = 1) -> InlineKeyboardMarkup:
    callback_data = f"admin_wallets:view:{user_id}:{page}" if user_id else "admin_wallets:main"
    text = "⬅️ К кошельку" if user_id else "⬅️ Назад"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data)],
        ]
    )
