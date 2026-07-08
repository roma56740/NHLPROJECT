from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.salary import league_cap
from app.services.chemistry import ChemistryBonus, ChemistryCard, calculate_chemistry


@dataclass(frozen=True)
class LineupSlotInfo:
    code: str
    title: str
    short_title: str
    position: str
    icon: str


@dataclass(frozen=True)
class LineupCard:
    user_card_id: int
    card_id: int
    name: str
    player_key: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    image_path: str
    lineup_slot: str | None
    collection_code: str
    salary: int = 0


@dataclass(frozen=True)
class LineupOverview:
    slots: dict[str, LineupCard | None]
    filled_count: int
    total_slots: int
    average_overall: int | None
    chemistry_bonus: int
    final_overall: int | None
    chemistry_bonuses: list[ChemistryBonus]
    is_complete: bool
    salary_total: int = 0
    salary_cap: int = 0


@dataclass(frozen=True)
class LineupCardsPage:
    cards: list[LineupCard]
    slot_code: str
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class LineupActionResult:
    success: bool
    message: str


LINEUP_SLOTS: dict[str, LineupSlotInfo] = {
    "G": LineupSlotInfo(code="G", title="Вратарь", short_title="G", position="G", icon="🥅"),
    "D1": LineupSlotInfo(code="D1", title="Защитник 1", short_title="D1", position="D", icon="🛡"),
    "D2": LineupSlotInfo(code="D2", title="Защитник 2", short_title="D2", position="D", icon="🛡"),
    "F1": LineupSlotInfo(code="F1", title="Нападающий 1", short_title="F1", position="F", icon="⚡"),
    "F2": LineupSlotInfo(code="F2", title="Нападающий 2", short_title="F2", position="F", icon="⚡"),
    "F3": LineupSlotInfo(code="F3", title="Нападающий 3", short_title="F3", position="F", icon="⚡"),
}

LINEUP_SLOT_ORDER = ["G", "D1", "D2", "F1", "F2", "F3"]


POSITION_NAMES = {
    "G": "вратарь",
    "D": "защитник",
    "F": "нападающий",
}


def is_valid_slot(slot_code: str | None) -> bool:
    return bool(slot_code and slot_code in LINEUP_SLOTS)


def get_slot_info(slot_code: str) -> LineupSlotInfo:
    return LINEUP_SLOTS[slot_code]


