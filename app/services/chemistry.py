from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Sequence

from app.database.db import get_connection


RULE_TYPES = {
    "country": "🌍 Страна",
    "team": "🏒 Команда",
    "collection": "🗂 Коллекция",
}

RULE_TYPE_ICONS = {
    "country": "🌍",
    "team": "🏒",
    "collection": "🗂",
}


@dataclass(frozen=True)
class ChemistryCard:
    country: str
    team: str
    collection_name: str
    collection_code: str | None = None


@dataclass(frozen=True)
class ChemistryRule:
    id: int
    rule_type: str
    value: str
    required_cards: int
    bonus_ovr: int
    active: bool
    created_at: str


@dataclass(frozen=True)
class ChemistryBonus:
    rule_id: int
    rule_type: str
    value: str
    required_cards: int
    matched_cards: int
    bonus_ovr: int
    icon: str


@dataclass(frozen=True)
class ChemistryResult:
    bonuses: list[ChemistryBonus]
    total_bonus: int


@dataclass(frozen=True)
class ChemistryRulesPage:
    rules: list[ChemistryRule]
    page: int
    pages_count: int
    total_count: int
    query: str | None = None


@dataclass(frozen=True)
class ChemistryActionResult:
    success: bool
    message: str
    rule_id: int | None = None


def normalize_value(value: object | None) -> str:
    return str(value or "").strip().casefold()


def row_to_rule(row) -> ChemistryRule:
    return ChemistryRule(
        id=int(row["id"]),
        rule_type=str(row["rule_type"]),
        value=str(row["value"]),
        required_cards=int(row["required_cards"]),
        bonus_ovr=int(row["bonus_ovr"]),
        active=bool(row["active"]),
        created_at=str(row["created_at"]),
    )


def get_rule_type_title(rule_type: str) -> str:
    return RULE_TYPES.get(rule_type, rule_type)


def get_rule_icon(rule_type: str) -> str:
    return RULE_TYPE_ICONS.get(rule_type, "✨")


async def get_active_chemistry_rules() -> list[ChemistryRule]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT id, rule_type, value, required_cards, bonus_ovr, active, created_at
            FROM chemistry_rules
            WHERE active = 1
            ORDER BY bonus_ovr DESC, required_cards DESC, value ASC
            """
        )
        rows = cursor.fetchall()

    return [row_to_rule(row) for row in rows]


async def calculate_chemistry(cards: Sequence[ChemistryCard]) -> ChemistryResult:
    if not cards:
        return ChemistryResult(bonuses=[], total_bonus=0)

    rules = await get_active_chemistry_rules()

    country_counts: dict[str, int] = {}
    team_counts: dict[str, int] = {}
    collection_counts: dict[str, int] = {}

    for card in cards:
        country_counts[normalize_value(card.country)] = country_counts.get(normalize_value(card.country), 0) + 1
        team_counts[normalize_value(card.team)] = team_counts.get(normalize_value(card.team), 0) + 1
        collection_counts[normalize_value(card.collection_name)] = collection_counts.get(normalize_value(card.collection_name), 0) + 1

        if card.collection_code:
            collection_counts[normalize_value(card.collection_code)] = collection_counts.get(normalize_value(card.collection_code), 0) + 1

    bonuses: list[ChemistryBonus] = []

    for rule in rules:
        normalized_rule_value = normalize_value(rule.value)

        if rule.rule_type == "country":
            matched_cards = country_counts.get(normalized_rule_value, 0)
        elif rule.rule_type == "team":
            matched_cards = team_counts.get(normalized_rule_value, 0)
        elif rule.rule_type == "collection":
            matched_cards = collection_counts.get(normalized_rule_value, 0)
        else:
            matched_cards = 0

        if matched_cards >= rule.required_cards:
            bonuses.append(
                ChemistryBonus(
                    rule_id=rule.id,
                    rule_type=rule.rule_type,
                    value=rule.value,
                    required_cards=rule.required_cards,
                    matched_cards=matched_cards,
                    bonus_ovr=rule.bonus_ovr,
                    icon=get_rule_icon(rule.rule_type),
                )
            )

    total_bonus = sum(bonus.bonus_ovr for bonus in bonuses)
    return ChemistryResult(bonuses=bonuses, total_bonus=total_bonus)


async def get_chemistry_rules_page(page: int = 1, per_page: int = 5, query: str | None = None) -> ChemistryRulesPage:
    where_sql = ""
    params: list[object] = []

    if query:
        where_sql = "WHERE value LIKE ? OR rule_type LIKE ?"
        search = f"%{query.strip()}%"
        params.extend([search, search])

    with get_connection() as connection:
        count_cursor = connection.execute(
            f"SELECT COUNT(*) AS total_count FROM chemistry_rules {where_sql}",
            params,
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT id, rule_type, value, required_cards, bonus_ovr, active, created_at
            FROM chemistry_rules
            {where_sql}
            ORDER BY active DESC, bonus_ovr DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    return ChemistryRulesPage(
        rules=[row_to_rule(row) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        query=query,
    )


async def get_chemistry_rule(rule_id: int) -> ChemistryRule | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT id, rule_type, value, required_cards, bonus_ovr, active, created_at
            FROM chemistry_rules
            WHERE id = ?
            """,
            (rule_id,),
        )
        row = cursor.fetchone()

    return row_to_rule(row) if row is not None else None


