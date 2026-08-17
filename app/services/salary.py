"""Потолок зарплат.

Зарплата хранится в тысячах долларов (целое число): $5.5M -> 5500.
Так избегаем чисел с плавающей точкой при суммировании и сравнении с лимитом.
"""

# Лимиты зарплат по лигам (в тысячах $).
LEAGUE_SALARY_CAPS = {
    "NCAA": 20000,
    "AHL": 26000,
    "NHL": 34000,
    "OLYMPICS": 54000,
}

# Отдельный лимит для клановых войн.
CLAN_WAR_SALARY_CAP = 70000

# THE STRONGHOLD: $45 000 000 из спеки события в единицах проекта (тысячи $) = 45000.
STRONGHOLD_SALARY_CAP = 45000

# CLAN WAR 2.0, режим SALARY_WAR: $50 000 000 из ТЗ в единицах проекта (тысячи $) = 50000.
# Отдельная константа от CLAN_WAR_SALARY_CAP=70000 — тот принадлежит старой системе
# CLAN WAR 2.0 использует собственный лимит зарплат.
WAR2_SALARY_CAP = 50000

# RANKED MODE: $54 000 000 из ТЗ (тысячи $) = 54000 — не 54_000_000 буквально.
# Единственный лимит, который использует Ranked Mode; обычный режим лимита не имеет
# вовсе (раздел NORMAL MODE ТЗ) — league_cap()/LEAGUE_SALARY_CAPS там больше не
# применяются к запуску матча.
RANKED_SALARY_CAP = 54000

DEFAULT_CAP = 34000

# RANKED CAPTAIN: +$20 000 000 (тысячи $ проекта = 20000) к потолку Ranked Mode,
# если у капитана >= RANKED_CAPTAIN_MIN_DIVISION_CARDS карт его дивизиона в составе
# (сам капитан входит в подсчёт). Бонус НЕ действует нигде, кроме Ranked Mode —
# см. app/services/ranked_captain.py, вызывается только из ranked_core.play_ranked_match().
RANKED_CAPTAIN_BONUS = 20000
RANKED_CAPTAIN_MIN_DIVISION_CARDS = 5


def league_cap(league: str | None) -> int:
    return LEAGUE_SALARY_CAPS.get((league or "").upper(), DEFAULT_CAP)


def format_salary_full(thousands: int) -> str:
    """"XX 000 000" — полная сумма в $ с пробелами-разрядами (не сокращение до M),
    используется на экранах капитана Ranked-состава по формату из ТЗ."""
    return f"{int(thousands) * 1000:,}".replace(",", " ")


def parse_salary(text: str | None) -> int | None:
    """Разбирает ввод зарплаты в тысячах $.

    Принимает форматы: "5.5", "5.5M", "$5.5M", "$5.5 M", "20", "0".
    Значение трактуется как миллионы. Возвращает тысячи $ или None при ошибке.
    """
    if text is None:
        return None

    cleaned = text.strip().upper().replace("$", "").replace("M", "").replace(",", ".").strip()
    if not cleaned:
        return None

    try:
        millions = float(cleaned)
    except ValueError:
        return None

    if millions < 0 or millions > 200:
        return None

    # округляем до 0.1M
    thousands = int(round(millions * 10)) * 100
    return thousands


def format_salary(thousands: int) -> str:
    return f"${thousands / 1000:.1f}M"
