from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="profile:refresh")],
            [InlineKeyboardButton(text="🎫 Ввести промокод", callback_data="promo:enter")],
            [InlineKeyboardButton(text="⚙️ Настройки профиля", callback_data="profile:settings")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_profile_settings_keyboard(public_cards: bool) -> InlineKeyboardMarkup:
    privacy_text = "🔒 Скрыть карточки" if public_cards else "🌍 Показывать карточки"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить никнейм", callback_data="profile:edit_nickname")],
            [InlineKeyboardButton(text=privacy_text, callback_data="profile:toggle_cards_privacy")],
            [InlineKeyboardButton(text="🏒 Название команды", callback_data="profile:edit_team_name")],
            [InlineKeyboardButton(text="🌍 Страна команды", callback_data="profile:edit_team_country")],
            [InlineKeyboardButton(text="🖼 Логотип команды", callback_data="profile:edit_team_logo")],
            [InlineKeyboardButton(text="👤 К профилю", callback_data="profile:refresh")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_profile_edit_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="profile:cancel_edit")],
        ]
    )


def build_profile_olympics_locked_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ К настройкам", callback_data="profile:settings")],
            [InlineKeyboardButton(text="👤 К профилю", callback_data="profile:refresh")],
        ]
    )
