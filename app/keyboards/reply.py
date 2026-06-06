from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


USER_MAIN_BUTTONS: list[list[str]] = [
    ["🏠 Главная", "🏒 Играть"],
    ["🃏 Карты", "🧩 Состав"],
    ["🎁 Паки", "🛒 Магазин"],
    ["🎯 Задания", "🎟 Hockey Pass"],
    ["🏆 Рейтинг", "🤝 Сообщество"],
    ["👤 Профиль"],
]


ADMIN_MAIN_BUTTONS: list[list[str]] = [
    ["📊 Админ-панель", "🃏 Карточки"],
    ["🎁 Паки", "🛒 Магазин"],
    ["👥 Пользователи", "🎟 Hockey Pass"],
    ["🎯 Задания", "🏆 Лиги и рейтинг"],
    ["🧪 Химия", "🎪 События"],
    ["💱 Валюты", "🤝 Кланы"],
    ["🔁 Обмены", "🛡 Безопасность"],
    ["📢 Рассылка", "⚙️ Настройки"],
]


USER_MAIN_TEXTS: set[str] = {button for row in USER_MAIN_BUTTONS for button in row}
ADMIN_MAIN_TEXTS: set[str] = {button for row in ADMIN_MAIN_BUTTONS for button in row}


def build_user_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=button) for button in row]
            for row in USER_MAIN_BUTTONS
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


def build_admin_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=button) for button in row]
            for row in ADMIN_MAIN_BUTTONS
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел админ-панели",
    )
