from app.services.salary import format_salary
from html import escape

from app.services.user_cards import PlayerCardProfile, PlayerCardsPage


USER_CARDS_MAIN_TEXT = """
<b>🃏 Моя коллекция</b>

Здесь собраны карточки игроков.
Можно открыть список, найти нужную карточку и посмотреть подробности.
""".strip()

USER_CARDS_SEARCH_TEXT = """
<b>🔎 Поиск карточки</b>

Отправь имя игрока, команду, страну, коллекцию, редкость, позицию или ID карточки.
""".strip()

USER_CARDS_FILTERS_TEXT = """
<b>🎛 Фильтры коллекции</b>

Выбери позицию или редкость.
После выбора открой список карточек.
""".strip()

USER_CARDS_EMPTY_TEXT = """
<b>🃏 Коллекция пока пустая</b>

Карточки появятся после открытия паков, наград или выдачи от администрации лиги.
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


def build_filter_line(page: PlayerCardsPage) -> str:
    parts: list[str] = []

    if page.search:
        parts.append(f"поиск: <b>{safe(page.search)}</b>")

    if page.position:
        parts.append(f"позиция: <b>{safe(page.position)}</b>")

    if page.rarity:
        parts.append(f"редкость: <b>{safe(page.rarity)}</b>")

    if not parts:
        return ""

    return "\n🎛 " + ", ".join(parts)


def build_player_cards_page_text(page: PlayerCardsPage) -> str:
    if page.total_count == 0:
        return USER_CARDS_EMPTY_TEXT

    filter_line = build_filter_line(page)
    sort_line = "слабые → сильные" if page.sort_order == "ovr_asc" else "сильные → слабые"

    return f"""
<b>🃏 Моя коллекция</b>

Карточек найдено: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{filter_line}
Сортировка: <b>{sort_line}</b>

Выбери карточку из списка ниже.
""".strip()


def build_player_card_profile_text(card: PlayerCardProfile) -> str:
    lineup_status = "в составе" if card.is_in_lineup else "свободна"
    trade_status = "закрыта для обмена" if card.trade_locked else "доступна"

    lock_line = ""
    if card.trade_locked and card.lock_reason:
        lock_line = f"\nПричина: <b>{safe(card.lock_reason)}</b>"

    return f"""
<b>🃏 Карточка игрока</b>

🏒 Игрок: <b>{safe(card.name)}</b>
⭐ OVR: <b>{card.overall}</b>
📍 Позиция: <b>{safe(card.position)}</b>
🛡 Команда: <b>{safe(card.team)}</b>
🌍 Страна: <b>{safe(card.country)}</b>
🗂 Коллекция: <b>{safe(card.collection_name)}</b>
✨ Редкость: <b>{safe(card.rarity)}</b>
💵 Зарплата: <b>{format_salary(card.salary)}</b>

<b>Статус</b>
Состав: <b>{lineup_status}</b>
Обмен: <b>{trade_status}</b>{lock_line}

ID экземпляра: <b>{card.id}</b>
""".strip()
