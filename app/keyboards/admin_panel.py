from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_admin_panel_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Админы", callback_data="admin_panel:admins")],
            [InlineKeyboardButton(text="📦 База и картинки", callback_data="admin_panel:data")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_panel:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admins_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_panel:admin_add")],
            [InlineKeyboardButton(text="➖ Убрать админа", callback_data="admin_panel:admin_remove")],
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
