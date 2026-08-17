from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable

from config import settings


ADMIN_ROLE_OWNER = "owner"
ADMIN_ROLE_SENIOR = "senior_admin"
ADMIN_ROLE_CONTENT = "content_admin"
ADMIN_ROLE_ECONOMY = "economy_admin"
ADMIN_ROLE_MODERATOR = "moderator"
ADMIN_ROLE_CLAN = "clan_admin"
ADMIN_ROLE_ANALYST = "analyst"


@dataclass(frozen=True)
class AdminRoleInfo:
    code: str
    title: str
    description: str


ADMIN_ROLES: dict[str, AdminRoleInfo] = {
    ADMIN_ROLE_OWNER: AdminRoleInfo(
        ADMIN_ROLE_OWNER,
        "👑 Главный админ",
        "Полный доступ. Выдаёт и снимает админку, получает базу и архивы.",
    ),
    ADMIN_ROLE_SENIOR: AdminRoleInfo(
        ADMIN_ROLE_SENIOR,
        "⭐ Старший админ",
        "Почти полный доступ к игровым настройкам без выдачи админок и выгрузки базы.",
    ),
    ADMIN_ROLE_CONTENT: AdminRoleInfo(
        ADMIN_ROLE_CONTENT,
        "🃏 Контент-админ",
        "Карты, массовая загрузка, паки, стартовый набор, дивизионы, картинки, химия и зарплаты.",
    ),
    ADMIN_ROLE_ECONOMY: AdminRoleInfo(
        ADMIN_ROLE_ECONOMY,
        "💰 Экономика",
        "Награды, магазин, паки, промокоды, квесты, события, Hockey Pass и ежедневный вход.",
    ),
    ADMIN_ROLE_MODERATOR: AdminRoleInfo(
        ADMIN_ROLE_MODERATOR,
        "🛡 Модератор",
        "Пользователи, блокировки, безопасность, жалобы, обмены и кланы без доступа к экономике.",
    ),
    ADMIN_ROLE_CLAN: AdminRoleInfo(
        ADMIN_ROLE_CLAN,
        "🏰 Клан-админ",
        "Кланы, арены, CLAN WAR 2.0 и статистика кланов.",
    ),
    ADMIN_ROLE_ANALYST: AdminRoleInfo(
        ADMIN_ROLE_ANALYST,
        "📊 Аналитик",
        "Просмотр админ-сводки, рейтинга и статистики без опасных действий.",
    ),
}

ADMIN_ROLE_ORDER = [
    ADMIN_ROLE_SENIOR,
    ADMIN_ROLE_CONTENT,
    ADMIN_ROLE_ECONOMY,
    ADMIN_ROLE_MODERATOR,
    ADMIN_ROLE_CLAN,
    ADMIN_ROLE_ANALYST,
]

# Разделы админки. Middleware блокирует и текстовые кнопки, и callback-префиксы.
PERMISSION_ADMIN_PANEL = "admin_panel"
PERMISSION_ADMIN_ROLES = "admin_roles"
PERMISSION_DATA_EXPORT = "data_export"
PERMISSION_CARDS = "cards"
PERMISSION_PACKS = "packs"
PERMISSION_FREE_CARDS = "free_cards"
PERMISSION_STARTER_KIT = "starter_kit"
PERMISSION_DIVISIONS = "divisions"
PERMISSION_SALARIES = "salaries"
PERMISSION_CHEMISTRY = "chemistry"
PERMISSION_REWARDS = "rewards"
PERMISSION_USERS = "users"
PERMISSION_WALLETS = "wallets"
PERMISSION_SECURITY = "security"
PERMISSION_SETTINGS = "settings"
PERMISSION_BROADCAST = "broadcast"
PERMISSION_PROMO = "promo"
PERMISSION_CREATORS = "creators"
PERMISSION_SEASONS = "seasons"
PERMISSION_RATING_ADMIN = "rating_admin"
PERMISSION_QUESTS = "quests"
PERMISSION_EVENTS = "events"
PERMISSION_HOCKEY_PASS = "hockey_pass"
PERMISSION_DAILY_LOGIN = "daily_login"
PERMISSION_SHOP = "shop"
PERMISSION_CLANS = "clans"
PERMISSION_ARENAS = "arenas"
PERMISSION_TRADES = "trades"
PERMISSION_STRONGHOLD = "stronghold"
PERMISSION_WAR2 = "war2"
PERMISSION_RANKED = "ranked"
PERMISSION_BLACK_MARKET = "black_market"
PERMISSION_COSMETICS = "cosmetics"