async def create_chemistry_rule(
    *,
    rule_type: str,
    value: str,
    required_cards: int,
    bonus_ovr: int,
) -> ChemistryActionResult:
    value = value.strip()

    if rule_type not in RULE_TYPES:
        return ChemistryActionResult(False, "Выбери тип бонуса.")

    if len(value) < 2 or len(value) > 64:
        return ChemistryActionResult(False, "Название должно быть от 2 до 64 символов.")

    if required_cards < 2 or required_cards > 6:
        return ChemistryActionResult(False, "Количество карточек должно быть от 2 до 6.")

    if bonus_ovr < 1 or bonus_ovr > 5:
        return ChemistryActionResult(False, "Бонус должен быть от +1 до +5 OVR.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO chemistry_rules (rule_type, value, required_cards, bonus_ovr, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (rule_type, value, required_cards, bonus_ovr),
        )
        connection.commit()
        rule_id = int(cursor.lastrowid)

    return ChemistryActionResult(True, "Бонус химии создан.", rule_id=rule_id)


async def update_chemistry_rule_field(rule_id: int, field: str, value: object) -> ChemistryActionResult:
    allowed_fields = {"rule_type", "value", "required_cards", "bonus_ovr"}

    if field not in allowed_fields:
        return ChemistryActionResult(False, "Поле не найдено.")

    rule = await get_chemistry_rule(rule_id)

    if rule is None:
        return ChemistryActionResult(False, "Бонус химии не найден.")

    if field == "rule_type" and str(value) not in RULE_TYPES:
        return ChemistryActionResult(False, "Выбери тип бонуса.")

    if field == "value":
        value = str(value).strip()
        if len(value) < 2 or len(value) > 64:
            return ChemistryActionResult(False, "Название должно быть от 2 до 64 символов.")

    if field == "required_cards":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return ChemistryActionResult(False, "Введи число от 2 до 6.")
        if int(value) < 2 or int(value) > 6:
            return ChemistryActionResult(False, "Количество карточек должно быть от 2 до 6.")

    if field == "bonus_ovr":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return ChemistryActionResult(False, "Введи число от 1 до 5.")
        if int(value) < 1 or int(value) > 5:
            return ChemistryActionResult(False, "Бонус должен быть от +1 до +5 OVR.")

    with get_connection() as connection:
        connection.execute(
            f"""
            UPDATE chemistry_rules
            SET {field} = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (value, rule_id),
        )
        connection.commit()

    return ChemistryActionResult(True, "Бонус химии обновлён.", rule_id=rule_id)


async def toggle_chemistry_rule(rule_id: int) -> ChemistryActionResult:
    rule = await get_chemistry_rule(rule_id)

    if rule is None:
        return ChemistryActionResult(False, "Бонус химии не найден.")

    new_active = 0 if rule.active else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE chemistry_rules
            SET active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_active, rule_id),
        )
        connection.commit()

    message = "Бонус отключён." if rule.active else "Бонус включён."
    return ChemistryActionResult(True, message, rule_id=rule_id)


async def delete_chemistry_rule(rule_id: int) -> ChemistryActionResult:
    rule = await get_chemistry_rule(rule_id)

    if rule is None:
        return ChemistryActionResult(False, "Бонус химии не найден.")

    with get_connection() as connection:
        connection.execute("DELETE FROM chemistry_rules WHERE id = ?", (rule_id,))
        connection.commit()

    return ChemistryActionResult(True, "Бонус химии удалён.")
