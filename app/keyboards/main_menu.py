from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_permissions import get_permission_for_callback, has_admin_permission
from app.utils.inline_navigation import suppress_auto_back_button


# DNA is a first-class main-menu system; keep all existing actions and add it directly.
# Редкие функции вынесены в «Прогресс» и «Ещё», чтобы главный экран не превращался
# в каталог из нескольких уровней.
USER_HOME_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🏒 Играть", "menu:open:matches"), ("🧩 Состав", "menu:open:lineup")),
    (("🃏 Карты", "menu:open:cards"), ("🎁 Паки", "menu:open:packs")),
    (("🏆 Ranked", "menu:open:ranked"), ("🏰 Stronghold", "menu:open:stronghold")),
    (("⚔️ Clan War", "menu:open:war2"), ("🧬 DNA", "menu:open:dna")),
    (("🕶 Чёрный рынок", "menu:open:black_market"), ("🛒 Магазин", "menu:open:shop")),
    (("🎨 Косметика", "menu:open:cosmetics"), ("🎯 Прогресс", "menu:user:progress")),
    (("☰ Ещё", "menu:user:more"),),
)

USER_PROGRESS_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🎯 Задания", "menu:open:quests"), ("🎟 Hockey Pass", "menu:open:hockey_pass")),
    (("📅 Ежедневный вход", "menu:open:daily"), ("🎁 Бесплатная карта", "menu:open:free_card")),
    (("🏆 Рейтинг", "menu:open:rating"), ("🎪 События", "menu:open:events")),
    (("⬅️ Главное меню", "menu:main"),),
)

USER_MORE_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("👤 Профиль", "menu:open:profile"), ("👥 Сообщество", "menu:open:community")),
    (("⭐ Креаторы", "menu:open:creators"), ("ℹ️ Как играть", "menu:user:help")),
    (("⬅️ Главное меню", "menu:main"),),
)


# Ровно 12 быстрых административных действий. Полная структура остаётся доступна
# через «Все разделы» и не загромождает первый экран.
ADMIN_HOME_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🃏 Карточки", "menu:open:admin_cards"), ("🎁 Паки", "menu:open:admin_packs")),
    (("👥 Пользователи", "menu:open:admin_users"), ("💱 Валюты", "menu:open:admin_wallets")),
    (("🏆 Ranked", "menu:open:admin_ranked"), ("🏰 Stronghold", "menu:open:admin_stronghold")),
    (("⚔️ Clan War", "menu:open:admin_war2"), ("🕶 Чёрный рынок", "menu:open:admin_black_market")),
    (("🎨 Косметика", "menu:open:admin_cosmetics"), ("🛠 Техперерыв", "menu:open:admin_maintenance")),
    (("📥 Массовая загрузка", "menu:open:admin_bulk"), ("☰ Все разделы", "menu:admin:all")),
)

ADMIN_ALL_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🃏 Контент", "menu:admin:content"), ("🎮 Режимы", "menu:admin:modes")),
    (("👥 Игроки", "menu:admin:players"), ("💰 Экономика", "menu:admin:economy")),
    (("🛡 Система", "menu:admin:system"), ("📊 Админ-панель", "menu:open:admin_panel")),
    (("⬅️ Быстрое меню", "menu:main"),),
)

ADMIN_CONTENT_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🃏 Карточки", "menu:open:admin_cards"), ("🎁 Паки", "menu:open:admin_packs")),
    (("🎨 Косметика", "menu:open:admin_cosmetics"), ("🎬 Видео паков", "menu:open:admin_pack_videos")),
    (("🖼 Рендеры", "menu:open:admin_render"), ("🏁 Стартовый набор", "menu:open:admin_starter_kit")),
    (("🏒 Дивизионы", "menu:open:admin_divisions"), ("🧪 Химия", "menu:open:admin_chemistry")),
    (("📥 Массовая загрузка", "menu:open:admin_bulk"),),
    (("⬅️ Все разделы", "menu:admin:all"),),
)

ADMIN_MODES_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🏆 Ranked", "menu:open:admin_ranked"), ("🏰 Stronghold", "menu:open:admin_stronghold")),
    (("🕐 Расписание", "menu:open:admin_stronghold_schedule"), ("⚔️ Clan War", "menu:open:admin_war2")),
    (("🤖 Боты", "menu:open:admin_ranked_bots"), ("🎪 События", "menu:open:admin_events")),
    (("🏆 Лиги", "menu:open:admin_rating"), ("🕶 Чёрный рынок", "menu:open:admin_black_market")),
    (("🏟 Арены", "menu:open:admin_arenas"),),
    (("📥 Массовая загрузка", "menu:open:admin_bulk"),),
    (("⬅️ Все разделы", "menu:admin:all"),),
)

ADMIN_PLAYERS_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("👥 Пользователи", "menu:open:admin_users"), ("🤝 Кланы", "menu:open:admin_clans")),
    (("🔁 Обмены", "menu:open:admin_trades"), ("🛡 Безопасность", "menu:open:admin_security")),
    (("⭐ Креаторы", "menu:open:admin_creators"), ("📥 Массовая загрузка", "menu:open:admin_bulk")),
    (("⬅️ Все разделы", "menu:admin:all"),),
)

