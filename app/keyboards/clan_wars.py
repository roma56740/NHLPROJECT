from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.clan_wars import ArenaInfo


def build_wars_arenas_keyboard(arenas: list[ArenaInfo]) -> InlineKeyboardMarkup:
    keyboard = []
    for arena in arenas:
        holder = f" • 🏰 {arena.holder_clan_name}" if arena.holder_clan_name else " • нейтральная"
        keyboard.append(
            [InlineKeyboardButton(text=f"🏟 {arena.name}{holder}", callback_data=f"wars:arena:{arena.id}")]
        )
    keyboard.append([InlineKeyboardButton(text="⬅️ К кланам", callback_data="community:clans")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_arena_view_keyboard(arena: ArenaInfo, can_attack: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if can_attack:
        keyboard.append([InlineKeyboardButton(text="⚔️ Атаковать арену", callback_data=f"wars:attack:{arena.id}")])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"wars:arena:{arena.id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К аренам", callback_data="wars:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

def build_admin_arenas_main_keyboard(arenas: list[ArenaInfo]) -> InlineKeyboardMarkup:
    keyboard = []
    for arena in arenas:
        status = "🟢" if arena.active else "🔴"
        keyboard.append(
            [InlineKeyboardButton(text=f"{status} {arena.name}", callback_data=f"admin_arenas:view:{arena.id}")]
        )
    keyboard.append([InlineKeyboardButton(text="➕ Создать арену", callback_data="admin_arenas:create")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_arena_view_keyboard(arena: ArenaInfo) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить" if arena.active else "🟢 Включить"
    keyboard = [
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_arenas:edit_name:{arena.id}")],
        [InlineKeyboardButton(text="✏️ Описание", callback_data=f"admin_arenas:edit_description:{arena.id}")],
        [InlineKeyboardButton(text="🎯 Победы для захвата", callback_data=f"admin_arenas:edit_wins:{arena.id}")],
        [InlineKeyboardButton(text="💰 Валюта дохода", callback_data=f"admin_arenas:income_currency:{arena.id}")],
        [InlineKeyboardButton(text="💰 Сумма дохода", callback_data=f"admin_arenas:edit_income:{arena.id}")],
        [InlineKeyboardButton(text="🎁 Валюта бонуса захвата", callback_data=f"admin_arenas:capture_currency:{arena.id}")],
        [InlineKeyboardButton(text="🎁 Сумма бонуса захвата", callback_data=f"admin_arenas:edit_capture:{arena.id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin_arenas:toggle:{arena.id}")],
    ]
    if arena.holder_clan_id is not None:
        keyboard.append([InlineKeyboardButton(text="🕊 Освободить арену", callback_data=f"admin_arenas:release:{arena.id}")])
    keyboard.append([InlineKeyboardButton(text="🗑 Удалить арену", callback_data=f"admin_arenas:delete_confirm:{arena.id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К аренам", callback_data="admin_arenas:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_arena_delete_confirm_keyboard(arena_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin_arenas:delete:{arena_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_arenas:view:{arena_id}")],
        ]
    )


def build_arena_currency_keyboard(currencies: list[tuple[str, str, str]], prefix: str, arena_id: int | None = None) -> InlineKeyboardMarkup:
    """prefix examples: 'admin_arenas:set_income_currency', 'admin_arenas:create_income_currency'."""
    suffix = f":{arena_id}" if arena_id is not None else ""
    keyboard = [
        [InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"{prefix}:{code}{suffix}")]
        for code, name, icon in currencies
    ]
    keyboard.append([InlineKeyboardButton(text="🚫 Без награды", callback_data=f"{prefix}:none{suffix}")])
    back_callback = f"admin_arenas:view:{arena_id}" if arena_id is not None else "admin_arenas:main"
    keyboard.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_arena_cancel_keyboard(arena_id: int | None = None) -> InlineKeyboardMarkup:
    back_callback = f"admin_arenas:view:{arena_id}" if arena_id is not None else "admin_arenas:main"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data=back_callback)]]
    )
