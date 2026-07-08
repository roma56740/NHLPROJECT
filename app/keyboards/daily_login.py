from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.daily_login import DailyRewardDef


def build_daily_user_keyboard(can_claim: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if can_claim:
        keyboard.append([InlineKeyboardButton(text="🎁 Забрать награду", callback_data="daily:claim")])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="daily:main")])
    keyboard.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_daily_after_claim_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏒 Играть", callback_data="matches:main")],
            [InlineKeyboardButton(text="📅 К наградам", callback_data="daily:main")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

def build_admin_daily_main_keyboard(ladder: list[DailyRewardDef]) -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for reward in ladder:
        row.append(InlineKeyboardButton(text=f"День {reward.day}", callback_data=f"admin_daily:day:{reward.day}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_daily:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_day_keyboard(day: int, has_pack: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🪙 Изменить Coins", callback_data=f"admin_daily:edit_coins:{day}")],
        [InlineKeyboardButton(text="💵 Изменить Рубли", callback_data=f"admin_daily:edit_rubles:{day}")],
        [InlineKeyboardButton(text="🎁 Выбрать пак", callback_data=f"admin_daily:pack:{day}")],
    ]
    if has_pack:
        keyboard.append([InlineKeyboardButton(text="🚫 Убрать пак", callback_data=f"admin_daily:clear_pack:{day}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К дням", callback_data="admin_daily:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_day_pack_keyboard(day: int, packs: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=f"🎁 {name}", callback_data=f"admin_daily:set_pack:{day}:{pack_id}")]
        for pack_id, name in packs
    ]
    keyboard.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_daily:day:{day}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_day_cancel_keyboard(day: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_daily:day:{day}")]]
    )
