from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.rating import LeaderboardPage


LEAGUES = ["NCAA", "AHL", "NHL", "OLYMPICS"]


def build_admin_rating_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Общий топ", callback_data="admin_rating:global:1")],
            [InlineKeyboardButton(text="🎓 NCAA", callback_data="admin_rating:league:NCAA:1")],
            [InlineKeyboardButton(text="🛡 AHL", callback_data="admin_rating:league:AHL:1")],
            [InlineKeyboardButton(text="🏒 NHL", callback_data="admin_rating:league:NHL:1")],
            [InlineKeyboardButton(text="🎖 OLYMPICS", callback_data="admin_rating:league:OLYMPICS:1")],
            [InlineKeyboardButton(text="🏒 Лиги", callback_data="admin_rating:leagues")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_leaderboard_keyboard(page: LeaderboardPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_rating:{page.mode}:{page.page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="noop"))

    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_rating:{page.mode}:{page.page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="⬅️ К рейтингу", callback_data="admin_rating:main")])
    keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_league_keyboard(league: str, page: LeaderboardPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_rating:league:{league}:{page.page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="noop"))

    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_rating:league:{league}:{page.page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="⬅️ К рейтингу", callback_data="admin_rating:main")])
    keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_rating_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К рейтингу", callback_data="admin_rating:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )
