from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


USER_MAIN_BUTTONS: list[list[str]] = [
    ["🏒 Играть", "🧩 Состав"],
    ["🃏 Карты", "🎁 Паки"],
    ["🛒 Магазин", "🎁 Бесплатная карточка"],
    ["🎟 Hockey Pass", "🎯 Задания"],
    ["🤝 Сообщество", "🏆 Рейтинг"],
    ["📅 Ежедневный вход", "⭐ Программа креаторов"],
    ["🏠 Главная", "👤 Профиль"],
]


ADMIN_MAIN_BUTTONS: list[list[str]] = [
    ["📊 Админ-панель", "🃏 Карточки"],
    ["🏁 Стартовый набор", "🎁 Паки"],
    ["🛒 Магазин"],
    ["👥 Пользователи", "🎟 Hockey Pass"],
    ["🎁 Бесплатная карточка", "🎯 Задания"],
    ["🏆 Лиги и рейтинг"],
    ["🧪 Химия", "🎪 События"],
    ["💱 Валюты", "🤝 Кланы"],
    ["🏟 Арены", "📅 Ежедневный вход"],
    ["🎫 Промокоды", "⭐ Креаторы"],
    ["🔄 Сброс сезона"],
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
