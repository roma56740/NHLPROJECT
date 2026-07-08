from html import escape

from app.services.currencies import format_currency_amount
from app.services.users import PlayerProfile, can_edit_team_profile


PROFILE_TEXT = """
<b>👤 Профиль игрока</b>

🏒 Никнейм: <b>{nickname}</b>
🏆 Лига: <b>{league}</b>
⭐ Очки рейтинга: <b>{rating_points}</b>

<b>📊 Статистика</b>
🏟 Матчи: <b>{matches_played}</b>
✅ Победы: <b>{wins}</b>
❌ Поражения: <b>{losses}</b>
🥅 Голы: <b>{goals_scored}</b>
🧤 Пропущено: <b>{goals_allowed}</b>

<b>🎟 Hockey Pass</b>
Сезон: <b>{hockey_pass_title}</b>
Уровень: <b>{hockey_pass_level}</b>
BP Points: <b>{bp_points}</b>
Premium: <b>{premium_pass}</b>

<b>💰 Баланс</b>
{balances}

<b>🏒 Команда</b>
Название: <b>{team_name}</b>
Страна: <b>{team_country}</b>
Логотип: <b>{team_logo}</b>

<b>🔐 Приватность</b>
Карточки: <b>{cards_privacy}</b>
""".strip()


PROFILE_SETTINGS_TEXT = """
<b>⚙️ Настройки профиля</b>

Здесь можно оформить профиль игрока и выбрать, что увидят другие участники лиги.

🏒 Никнейм: <b>{nickname}</b>
🌍 Карточки: <b>{cards_privacy}</b>

<b>🏆 Команда</b>
Название: <b>{team_name}</b>
Страна: <b>{team_country}</b>
Логотип: <b>{team_logo}</b>

{team_note}
""".strip()


EDIT_NICKNAME_TEXT = """
<b>✏️ Новый никнейм</b>

Отправь новый никнейм одним сообщением.

Минимум: <b>2 символа</b>
Максимум: <b>24 символа</b>
""".strip()


EDIT_TEAM_NAME_TEXT = """
<b>🏒 Название команды</b>

Отправь название команды одним сообщением.

Минимум: <b>2 символа</b>
Максимум: <b>32 символа</b>
""".strip()


EDIT_TEAM_COUNTRY_TEXT = """
<b>🌍 Страна команды</b>

Отправь страну команды одним сообщением.

Пример: <b>Canada</b>
""".strip()


EDIT_TEAM_LOGO_TEXT = """
<b>🖼 Логотип команды</b>

Отправь изображение логотипа одним сообщением.

Лучше выбрать квадратную картинку, чтобы эмблема красиво смотрелась в профиле.
""".strip()


OLYMPICS_LOCKED_TEXT = """
<b>🏆 Команда откроется в OLYMPICS</b>

Название, страна и логотип команды станут доступны после выхода в лигу <b>OLYMPICS</b>.

Продолжай побеждать, усиливай состав и поднимайся выше.
""".strip()


def build_balances_text(profile: PlayerProfile) -> str:
    if not profile.balances:
        return "Пока пусто"

    return "\n".join(format_currency_amount(balance) for balance in profile.balances)


def clean_user_text(value: str) -> str:
    return " ".join(value.strip().split())


def format_yes_no(value: bool) -> str:
    return "👑 открыт" if value else "не открыт"


def format_public_cards(value: bool) -> str:
    return "показываются" if value else "скрыты"


def format_safe(value: str | None) -> str:
    if value:
        return escape(value, quote=False)

    return "не выбрано"


def format_team_logo(value: str | None) -> str:
    return "добавлен" if value else "не загружен"


def build_team_note(profile: PlayerProfile) -> str:
    if can_edit_team_profile(profile):
        return "🏆 Команду можно оформить прямо сейчас."

    return "🏆 Название, страна и логотип команды откроются в лиге OLYMPICS."


def format_hockey_pass_title(value: str | None) -> str:
    return escape(value, quote=False) if value else "сезон не открыт"


def build_profile_text(profile: PlayerProfile) -> str:
    badge = " ✅" if getattr(profile, "is_creator", False) else ""
    return PROFILE_TEXT.format(
        nickname=format_safe(profile.nickname) + badge,
        league=format_safe(profile.league),
        rating_points=profile.rating_points,
        matches_played=profile.matches_played,
        wins=profile.wins,
        losses=profile.losses,
        goals_scored=profile.goals_scored,
        goals_allowed=profile.goals_allowed,
        hockey_pass_title=format_hockey_pass_title(profile.hockey_pass_title),
        hockey_pass_level=profile.hockey_pass_level,
        bp_points=profile.bp_points,
        premium_pass=format_yes_no(profile.hockey_pass_premium_active),
        balances=build_balances_text(profile),
        team_name=format_safe(profile.team_name),
        team_country=format_safe(profile.team_country),
        team_logo=format_team_logo(profile.team_logo_path),
        cards_privacy=format_public_cards(profile.privacy_public_cards),
    )


def build_profile_settings_text(profile: PlayerProfile) -> str:
    return PROFILE_SETTINGS_TEXT.format(
        nickname=format_safe(profile.nickname),
        cards_privacy=format_public_cards(profile.privacy_public_cards),
        team_name=format_safe(profile.team_name),
        team_country=format_safe(profile.team_country),
        team_logo=format_team_logo(profile.team_logo_path),
        team_note=build_team_note(profile),
    )


def validate_text_value(value: str | None, min_length: int, max_length: int) -> str | None:
    if value is None:
        return None

    clean_value = clean_user_text(value)

    if len(clean_value) < min_length:
        return None

    if len(clean_value) > max_length:
        return None

    return clean_value