ADMIN_ECONOMY_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("💱 Валюты", "menu:open:admin_wallets"), ("💵 Зарплаты", "menu:open:admin_salaries")),
    (("🎁 Награды", "menu:open:admin_rewards"), ("🎯 Задания", "menu:open:admin_quests")),
    (("🎟 Hockey Pass", "menu:open:admin_hockey_pass"), ("📅 Ежедневный вход", "menu:open:admin_daily")),
    (("🎫 Промокоды", "menu:open:admin_promo"), ("🎁 Бесплатная карта", "menu:open:admin_free_card")),
    (("📥 Массовая загрузка", "menu:open:admin_bulk"),),
    (("⬅️ Все разделы", "menu:admin:all"),),
)

ADMIN_SYSTEM_BUTTONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("🛠 Техперерыв", "menu:open:admin_maintenance"), ("🔒 Активные матчи", "menu:open:admin_match_locks")),
    (("⚙️ Настройки", "menu:open:admin_settings"), ("🔄 Сезон", "menu:open:admin_seasons")),
    (("📢 Рассылка", "menu:open:admin_broadcast"), ("📊 Админ-панель", "menu:open:admin_panel")),
    (("📥 Массовая загрузка", "menu:open:admin_bulk"),),
    (("⬅️ Все разделы", "menu:admin:all"),),
)


def _build(rows: Iterable[Iterable[tuple[str, str]]]) -> InlineKeyboardMarkup:
    # Корневые фото-меню и их собственные категории уже содержат продуманную
    # навигацию. Не добавляем к ним глобальную страховочную кнопку автоматически.
    with suppress_auto_back_button():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=text, callback_data=callback_data) for text, callback_data in row]
                for row in rows
            ]
        )


def _admin_rows_for_user(
    rows: Iterable[Iterable[tuple[str, str]]],
    user_id: int | None,
) -> list[list[tuple[str, str]]]:
    filtered: list[list[tuple[str, str]]] = []
    for row in rows:
        allowed_row: list[tuple[str, str]] = []
        for text, callback_data in row:
            # menu:open:* сам по себе не имеет permission-prefix, поэтому для
            # быстрых кнопок permission задаётся по целевому callback ниже.
            target_callback = ADMIN_TARGET_CALLBACKS.get(callback_data, callback_data)
            permission = get_permission_for_callback(target_callback)
            if permission is None or has_admin_permission(user_id, permission):
                allowed_row.append((text, callback_data))
        if allowed_row:
            filtered.append(allowed_row)
    return filtered


ADMIN_TARGET_CALLBACKS: dict[str, str] = {
    "menu:open:admin_cards": "admin_cards:main",
    "menu:open:admin_packs": "admin_packs:main",
    "menu:open:admin_users": "admin_users:main",
    "menu:open:admin_wallets": "admin_wallets:main",
    "menu:open:admin_ranked": "admin_ranked:main",
    "menu:open:admin_stronghold": "admin_stronghold:main",
    "menu:open:admin_war2": "admin_war2:main",
    "menu:open:admin_black_market": "bm_admin:main",
    "menu:open:admin_cosmetics": "admin_cosmetics:main",
    "menu:open:admin_maintenance": "admin_maintenance:main",
    "menu:open:admin_match_locks": "admin_security:match_locks:1",
    "menu:open:admin_panel": "admin_panel:main",
    "menu:open:admin_pack_videos": "admin_packs:videos:1",
    "menu:open:admin_render": "admin_render:main",
    "menu:open:admin_starter_kit": "starter_kit:main",
    "menu:open:admin_divisions": "admin_divisions:main",
    "menu:open:admin_chemistry": "chemistry:main",
    "menu:open:admin_stronghold_schedule": "admin_stronghold:schedule",
    "menu:open:admin_ranked_bots": "admin_ranked:bot_diag",
    "menu:open:admin_events": "admin_events:main",
    "menu:open:admin_rating": "admin_rating:main",
    "menu:open:admin_clans": "admin_clans:list:1",
    "menu:open:admin_arenas": "admin_arenas:main",
    "menu:open:admin_trades": "admin_trades:list:1",
    "menu:open:admin_security": "admin_security:main",
    "menu:open:admin_creators": "admin_creators:main",
    "menu:open:admin_salaries": "admin_salaries:main",
    "menu:open:admin_rewards": "admin_rewards:main",
    "menu:open:admin_quests": "admin_quests:main",
    "menu:open:admin_hockey_pass": "admin_hpass:main",
    "menu:open:admin_daily": "admin_daily:main",
    "menu:open:admin_promo": "admin_promo:main",
    "menu:open:admin_free_card": "free_card:admin",
    "menu:open:admin_settings": "admin_settings:main",
    "menu:open:admin_seasons": "season:main",
    "menu:open:admin_broadcast": "broadcast:main",
    "menu:open:admin_bulk": "admin_bulk:hub",
}


def build_user_home_keyboard() -> InlineKeyboardMarkup:
    return _build(USER_HOME_BUTTONS)


def build_user_progress_keyboard() -> InlineKeyboardMarkup:
    return _build(USER_PROGRESS_BUTTONS)


def build_user_more_keyboard() -> InlineKeyboardMarkup:
    return _build(USER_MORE_BUTTONS)


def build_admin_home_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_HOME_BUTTONS, user_id))


def build_admin_all_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_ALL_BUTTONS, user_id))


def build_admin_content_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_CONTENT_BUTTONS, user_id))


def build_admin_modes_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_MODES_BUTTONS, user_id))


def build_admin_players_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_PLAYERS_BUTTONS, user_id))


def build_admin_economy_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_ECONOMY_BUTTONS, user_id))


def build_admin_system_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return _build(_admin_rows_for_user(ADMIN_SYSTEM_BUTTONS, user_id))
