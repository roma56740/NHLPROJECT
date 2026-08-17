from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.services.admin_permissions import allowed_admin_buttons_for_user
from app.keyboards.main_menu import (
    build_admin_home_keyboard as _build_admin_home_keyboard,
    build_user_home_keyboard as _build_user_home_keyboard,
)


# ---------------------------------------------------------------------------
# Пользовательская навигация
# ---------------------------------------------------------------------------
# Главное меню намеренно короткое: пользователь сначала выбирает понятную цель,
# затем получает только относящиеся к ней действия. Это убирает длинную клавиатуру
# из 10+ строк и делает первый шаг очевидным.
USER_MAIN_BUTTONS: list[list[str]] = [
    ["🎮 Играть", "🧩 Команда"],
    ["🎁 Паки", "🎯 Мой прогресс"],
    ["🛒 Магазин", "👥 Сообщество"],
    ["👤 Профиль", "ℹ️ Как играть"],
    ["🏠 Главная"],
]

USER_GAMES_BUTTONS: list[list[str]] = [
    ["🏒 Играть", "🏆 Ranked Mode"],
    ["🏰 THE STRONGHOLD", "⚔️ CLAN WAR 2.0"],
    ["🕶 Чёрный рынок"],
    ["⬅️ Главное меню"],
]

USER_TEAM_BUTTONS: list[list[str]] = [
    ["🧩 Состав", "🃏 Карты"],
    ["🎨 Косметика", "🎁 Паки"],
    ["⬅️ Главное меню"],
]

USER_PROGRESS_BUTTONS: list[list[str]] = [
    ["🎯 Задания", "🎟 Hockey Pass"],
    ["📅 Ежедневный вход", "🎁 Бесплатная карточка"],
    ["🏆 Рейтинг", "⭐ Программа креаторов"],
    ["⬅️ Главное меню"],
]

USER_COMMUNITY_BUTTONS: list[list[str]] = [
    ["🤝 Сообщество", "⚔️ CLAN WAR 2.0"],
    ["🏆 Рейтинг", "⭐ Программа креаторов"],
    ["⬅️ Главное меню"],
]


# ---------------------------------------------------------------------------
# Административная навигация
# ---------------------------------------------------------------------------
# Вместо одной клавиатуры на несколько экранов — пять логических разделов.
ADMIN_MAIN_BUTTONS: list[list[str]] = [
    ["🃏 Контент", "🎮 Режимы"],
    ["👥 Игроки", "💰 Экономика"],
    ["🛡 Система", "📊 Админ-панель"],
]

ADMIN_CONTENT_BUTTONS: list[list[str]] = [
    ["🃏 Карточки", "🎁 Паки"],
    ["🎨 Управление косметикой", "🎬 Видео паков"],
    ["🏁 Стартовый набор"],
    ["🏒 Дивизионы", "🧪 Химия"],
    ["⬅️ Админ-центр"],
]

ADMIN_MODES_BUTTONS: list[list[str]] = [
    ["🏆 Админка Ranked", "🏰 THE STRONGHOLD"],
    ["🕐 Расписание Stronghold", "⚔️ Админка Clan War 2.0"],
    ["🤖 Диагностика ботов", "🎪 События"],
    ["🏟 Арены"],
    ["🏆 Лиги и рейтинг", "🕶 Чёрный рынок"],
    ["⬅️ Админ-центр"],
]

ADMIN_PLAYERS_BUTTONS: list[list[str]] = [
    ["👥 Пользователи", "🤝 Кланы"],
    ["🔁 Обмены", "🛡 Безопасность"],
    ["⭐ Креаторы"],
    ["⬅️ Админ-центр"],
]

ADMIN_ECONOMY_BUTTONS: list[list[str]] = [
    ["💱 Валюты", "💵 Зарплаты"],
    ["🎁 Награды", "🛒 Магазин"],
    ["🎯 Задания", "🎟 Hockey Pass"],
    ["📅 Ежедневный вход", "🎫 Промокоды"],
    ["🎁 Бесплатная карточка"],
    ["⬅️ Админ-центр"],
]

ADMIN_SYSTEM_BUTTONS: list[list[str]] = [
    ["🛠 Технический перерыв", "🔒 Активные матчи"],
    ["⚙️ Настройки", "🔄 Сброс сезона"],
    ["📢 Рассылка", "📊 Админ-панель"],
    ["⬅️ Админ-центр"],
]


# Эти множества используются FSM-хендлерами: нажатие любой навигационной кнопки
# должно корректно вывести пользователя из незавершённого ввода.
USER_MAIN_TEXTS: set[str] = {
    button
    for menu in (
        USER_MAIN_BUTTONS,
        USER_GAMES_BUTTONS,
        USER_TEAM_BUTTONS,
        USER_PROGRESS_BUTTONS,
        USER_COMMUNITY_BUTTONS,
    )
    for row in menu
    for button in row
}

ADMIN_MAIN_TEXTS: set[str] = {
    button
    for menu in (
        ADMIN_MAIN_BUTTONS,
        ADMIN_CONTENT_BUTTONS,
        ADMIN_MODES_BUTTONS,
        ADMIN_PLAYERS_BUTTONS,
        ADMIN_ECONOMY_BUTTONS,
        ADMIN_SYSTEM_BUTTONS,
    )
    for row in menu
    for button in row
}


def _build_keyboard(rows: list[list[str]], placeholder: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=button) for button in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


def _build_admin_keyboard(rows: list[list[str]], user_id: int | None, placeholder: str) -> ReplyKeyboardMarkup:
    allowed_rows = allowed_admin_buttons_for_user(user_id, rows) if user_id is not None else rows
    return _build_keyboard(allowed_rows, placeholder)


def build_user_main_keyboard():
    """Совместимый alias: главное меню теперь inline, а не нижняя ReplyKeyboard."""
    return _build_user_home_keyboard()


def build_user_games_keyboard() -> ReplyKeyboardMarkup:
    return _build_keyboard(USER_GAMES_BUTTONS, "Выбери игровой режим")


def build_user_team_keyboard() -> ReplyKeyboardMarkup:
    return _build_keyboard(USER_TEAM_BUTTONS, "Управление командой")


def build_user_progress_keyboard() -> ReplyKeyboardMarkup:
    return _build_keyboard(USER_PROGRESS_BUTTONS, "Прогресс и награды")


def build_user_community_keyboard() -> ReplyKeyboardMarkup:
    return _build_keyboard(USER_COMMUNITY_BUTTONS, "Сообщество и кланы")


def build_admin_main_keyboard(user_id: int | None = None):
    """Совместимый alias: админ-центр теперь inline под фотографией."""
    return _build_admin_home_keyboard(user_id)


def build_admin_content_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    return _build_admin_keyboard(ADMIN_CONTENT_BUTTONS, user_id, "Карты, паки и игровые данные")


def build_admin_modes_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    return _build_admin_keyboard(ADMIN_MODES_BUTTONS, user_id, "Управление игровыми режимами")


def build_admin_players_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    return _build_admin_keyboard(ADMIN_PLAYERS_BUTTONS, user_id, "Игроки, кланы и безопасность")


def build_admin_economy_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    return _build_admin_keyboard(ADMIN_ECONOMY_BUTTONS, user_id, "Экономика и награды")


def build_admin_system_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    return _build_admin_keyboard(ADMIN_SYSTEM_BUTTONS, user_id, "Системные инструменты")