ALL_PERMISSIONS = {
    PERMISSION_ADMIN_PANEL,
    PERMISSION_ADMIN_ROLES,
    PERMISSION_DATA_EXPORT,
    PERMISSION_CARDS,
    PERMISSION_PACKS,
    PERMISSION_FREE_CARDS,
    PERMISSION_STARTER_KIT,
    PERMISSION_DIVISIONS,
    PERMISSION_SALARIES,
    PERMISSION_CHEMISTRY,
    PERMISSION_REWARDS,
    PERMISSION_USERS,
    PERMISSION_WALLETS,
    PERMISSION_SECURITY,
    PERMISSION_SETTINGS,
    PERMISSION_BROADCAST,
    PERMISSION_PROMO,
    PERMISSION_CREATORS,
    PERMISSION_SEASONS,
    PERMISSION_RATING_ADMIN,
    PERMISSION_QUESTS,
    PERMISSION_EVENTS,
    PERMISSION_HOCKEY_PASS,
    PERMISSION_DAILY_LOGIN,
    PERMISSION_SHOP,
    PERMISSION_CLANS,
    PERMISSION_ARENAS,
    PERMISSION_TRADES,
    PERMISSION_STRONGHOLD,
    PERMISSION_WAR2,
    PERMISSION_RANKED,
    PERMISSION_BLACK_MARKET,
    PERMISSION_COSMETICS,
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ADMIN_ROLE_OWNER: set(ALL_PERMISSIONS),
    ADMIN_ROLE_SENIOR: set(ALL_PERMISSIONS) - {PERMISSION_ADMIN_ROLES, PERMISSION_DATA_EXPORT},
    ADMIN_ROLE_CONTENT: {
        PERMISSION_ADMIN_PANEL,
        PERMISSION_CARDS,
        PERMISSION_PACKS,
        PERMISSION_FREE_CARDS,
        PERMISSION_STARTER_KIT,
        PERMISSION_DIVISIONS,
        PERMISSION_SALARIES,
        PERMISSION_CHEMISTRY,
        PERMISSION_REWARDS,
        PERMISSION_COSMETICS,
    },
    ADMIN_ROLE_ECONOMY: {
        PERMISSION_ADMIN_PANEL,
        PERMISSION_REWARDS,
        PERMISSION_SHOP,
        PERMISSION_PACKS,
        PERMISSION_PROMO,
        PERMISSION_QUESTS,
        PERMISSION_EVENTS,
        PERMISSION_HOCKEY_PASS,
        PERMISSION_DAILY_LOGIN,
        PERMISSION_CREATORS,
        PERMISSION_STRONGHOLD,
        PERMISSION_WAR2,
        PERMISSION_RANKED,
        PERMISSION_BLACK_MARKET,
    },
    ADMIN_ROLE_MODERATOR: {
        PERMISSION_ADMIN_PANEL,
        PERMISSION_USERS,
        PERMISSION_SECURITY,
        PERMISSION_CLANS,
        PERMISSION_TRADES,
        PERMISSION_BROADCAST,
        PERMISSION_RATING_ADMIN,
    },
    ADMIN_ROLE_CLAN: {
        PERMISSION_ADMIN_PANEL,
        PERMISSION_CLANS,
        PERMISSION_ARENAS,
            PERMISSION_TRADES,
        PERMISSION_RATING_ADMIN,
        PERMISSION_WAR2,
    },
    ADMIN_ROLE_ANALYST: {
        PERMISSION_ADMIN_PANEL,
        PERMISSION_RATING_ADMIN,
    },
}

