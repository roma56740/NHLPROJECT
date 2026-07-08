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

DEFAULT_CAP = 34000


def league_cap(league: str | None) -> int:
    return LEAGUE_SALARY_CAPS.get((league or "").upper(), DEFAULT_CAP)


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
