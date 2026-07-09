from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.services.admin_permissions import allowed_admin_buttons_for_user


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
    ["🏟 Арены", "🏒 Дивизионы"],
    ["💵 Зарплаты", "🎁 Награды"],
    ["📅 Ежедневный вход"],
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


def build_admin_main_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    rows = allowed_admin_buttons_for_user(user_id, ADMIN_MAIN_BUTTONS) if user_id is not None else ADMIN_MAIN_BUTTONS
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=button) for button in row]
            for row in rows
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел админ-панели",
    )
