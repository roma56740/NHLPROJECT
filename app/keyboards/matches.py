from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.matches import MatchHistoryPage


MATCH_HISTORY_PER_PAGE = 5


def build_matches_main_keyboard(is_ready: bool) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    if is_ready:
        keyboard.append([InlineKeyboardButton(text="🏒 Найти соперника", callback_data="matches:play")])
    else:
        keyboard.append([InlineKeyboardButton(text="🧩 Собрать состав", callback_data="lineup:main")])

    keyboard.append([InlineKeyboardButton(text="📜 История матчей", callback_data="matches:history:1")])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="matches:main")])
    keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_match_search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="matches:cancel")],
        ]
    )


def build_match_result_keyboard(match_id: int | None) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🏒 Найти ещё соперника", callback_data="matches:play")],
        [InlineKeyboardButton(text="📜 История матчей", callback_data="matches:history:1")],
    ]

    if match_id is not None:
        keyboard.insert(1, [InlineKeyboardButton(text="📋 Детали матча", callback_data=f"matches:details:{match_id}:1")])

    keyboard.append([InlineKeyboardButton(text="⬅️ К разделу", callback_data="matches:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_match_not_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧩 Открыть состав", callback_data="lineup:main")],
            [InlineKeyboardButton(text="⬅️ К матчам", callback_data="matches:main")],
        ]
    )


def build_match_history_keyboard(page: MatchHistoryPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for match in page.matches:
        mark = "✅" if match.result == "win" else "❌"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {match.user_score}-{match.opponent_score} · {match.opponent_name}",
                    callback_data=f"matches:details:{match.id}:{page.page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"matches:history:{page.page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="matches:page_info"))

    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"matches:history:{page.page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="⬅️ К матчам", callback_data="matches:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_match_details_keyboard(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К истории", callback_data=f"matches:history:{page}")],
            [InlineKeyboardButton(text="🏒 Найти соперника", callback_data="matches:play")],
        ]
    )


def build_match_captcha_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=opt, callback_data=f"matches:captcha:{opt}") for opt in options]
    return InlineKeyboardMarkup(inline_keyboard=[row, [InlineKeyboardButton(text="⬅️ Отмена", callback_data="matches:main")]])