ADMIN_TEXT_PERMISSIONS: dict[str, str] = {
    "📊 Админ-панель": PERMISSION_ADMIN_PANEL,
    "🃏 Карточки": PERMISSION_CARDS,
    "🏁 Стартовый набор": PERMISSION_STARTER_KIT,
    "🎁 Паки": PERMISSION_PACKS,
    "🛒 Магазин": PERMISSION_SHOP,
    "👥 Пользователи": PERMISSION_USERS,
    "🎟 Hockey Pass": PERMISSION_HOCKEY_PASS,
    "🎁 Бесплатная карточка": PERMISSION_FREE_CARDS,
    "🎯 Задания": PERMISSION_QUESTS,
    "🏆 Лиги и рейтинг": PERMISSION_RATING_ADMIN,
    "🧪 Химия": PERMISSION_CHEMISTRY,
    "🎪 События": PERMISSION_EVENTS,
    "🏰 THE STRONGHOLD": PERMISSION_STRONGHOLD,
    "💱 Валюты": PERMISSION_WALLETS,
    "🤝 Кланы": PERMISSION_CLANS,
    "🏟 Арены": PERMISSION_ARENAS,
    "🏒 Дивизионы": PERMISSION_DIVISIONS,
    "💵 Зарплаты": PERMISSION_SALARIES,
    "🎁 Награды": PERMISSION_REWARDS,
    "📅 Ежедневный вход": PERMISSION_DAILY_LOGIN,
    "🎫 Промокоды": PERMISSION_PROMO,
    "⭐ Креаторы": PERMISSION_CREATORS,
    "🔄 Сброс сезона": PERMISSION_SEASONS,
    "🔁 Обмены": PERMISSION_TRADES,
    "🛡 Безопасность": PERMISSION_SECURITY,
    "📢 Рассылка": PERMISSION_BROADCAST,
    "⚙️ Настройки": PERMISSION_SETTINGS,
    "🕶 Чёрный рынок": PERMISSION_BLACK_MARKET,
    "🏆 Админка Ranked": PERMISSION_RANKED,
    "🤖 Диагностика ботов": PERMISSION_RANKED,
    "🕐 Расписание Stronghold": PERMISSION_STRONGHOLD,
    "⚔️ Админка Clan War 2.0": PERMISSION_WAR2,
    "🛠 Технический перерыв": PERMISSION_SETTINGS,
    "🔒 Активные матчи": PERMISSION_SECURITY,
    "🎬 Видео паков": PERMISSION_PACKS,
    "🎨 Управление косметикой": PERMISSION_COSMETICS,
}

CALLBACK_PERMISSION_PREFIXES: tuple[tuple[str, str], ...] = (
    ("admin_panel:admins", PERMISSION_ADMIN_ROLES),
    ("admin_panel:data", PERMISSION_DATA_EXPORT),
    ("admin_panel:admin_", PERMISSION_ADMIN_ROLES),
    ("admin_panel:role_", PERMISSION_ADMIN_ROLES),
    ("admin_panel:get_", PERMISSION_DATA_EXPORT),
    ("admin_bulk:", PERMISSION_ADMIN_PANEL),
    ("admin_cards:", PERMISSION_CARDS),
    ("admin_bulk_cards:", PERMISSION_CARDS),
    ("bulk_cards:", PERMISSION_CARDS),
    ("packs:admin", PERMISSION_PACKS),
    ("admin_packs:", PERMISSION_PACKS),
    ("free_card:admin", PERMISSION_FREE_CARDS),
    ("starter_kit:", PERMISSION_STARTER_KIT),
    ("admin_divisions:", PERMISSION_DIVISIONS),
    ("admin_salaries:", PERMISSION_SALARIES),
    ("admin_chemistry:", PERMISSION_CHEMISTRY),
    ("chemistry:", PERMISSION_CHEMISTRY),
    ("admin_rewards:", PERMISSION_REWARDS),
    ("admin_users:", PERMISSION_USERS),
    ("admin_wallets:", PERMISSION_WALLETS),
    ("admin_security:", PERMISSION_SECURITY),
    ("admin_settings:", PERMISSION_SETTINGS),
    ("admin_render:", PERMISSION_COSMETICS),
    ("admin_maintenance:", PERMISSION_SETTINGS),
    ("broadcast:", PERMISSION_BROADCAST),
    ("admin_promo:", PERMISSION_PROMO),
    ("creators:admin", PERMISSION_CREATORS),
    ("admin_creators:", PERMISSION_CREATORS),
    ("season:", PERMISSION_SEASONS),
    ("clan_season:", PERMISSION_SEASONS),
    ("admin_rating:", PERMISSION_RATING_ADMIN),
    ("admin_quests:", PERMISSION_QUESTS),
    ("events:admin", PERMISSION_EVENTS),
    ("admin_events:", PERMISSION_EVENTS),
    ("hockey_pass:admin", PERMISSION_HOCKEY_PASS),
    ("admin_hpass:", PERMISSION_HOCKEY_PASS),
    ("daily_login:admin", PERMISSION_DAILY_LOGIN),
    ("admin_daily:", PERMISSION_DAILY_LOGIN),
    ("shop:admin", PERMISSION_SHOP),
    ("admin_clans:", PERMISSION_CLANS),
    ("admin_arenas:", PERMISSION_ARENAS),
    ("admin_trades:", PERMISSION_TRADES),
    ("admin_stronghold:", PERMISSION_STRONGHOLD),
    ("admin_war2:", PERMISSION_WAR2),
    ("admin_ranked:", PERMISSION_RANKED),
    ("admin_cosmetics:", PERMISSION_COSMETICS),
    ("bm_admin:", PERMISSION_BLACK_MARKET),
)

