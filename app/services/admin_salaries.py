from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.salary import parse_salary


@dataclass(frozen=True)
class SalarySummary:
    total_cards: int
    zero_salary_cards: int
    active_zero_salary_cards: int
    avg_salary: int
    max_salary: int
    collections_count: int
    teams_count: int


@dataclass(frozen=True)
class SalaryCardItem:
    id: int
    name: str
    overall: int
    team: str
    collection_name: str
    salary: int
    active: bool


@dataclass(frozen=True)
class SalaryCardsPage:
    cards: list[SalaryCardItem]
    page: int
    pages_count: int
    total_count: int
    mode: str


@dataclass(frozen=True)
class SalaryCollectionItem:
    id: int
    name: str
    cards_count: int
    zero_salary_count: int
    avg_salary: int


async def get_salary_summary() -> SalarySummary:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_cards,
                SUM(CASE WHEN salary = 0 THEN 1 ELSE 0 END) AS zero_salary_cards,
                SUM(CASE WHEN salary = 0 AND active = 1 THEN 1 ELSE 0 END) AS active_zero_salary_cards,
                COALESCE(AVG(NULLIF(salary, 0)), 0) AS avg_salary,
                COALESCE(MAX(salary), 0) AS max_salary,
                COUNT(DISTINCT collection_id) AS collections_count,
                COUNT(DISTINCT team) AS teams_count
            FROM cards
            """
        ).fetchone()
    return SalarySummary(
        total_cards=int(row["total_cards"] or 0),
        zero_salary_cards=int(row["zero_salary_cards"] or 0),
        active_zero_salary_cards=int(row["active_zero_salary_cards"] or 0),
        avg_salary=int(row["avg_salary"] or 0),
        max_salary=int(row["max_salary"] or 0),
        collections_count=int(row["collections_count"] or 0),
        teams_count=int(row["teams_count"] or 0),
    )


async def get_salary_cards_page(mode: str = "zero", page: int = 1, per_page: int = 8) -> SalaryCardsPage:
    if mode == "zero":
        where = "WHERE cards.salary = 0"
    elif mode == "highest":
        where = "WHERE cards.salary > 0"
    else:
        where = ""
    order = "cards.salary DESC, cards.overall DESC" if mode == "highest" else "cards.id DESC"
    with get_connection() as connection:
        total = int(connection.execute(f"SELECT COUNT(*) AS total FROM cards {where}").fetchone()["total"] or 0)
        pages = max(1, ceil(total / per_page))
        safe_page = min(max(page, 1), pages)
        rows = connection.execute(
            f"""
            SELECT cards.id, cards.name, cards.overall, cards.team, cards.salary, cards.active, collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,
            (per_page, (safe_page - 1) * per_page),
        ).fetchall()
    items = [SalaryCardItem(
        id=int(row["id"]), name=str(row["name"]), overall=int(row["overall"]), team=str(row["team"]),
        collection_name=str(row["collection_name"]), salary=int(row["salary"] or 0), active=bool(row["active"])
    ) for row in rows]
    return SalaryCardsPage(cards=items, page=safe_page, pages_count=pages, total_count=total, mode=mode)


async def get_salary_collections() -> list[SalaryCollectionItem]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT collections.id, collections.name,
                   COUNT(cards.id) AS cards_count,
                   SUM(CASE WHEN cards.salary = 0 THEN 1 ELSE 0 END) AS zero_salary_count,
                   COALESCE(AVG(NULLIF(cards.salary, 0)), 0) AS avg_salary
            FROM collections
            LEFT JOIN cards ON cards.collection_id = collections.id
            GROUP BY collections.id
            ORDER BY collections.name COLLATE NOCASE ASC
            """
        ).fetchall()
    return [SalaryCollectionItem(
        id=int(row["id"]), name=str(row["name"]), cards_count=int(row["cards_count"] or 0),
        zero_salary_count=int(row["zero_salary_count"] or 0), avg_salary=int(row["avg_salary"] or 0)
    ) for row in rows]


async def set_collection_salary(collection_id: int, raw_salary: str, only_zero: bool = False) -> tuple[bool, str, int]:
    salary = parse_salary(raw_salary)
    if salary is None:
        return False, "Введи зарплату в миллионах, например 5.5. Можно 0.", 0
    where = "collection_id = ?"
    params: list[object] = [salary, collection_id]
    if only_zero:
        where += " AND salary = 0"
    with get_connection() as connection:
        cursor = connection.execute(f"UPDATE cards SET salary = ?, updated_at = CURRENT_TIMESTAMP WHERE {where}", params)
        connection.commit()
    return True, "Зарплата коллекции обновлена.", int(cursor.rowcount or 0)


async def set_all_zero_salary(raw_salary: str) -> tuple[bool, str, int]:
    salary = parse_salary(raw_salary)
    if salary is None or salary <= 0:
        return False, "Для массового заполнения нулевых зарплат введи число больше 0, например 1.2 или 5.5.", 0
    with get_connection() as connection:
        cursor = connection.execute("UPDATE cards SET salary = ?, updated_at = CURRENT_TIMESTAMP WHERE salary = 0", (salary,))
        connection.commit()
    return True, "Нулевые зарплаты заполнены.", int(cursor.rowcount or 0)


async def set_salary_by_overall_range(min_ovr: int, max_ovr: int, raw_salary: str) -> tuple[bool, str, int]:
    salary = parse_salary(raw_salary)
    if salary is None:
        return False, "Зарплата не распознана. Пример: 5.5", 0
    if min_ovr < 1 or max_ovr > 99 or min_ovr > max_ovr:
        return False, "Диапазон OVR должен быть от 1 до 99. Пример: 90-93 5.5", 0
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE cards SET salary = ?, updated_at = CURRENT_TIMESTAMP WHERE overall BETWEEN ? AND ?",
            (salary, min_ovr, max_ovr),
        )
        connection.commit()
    return True, "Зарплата по диапазону OVR обновлена.", int(cursor.rowcount or 0)
