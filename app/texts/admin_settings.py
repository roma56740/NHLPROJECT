from app.services.settings import GameSetting


ADMIN_SETTINGS_MAIN_TEXT = """
<b>⚙️ Настройки игры</b>

Здесь можно менять основные правила лиги без правки кода.

Выбери параметр, который нужно настроить.
""".strip()

ADMIN_SETTINGS_VALUE_TEXT = """
<b>✏️ Новое значение</b>

Введи новое значение для настройки.
""".strip()

ADMIN_SETTINGS_BAD_NUMBER_TEXT = """
<b>⚠️ Не получилось сохранить</b>

Введи целое число больше нуля.
""".strip()

ADMIN_SETTINGS_BAD_WAIT_TEXT = """
<b>⚠️ Проверь время поиска</b>

Минимальное время не должно быть больше максимального.
""".strip()

ADMIN_SETTINGS_SAVED_TEXT = """
<b>✅ Настройка сохранена</b>

Изменение уже применяется в игре.
""".strip()


SETTING_LABELS = {
    "maintenance_mode": "🛠 Режим обслуживания",
    "season_key": "🎮 Текущий сезон",
    "win_coins_reward": "🏆 Coins за победу",
    "loss_coins_reward": "💔 Coins за поражение",
    "bot_handicap_extra": "🤖 Ослабление ботов",
    "matchmaking_min_wait_seconds": "⏱ Минимум поиска",
    "matchmaking_max_wait_seconds": "⏱ Максимум поиска",
    "start_coins": "🪙 Стартовые Coins",
    "start_energy": "💵 Стартовые Рубли",
    "start_rank_points": "🏅 Стартовые Rank-point",
}


def format_setting_value(setting: GameSetting) -> str:
    if setting.key == "maintenance_mode":
        return "включён" if setting.value == "1" else "выключен"

    if setting.key in {"win_coins_reward", "loss_coins_reward", "start_coins", "start_energy", "start_rank_points", "bot_handicap_extra"}:
        return f"{int(setting.value):,}".replace(",", " ") if str(setting.value).isdigit() else setting.value

    if setting.key in {"matchmaking_min_wait_seconds", "matchmaking_max_wait_seconds"}:
        return f"{setting.value} сек."

    return setting.value


def build_admin_settings_text(settings: list[GameSetting]) -> str:
    rows = []

    for setting in settings:
        label = SETTING_LABELS.get(setting.key, setting.title)
        rows.append(f"{label}: <b>{format_setting_value(setting)}</b>")

    body = "\n".join(rows) if rows else "Настройки пока не найдены."

    return f"""
<b>⚙️ Настройки игры</b>

{body}

Все изменения применяются сразу после сохранения.
""".strip()


def build_admin_setting_edit_text(setting: GameSetting) -> str:
    label = SETTING_LABELS.get(setting.key, setting.title)
    return f"""
<b>{label}</b>

{setting.description}

Текущее значение: <b>{format_setting_value(setting)}</b>

Введи новое значение.
""".strip()
