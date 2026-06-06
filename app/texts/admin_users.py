from html import escape

from app.services.admin_users import AdminUserProfile, AdminUsersPage
from app.services.currencies import format_currency_amount
from app.services.user_cards import CardChoicePage


ADMIN_USERS_MAIN_TEXT = """
<b>👥 Игроки</b>

Здесь можно найти игрока, открыть профиль, начислить валюту, выдать Premium Pass, изменить лигу или ограничить доступ.
""".strip()

ADMIN_USERS_SEARCH_TEXT = """
<b>🔎 Поиск игрока</b>

Отправь никнейм, username или ID игрока.
""".strip()

ADMIN_USERS_EMPTY_TEXT = """
<b>👥 Игроки не найдены</b>

Попробуй изменить запрос или открыть полный список игроков.
""".strip()

ADMIN_USERS_CURRENCY_TEXT = """
<b>💱 Выдать валюту</b>

Выбери валюту для игрока:
<b>{nickname}</b>
""".strip()

ADMIN_USERS_CURRENCY_AMOUNT_TEXT = """
<b>{currency_title}</b>

Отправь сумму одним сообщением.

Пример: <b>10000</b>
Для списания можно указать сумму с минусом.
""".strip()

ADMIN_USERS_LEAGUE_TEXT = """
<b>🏆 Лига игрока</b>

Игрок: <b>{nickname}</b>
Текущая лига: <b>{league}</b>

Выбери новую лигу.
""".strip()

ADMIN_USERS_GIVE_CARD_SEARCH_TEXT = """
<b>🔎 Поиск карточки</b>

Отправь имя игрока, команду, страну, коллекцию, редкость, позицию или ID карточки.
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def yes_no(value: bool) -> str:
    return "да" if value else "нет"


def premium_status(profile: AdminUserProfile) -> str:
    if not profile.hockey_pass_title:
        return "нет активного сезона"

    return "👑 открыт" if profile.hockey_pass_premium_unlocked else "не открыт"


def active_hidden(value: bool) -> str:
    return "показываются" if value else "скрыты"


def player_status(profile: AdminUserProfile) -> str:
    if profile.is_banned:
        return "🚫 ограничен"

    return "✅ активен"


def format_balances(profile: AdminUserProfile) -> str:
    if not profile.balances:
        return "Пока пусто"

    return "\n".join(format_currency_amount(balance) for balance in profile.balances)


def build_admin_users_page_text(page: AdminUsersPage) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return ADMIN_USERS_EMPTY_TEXT

    return f"""
<b>👥 Игроки</b>

Всего игроков: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери игрока из списка ниже.
""".strip()


def build_admin_user_profile_text(profile: AdminUserProfile) -> str:
    username = f"@{profile.username}" if profile.username else "не указан"
    full_name = " ".join(part for part in [profile.first_name, profile.last_name] if part)

    return f"""
<b>👤 Карточка игрока</b>

🏒 Никнейм: <b>{safe(profile.nickname)}</b>
🌐 Username: <b>{safe(username)}</b>
👥 Имя: <b>{safe(full_name)}</b>
🆔 ID игрока: <b>{profile.telegram_id}</b>

<b>🏆 Прогресс</b>
Лига: <b>{safe(profile.league)}</b>
Очки рейтинга: <b>{profile.rating_points}</b>
Матчи: <b>{profile.matches_played}</b>
Победы: <b>{profile.wins}</b>
Поражения: <b>{profile.losses}</b>
Голы: <b>{profile.goals_scored}</b>
Пропущено: <b>{profile.goals_allowed}</b>

<b>🎟 Hockey Pass</b>
Сезон: <b>{safe(profile.hockey_pass_title)}</b>
Уровень: <b>{profile.hockey_pass_level}</b>
BP Points: <b>{profile.bp_points}</b>
Premium: <b>{premium_status(profile)}</b>

<b>💰 Баланс</b>
{format_balances(profile)}

<b>🃏 Коллекция</b>
Карточек: <b>{profile.cards_count}</b>
Паков: <b>{profile.packs_count}</b>

<b>🏒 Команда</b>
Название: <b>{safe(profile.team_name)}</b>
Страна: <b>{safe(profile.team_country)}</b>
Логотип: <b>{'загружен' if profile.team_logo_path else 'не загружен'}</b>

<b>🔐 Профиль</b>
Карточки: <b>{active_hidden(profile.privacy_public_cards)}</b>
Статус: <b>{player_status(profile)}</b>
""".strip()


def get_currency_title(currency_code: str) -> str:
    titles = {
        "coins": "🪙 Coins",
        "energy": "⚡ Energy",
        "rank_point": "🏅 Rank-point",
    }

    return titles.get(currency_code, "💱 Валюта")


def build_admin_give_card_page_text(page: CardChoicePage, nickname: str) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return f"""
<b>🃏 Выдать карточку</b>

Игрок: <b>{safe(nickname)}</b>

Подходящие карточки не найдены.
Попробуй изменить запрос или открыть полный список.
""".strip()

    return f"""
<b>🃏 Выдать карточку</b>

Игрок: <b>{safe(nickname)}</b>
Карточек найдено: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери карточку для выдачи.
""".strip()