COMMAND_PERMISSIONS: dict[str, str] = {
    "db_get": PERMISSION_DATA_EXPORT,
}


def normalize_admin_role(role: str | None) -> str:
    role = str(role or "").strip()
    if role in ADMIN_ROLES:
        return role
    return ADMIN_ROLE_SENIOR


def get_admin_role_title(role: str | None) -> str:
    return ADMIN_ROLES.get(normalize_admin_role(role), ADMIN_ROLES[ADMIN_ROLE_SENIOR]).title


def is_owner_admin(user_id: int | None) -> bool:
    return bool(user_id is not None and user_id in settings.admin_ids)


def _fetch_panel_role(user_id: int) -> str | None:
    try:
        connection = sqlite3.connect(settings.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT role
                FROM bot_admins
                WHERE telegram_id = ? AND active = 1
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            return str(row["role"] or ADMIN_ROLE_SENIOR) if row is not None else None
        finally:
            connection.close()
    except sqlite3.Error:
        return None


def get_admin_role(user_id: int | None) -> str | None:
    if user_id is None:
        return None
    if is_owner_admin(user_id):
        return ADMIN_ROLE_OWNER
    return _fetch_panel_role(int(user_id))


def is_panel_admin(user_id: int | None) -> bool:
    return get_admin_role(user_id) is not None


def has_admin_permission(user_id: int | None, permission: str | None) -> bool:
    if not permission:
        return is_panel_admin(user_id)
    role = get_admin_role(user_id)
    if role is None:
        return False
    if role == ADMIN_ROLE_OWNER:
        return True
    return permission in ROLE_PERMISSIONS.get(role, set())


def get_permission_for_admin_text(text: str | None) -> str | None:
    return ADMIN_TEXT_PERMISSIONS.get(str(text or ""))


def get_permission_for_callback(data: str | None) -> str | None:
    text = str(data or "")
    for prefix, permission in CALLBACK_PERMISSION_PREFIXES:
        if text.startswith(prefix):
            return permission
    return None


def get_permission_for_command(text: str | None) -> str | None:
    if not text or not text.startswith("/"):
        return None
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lstrip("/")
    return COMMAND_PERMISSIONS.get(command)


def allowed_admin_buttons_for_user(user_id: int | None, rows: Iterable[Iterable[str]]) -> list[list[str]]:
    result: list[list[str]] = []
    for row in rows:
        allowed_row = []
        for text in row:
            permission = get_permission_for_admin_text(text)
            if permission is None or has_admin_permission(user_id, permission):
                allowed_row.append(text)
        if allowed_row:
            result.append(allowed_row)
    return result
