from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.rating import LeaderboardPage


RATING_PER_PAGE = 5


def build_rating_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Таблица лидеров", callback_data="rating:global:1")],
            [InlineKeyboardButton(text="🏆 Топ моей лиги", callback_data="rating:league:1")],
            [InlineKeyboardButton(text="🎖 Топ OLYMPICS", callback_data="rating:olympics:1")],
            [InlineKeyboardButton(text="🏒 Лиги", callback_data="rating:leagues")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="rating:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_leaderboard_keyboard(page: LeaderboardPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"rating:{page.mode}:{page.page - 1}")
        )

    navigation.append(
        InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="rating:page_info")
    )

    if page.page < page.pages_count:
        navigation.append(
            InlineKeyboardButton(text="➡️", callback_data=f"rating:{page.mode}:{page.page + 1}")
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="⬅️ К рейтингу", callback_data="rating:main")])
    keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_rating_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К рейтингу", callback_data="rating:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )
