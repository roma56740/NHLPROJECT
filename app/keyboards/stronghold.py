"""Клавиатуры THE STRONGHOLD (пользовательский UI).

Вынесено из app/handlers/stronghold.py в соответствии с конвенцией проекта
(см. app/keyboards/quests.py и т.п.) — функции строят `InlineKeyboardMarkup` по данным
сервисного слоя, ничего сами не запрашивают и не вычисляют бизнес-логику.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.texts import stronghold as texts


def back_row(callback_data: str = "stg:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)]


def build_overview_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚔️ Upgrade Chain", callback_data="stg:upgrade")],
        [InlineKeyboardButton(text="🏯 Fortress", callback_data="stg:fortress")],
        [InlineKeyboardButton(text="🌊 Endless Siege", callback_data="stg:endless")],
        [InlineKeyboardButton(text="🎯 Задания", callback_data="stg:missions:DAILY")],
        [InlineKeyboardButton(text="📈 Season Track", callback_data="stg:season")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="stg:store:Featured")],
        [InlineKeyboardButton(text="📜 История кошелька", callback_data="stg:wallet_history:1")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_upgrade_keyboard(*, can_confirm: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if can_confirm:
        keyboard.append([InlineKeyboardButton(text="✅ Подтвердить апгрейд", callback_data="stg:upgrade:confirm")])
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_fortress_list_keyboard(fortresses) -> InlineKeyboardMarkup:
    keyboard = []
    for fortress in fortresses:
        icon = texts.FORTRESS_STATUS_ICONS.get(fortress.status, "")
        label = f"{icon} {fortress.order_index}. {fortress.title}"
        callback_data = f"stg:fortress:view:{fortress.id}" if fortress.status != "LOCKED" else f"stg:fortress:locked:{fortress.id}"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_fortress_view_keyboard(fortress) -> InlineKeyboardMarkup:
    keyboard = []
    for match in fortress.matches:
        icon = texts.FORTRESS_MATCH_STATUS_ICONS.get(match.status, "")
        stars_text = "⭐" * match.stars if match.stars else ""
        label = f"{icon} Матч {match.order_index} vs {match.opponent_name} (OVR {match.opponent_ovr}) {stars_text}"
        callback_data = f"stg:fortress:play:{match.id}" if match.status in ("AVAILABLE", "WON", "LOST", "COMPLETED") else "stg:fortress:locked"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    keyboard.append(back_row("stg:fortress"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_endless_keyboard(*, unlocked: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if unlocked:
        keyboard.append([InlineKeyboardButton(text="⚔️ Играть волну", callback_data="stg:endless:play")])
    keyboard.append([InlineKeyboardButton(text="🏆 Таблица лидеров", callback_data="stg:endless:leaderboard:1")])
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_leaderboard_keyboard(board) -> InlineKeyboardMarkup:
    keyboard = []
    nav_row = []
    if board.page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"stg:endless:leaderboard:{board.page - 1}"))
    if board.page < board.pages_count:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"stg:endless:leaderboard:{board.page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append(back_row("stg:endless"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_missions_keyboard(missions, mission_type: str, mission_types: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    for mission in missions:
        if mission.status == "COMPLETED":
            keyboard.append([InlineKeyboardButton(text=f"🎁 Забрать: {mission.title[:30]}", callback_data=f"stg:missions:claim:{mission.id}:{mission_type}")])

    type_row = [
        InlineKeyboardButton(text=("• " if t == mission_type else "") + t.title(), callback_data=f"stg:missions:{t}")
        for t in mission_types
    ]
    keyboard.insert(0, type_row)
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_season_track_keyboard(track) -> InlineKeyboardMarkup:
    keyboard = []
    for level in track.levels:
        if level.status == "AVAILABLE":
            keyboard.append([InlineKeyboardButton(text=f"🎁 Забрать уровень {level.level}", callback_data=f"stg:season:claim:{level.id}")])
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_store_keyboard(products, category: str, store_categories: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    for product in products:
        if product.available:
            keyboard.append([InlineKeyboardButton(text=f"💳 Купить: {product.title[:30]}", callback_data=f"stg:store:buy:{product.id}")])

    category_row = [
        InlineKeyboardButton(text=("• " if c == category else "") + c, callback_data=f"stg:store:{c}")
        for c in store_categories
    ]
    keyboard.insert(0, category_row)
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_wallet_history_keyboard(history) -> InlineKeyboardMarkup:
    keyboard = []
    nav_row = []
    if history.page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"stg:wallet_history:{history.page - 1}"))
    if history.page < history.pages_count:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"stg:wallet_history:{history.page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append(back_row())
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
