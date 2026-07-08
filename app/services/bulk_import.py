"""Массовое добавление карт по шаблону (#15).

Шаблон одной карты (поля в любом порядке, карты разделяются пустой строкой):
    Имя: Sidney Crosby
    Позиция: F
    OVR: 87
    Команда: Pittsburgh Penguins
    Страна: Canada
    Коллекция: Base Collection
    Редкость: Epic
    Зарплата: $5.5M
"""

from dataclasses import dataclass

from app.services.admin_cards import CardDraft, create_card
from app.services.salary import parse_salary

VALID_POSITIONS = {"G", "D", "F"}
VALID_RARITIES = {"Common", "Rare", "Epic", "Legendary", "Event", "Icon"}

# синонимы полей (рус/англ)
FIELD_ALIASES = {
    "имя": "name", "name": "name",
    "позиция": "position", "position": "position", "поз": "position",
    "ovr": "overall", "овр": "overall", "рейтинг": "overall",
    "команда": "team", "team": "team",
    "страна": "country", "country": "country",
    "коллекция": "collection", "collection": "collection",
    "редкость": "rarity", "rarity": "rarity",
    "зарплата": "salary", "salary": "salary",
}

RARITY_ALIASES = {r.lower(): r for r in VALID_RARITIES}


@dataclass
class ParsedCard:
    line_no: int
    raw: str
    fields: dict
    error: str | None


def parse_bulk_cards(text: str) -> list[ParsedCard]:
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start_line = 1

    for line_index, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "":
            if current:
                blocks.append((start_line, current))
                current = []
            continue
        if not current:
            start_line = line_index
        current.append(line)
    if current:
        blocks.append((start_line, current))

    parsed: list[ParsedCard] = []
    for line_no, block in blocks:
        fields: dict = {}
        error = None
        for row in block:
            if ":" not in row:
                continue
            key, _, value = row.partition(":")
            key_norm = key.strip().lower()
            field = FIELD_ALIASES.get(key_norm)
            if field is None:
                continue
            fields[field] = value.strip()

        # валидация
        required = ["name", "position", "overall", "team", "country", "collection", "rarity"]
        missing = [f for f in required if not fields.get(f)]
        if missing:
            error = f"нет полей: {', '.join(missing)}"
        else:
            pos = fields["position"].upper()
            if pos not in VALID_POSITIONS:
                error = f"позиция должна быть G/D/F (указано: {fields['position']})"
            else:
                fields["position"] = pos

            if error is None:
                try:
                    ovr = int(fields["overall"])
                    if not (1 <= ovr <= 99):
                        raise ValueError
                    fields["overall"] = ovr
                except ValueError:
                    error = f"OVR должен быть числом 1–99 (указано: {fields['overall']})"

            if error is None:
                rarity = RARITY_ALIASES.get(fields["rarity"].lower())
                if rarity is None:
                    error = f"редкость должна быть одной из: {', '.join(sorted(VALID_RARITIES))}"
                else:
                    fields["rarity"] = rarity

            if error is None:
                salary_raw = fields.get("salary", "0") or "0"
                salary = parse_salary(salary_raw)
                if salary is None:
                    error = f"зарплата в млн, напр. 5.5 (указано: {salary_raw})"
                else:
                    fields["salary"] = salary

        parsed.append(ParsedCard(line_no=line_no, raw="\n".join(block), fields=fields, error=error))

    return parsed


async def create_bulk_cards(parsed: list[ParsedCard]) -> tuple[int, list[str]]:
    """Создаёт валидные карты. Возвращает (сколько создано, список ошибок)."""
    created = 0
    errors: list[str] = []

    for item in parsed:
        if item.error is not None:
            name = item.fields.get("name", f"строка {item.line_no}")
            errors.append(f"❌ {name}: {item.error}")
            continue
        try:
            draft = CardDraft(
                image_path="logo.png",  # плейсхолдер; админ заменит фото позже
                name=str(item.fields["name"]),
                position=str(item.fields["position"]),
                overall=int(item.fields["overall"]),
                team=str(item.fields["team"]),
                country=str(item.fields["country"]),
                collection_name=str(item.fields["collection"]),
                rarity=str(item.fields["rarity"]),
                salary=int(item.fields.get("salary", 0)),
            )
            await create_card(draft)
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"❌ {item.fields.get('name', '?')}: ошибка сохранения ({exc})")

    return created, errors
