from html import escape

from app.services.admin_salaries import SalaryCardsPage, SalaryCollectionItem, SalarySummary
from app.services.salary import format_salary


def safe(value: object | None) -> str:
    return escape(str(value or "не указано"), quote=False)


ADMIN_SALARIES_BUTTON_TEXT = "💵 Зарплаты"
ADMIN_SALARIES_MAIN_TEXT = """
<b>💵 Управление зарплатами</b>

Здесь можно быстро найти карточки без зарплаты, массово заполнить зарплаты и обновить зарплату всей коллекции.
""".strip()

ADMIN_SALARY_VALUE_TEXT = """
<b>💵 Новая зарплата</b>

Введи зарплату в миллионах.

Пример: <b>5.5</b>
""".strip()

ADMIN_OVR_RANGE_TEXT = """
<b>⭐ Зарплата по OVR</b>

Отправь диапазон OVR и зарплату одним сообщением.

Пример: <b>90-93 5.5</b>
""".strip()


def build_salary_summary_text(summary: SalarySummary) -> str:
    return f"""
<b>💵 Управление зарплатами</b>

Всего карточек: <b>{summary.total_cards}</b>
Без зарплаты: <b>{summary.zero_salary_cards}</b>
Активных без зарплаты: <b>{summary.active_zero_salary_cards}</b>
Средняя зарплата: <b>{format_salary(summary.avg_salary)}</b>
Максимальная зарплата: <b>{format_salary(summary.max_salary)}</b>
Коллекций: <b>{summary.collections_count}</b>
Команд: <b>{summary.teams_count}</b>

Выбери действие ниже.
""".strip()


def build_salary_cards_page_text(page: SalaryCardsPage) -> str:
    title = "Карточки без зарплаты" if page.mode == "zero" else "Самые дорогие карточки"
    lines = [f"<b>💵 {title}</b>", "", f"Страница: <b>{page.page}/{page.pages_count}</b>", f"Всего: <b>{page.total_count}</b>", ""]
    if not page.cards:
        lines.append("Список пуст.")
    else:
        for card in page.cards:
            status = "✅" if card.active else "⏸"
            lines.append(f"{status} ID {card.id} · <b>{safe(card.name)}</b> · {card.overall} OVR · {format_salary(card.salary)} · {safe(card.collection_name)}")
    return "\n".join(lines)


def build_salary_collections_text(collections: list[SalaryCollectionItem]) -> str:
    lines = ["<b>🗂 Зарплаты по коллекциям</b>", ""]
    if not collections:
        lines.append("Коллекций пока нет.")
    else:
        for col in collections:
            lines.append(f"<b>{safe(col.name)}</b> — {col.cards_count} карт · без зарплаты: {col.zero_salary_count} · средняя: {format_salary(col.avg_salary)}")
    lines.append("")
    lines.append("Выбери коллекцию ниже, чтобы поставить зарплату всем картам коллекции.")
    return "\n".join(lines)