def row_to_lineup_card(row) -> LineupCard:
    return LineupCard(
        user_card_id=row["user_card_id"],
        card_id=row["card_id"],
        name=row["name"],
        player_key=row["player_key"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        country=row["country"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
        image_path=row["image_path"],
        lineup_slot=row["lineup_slot"],
        collection_code=row["collection_code"],
        salary=int(row["salary"] or 0) if "salary" in row.keys() else 0,
    )


async def get_user_league(user_id: int) -> str:
    with get_connection() as connection:
        row = connection.execute("SELECT league FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["league"] if row and row["league"] else "NCAA"


async def get_lineup_overview(user_id: int) -> LineupOverview:
    slots: dict[str, LineupCard | None] = {slot_code: None for slot_code in LINEUP_SLOT_ORDER}

    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            SELECT
                user_cards.id AS user_card_id,
                user_cards.card_id,
                user_cards.lineup_slot,
                cards.name,
                cards.player_key,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                cards.salary,
                collections.name AS collection_name,
                collections.code AS collection_code
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE user_cards.user_id = ?
              AND user_cards.is_in_lineup = 1
              AND user_cards.lineup_slot IN ({','.join(['?'] * len(LINEUP_SLOT_ORDER))})
            ORDER BY user_cards.updated_at DESC, user_cards.id DESC
            """,
            [user_id, *LINEUP_SLOT_ORDER],
        )
        rows = cursor.fetchall()

    for row in rows:
        slot_code = row["lineup_slot"]
        if slot_code in slots and slots[slot_code] is None:
            slots[slot_code] = row_to_lineup_card(row)

    cards = [card for card in slots.values() if card is not None]
    filled_count = len(cards)
    salary_total = sum(card.salary for card in cards)
    average_overall = round(sum(card.overall for card in cards) / filled_count) if filled_count else None
    chemistry_result = await calculate_chemistry([
        ChemistryCard(
            country=card.country,
            team=card.team,
            collection_name=card.collection_name,
            collection_code=card.collection_code,
        )
        for card in cards
    ])
    final_overall = None

    if average_overall is not None:
        final_overall = min(99, average_overall + chemistry_result.total_bonus)

    return LineupOverview(
        slots=slots,
        filled_count=filled_count,
        total_slots=len(LINEUP_SLOT_ORDER),
        average_overall=average_overall,
        chemistry_bonus=chemistry_result.total_bonus,
        final_overall=final_overall,
        chemistry_bonuses=chemistry_result.bonuses,
        is_complete=filled_count == len(LINEUP_SLOT_ORDER),
        salary_total=salary_total,
        salary_cap=league_cap(await get_user_league(user_id)),
    )


async def get_lineup_cards_page(
    user_id: int,
    slot_code: str,
    page: int = 1,
    per_page: int = 5,
) -> LineupCardsPage:
    if not is_valid_slot(slot_code):
        return LineupCardsPage(cards=[], slot_code="G", page=1, pages_count=1, total_count=0)

    slot = get_slot_info(slot_code)

    with get_connection() as connection:
        forbidden_cursor = connection.execute(
            """
            SELECT DISTINCT cards.player_key
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ?
              AND user_cards.is_in_lineup = 1
              AND user_cards.lineup_slot != ?
            """,
            (user_id, slot_code),
        )
        forbidden_keys = [row["player_key"] for row in forbidden_cursor.fetchall()]

        forbidden_sql = ""
        params: list[object] = [user_id, slot.position, slot_code]

        if forbidden_keys:
            forbidden_sql = f"AND cards.player_key NOT IN ({','.join(['?'] * len(forbidden_keys))})"
            params.extend(forbidden_keys)

        count_cursor = connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ?
              AND cards.active = 1
              AND cards.position = ?
              AND (user_cards.is_in_lineup = 0 OR user_cards.lineup_slot = ?)
              {forbidden_sql}
            """,
            params,
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                user_cards.id AS user_card_id,
                user_cards.card_id,
                user_cards.lineup_slot,
                cards.name,
                cards.player_key,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                collections.name AS collection_name,
                collections.code AS collection_code
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE user_cards.user_id = ?
              AND cards.active = 1
              AND cards.position = ?
              AND (user_cards.is_in_lineup = 0 OR user_cards.lineup_slot = ?)
              {forbidden_sql}
            ORDER BY cards.overall DESC, cards.name ASC, user_cards.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    return LineupCardsPage(
        cards=[row_to_lineup_card(row) for row in rows],
        slot_code=slot_code,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )


async def set_lineup_card(user_id: int, slot_code: str, user_card_id: int) -> LineupActionResult:
    if not is_valid_slot(slot_code):
        return LineupActionResult(False, "Слот состава не найден.")

    slot = get_slot_info(slot_code)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                user_cards.id,
                user_cards.is_in_lineup,
                user_cards.lineup_slot,
                cards.name,
                cards.player_key,
                cards.position,
                cards.active
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.id = ?
              AND user_cards.user_id = ?
            """,
            (user_card_id, user_id),
        )
        card = cursor.fetchone()

        if card is None:
            return LineupActionResult(False, "Карточка не найдена в коллекции.")

        if not bool(card["active"]):
            return LineupActionResult(False, "Карточка сейчас недоступна для состава.")

        if card["position"] != slot.position:
            position_name = POSITION_NAMES.get(slot.position, slot.position)
            return LineupActionResult(False, f"В этот слот нужен {position_name}.")

        if bool(card["is_in_lineup"]) and card["lineup_slot"] != slot_code:
            return LineupActionResult(False, "Эта карточка уже стоит в другом слоте.")

        duplicate_cursor = connection.execute(
            """
            SELECT 1
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ?
              AND user_cards.is_in_lineup = 1
              AND user_cards.lineup_slot != ?
              AND cards.player_key = ?
            LIMIT 1
            """,
            (user_id, slot_code, card["player_key"]),
        )

        if duplicate_cursor.fetchone() is not None:
            return LineupActionResult(False, "Один и тот же игрок не может быть в составе дважды.")

        connection.execute(
            """
            UPDATE user_cards
            SET is_in_lineup = 0,
                lineup_slot = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
              AND lineup_slot = ?
            """,
            (user_id, slot_code),
        )
        connection.execute(
            """
            UPDATE user_cards
            SET is_in_lineup = 1,
                lineup_slot = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND user_id = ?
            """,
            (slot_code, user_card_id, user_id),
        )
        connection.commit()

    return LineupActionResult(True, "Карточка добавлена в состав.")


async def remove_lineup_slot(user_id: int, slot_code: str) -> LineupActionResult:
    if not is_valid_slot(slot_code):
        return LineupActionResult(False, "Слот состава не найден.")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_cards
            SET is_in_lineup = 0,
                lineup_slot = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
              AND lineup_slot = ?
            """,
            (user_id, slot_code),
        )
        connection.commit()

    return LineupActionResult(True, "Слот освобождён.")


async def clear_lineup(user_id: int) -> LineupActionResult:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_cards
            SET is_in_lineup = 0,
                lineup_slot = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
              AND is_in_lineup = 1
            """,
            (user_id,),
        )
        connection.commit()

    return LineupActionResult(True, "Состав очищен.")


async def auto_fill_best_lineup(user_id: int) -> LineupActionResult:
    selected: dict[str, int] = {}
    used_player_keys: set[str] = set()
    missing_positions: list[str] = []

    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                user_cards.id AS user_card_id,
                cards.player_key,
                cards.position,
                cards.overall,
                cards.name
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ?
              AND cards.active = 1
            ORDER BY cards.overall DESC, cards.name ASC, user_cards.id DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()

        for slot_code in LINEUP_SLOT_ORDER:
            slot = get_slot_info(slot_code)
            chosen_row = None

            for row in rows:
                player_key = str(row["player_key"] or "")

                if row["position"] != slot.position:
                    continue

                if player_key and player_key in used_player_keys:
                    continue

                chosen_row = row
                break

            if chosen_row is None:
                missing_positions.append(slot.short_title)
                continue

            selected[slot_code] = int(chosen_row["user_card_id"])
            player_key = str(chosen_row["player_key"] or "")

            if player_key:
                used_player_keys.add(player_key)

        if not selected:
            return LineupActionResult(
                False,
                "В коллекции пока нет подходящих карточек для состава.",
            )

        connection.execute(
            """
            UPDATE user_cards
            SET is_in_lineup = 0,
                lineup_slot = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
              AND is_in_lineup = 1
            """,
            (user_id,),
        )

        for slot_code, user_card_id in selected.items():
            connection.execute(
                """
                UPDATE user_cards
                SET is_in_lineup = 1,
                    lineup_slot = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND user_id = ?
                """,
                (slot_code, user_card_id, user_id),
            )

        connection.commit()

    if missing_positions:
        missing_text = ", ".join(missing_positions)
        return LineupActionResult(
            True,
            f"Лучшие доступные карточки поставлены. Пока не хватает позиций: {missing_text}.",
        )

    return LineupActionResult(True, "Лучший состав собран автоматически.")

