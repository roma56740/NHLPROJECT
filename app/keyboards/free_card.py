from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_free_card_user_keyboard(is_ready: bool) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    if is_ready:
        buttons.append([
            InlineKeyboardButton(text="🎁 Получить карточку", callback_data="free_card:claim"),
        ])

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="free_card:user"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_free_card_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить карточку", callback_data="free_card:claim")],
            [InlineKeyboardButton(text="⏳ Посмотреть таймер", callback_data="free_card:user")],
        ]
    )


def build_free_card_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Выбрать коллекцию", callback_data="free_card:admin:set_collection")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="free_card:admin")],
        ]
    )


def build_free_card_admin_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="free_card:admin")],
        ]
    )
