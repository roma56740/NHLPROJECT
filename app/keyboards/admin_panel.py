from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_permissions import ADMIN_ROLE_ORDER, ADMIN_ROLES


def build_admin_panel_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Админы", callback_data="admin_panel:admins")],
            [InlineKeyboardButton(text="📦 База и картинки", callback_data="admin_panel:data")],
            [InlineKeyboardButton(text="🏒 Дивизионы и анимация", callback_data="admin_divisions:main")],
            [InlineKeyboardButton(text="💵 Зарплаты", callback_data="admin_salaries:main")],
            [InlineKeyboardButton(text="🎁 Награды", callback_data="admin_rewards:main")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_panel:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admins_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_panel:admin_add")],
            [InlineKeyboardButton(text="➖ Убрать админа", callback_data="admin_panel:admin_remove")],
            [InlineKeyboardButton(text="🎚 Изменить уровень", callback_data="admin_panel:role_change")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_panel:admins")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel:main")],
        ]
    )


def build_admin_data_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗄 Получить базу", callback_data="admin_panel:get_db")],
            [InlineKeyboardButton(text="🖼 Получить картинки", callback_data="admin_panel:get_uploads")],
            [InlineKeyboardButton(text="📦 Получить всё", callback_data="admin_panel:get_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel:main")],
        ]
    )


def build_cancel_admin_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel:cancel_input")],
        ]
    )


def build_admin_role_keyboard(prefix: str) -> InlineKeyboardMarkup:
    keyboard = []
    for role in ADMIN_ROLE_ORDER:
        info = ADMIN_ROLES[role]
        keyboard.append([InlineKeyboardButton(text=info.title, callback_data=f"{prefix}:{role}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel:admins")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_change_role_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return build_admin_role_keyboard(f"admin_panel:role_set:{telegram_id}")
