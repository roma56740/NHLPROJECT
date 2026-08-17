from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.card_distribution_policy import is_admin_only_card


@dataclass(frozen=True)
class StarterKitSlotInfo:
    code: str
    title: str
    position: str
    icon: str


@dataclass(frozen=True)
class StarterKitCard:
    id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    active: bool
    slot_code: str | None = None


@dataclass(frozen=True)
class StarterKitOverview:
    slots: dict[str, StarterKitCard | None]
    filled_count: int
    total_count: int
    is_complete: bool


@dataclass(frozen=True)
class StarterKitCardsPage:
    slot_code: str
    cards: list[StarterKitCard]
    page: int
    pages_count: int
    total_count: int


STARTER_KIT_SLOTS: dict[str, StarterKitSlotInfo] = {
    "G": StarterKitSlotInfo(code="G", title="Вратарь", position="G", icon="🥅"),
    "D1": StarterKitSlotInfo(code="D1", title="Защитник 1", position="D", icon="🛡"),
    "D2": StarterKitSlotInfo(code="D2", title="Защитник 2", position="D", icon="🛡"),
    "F1": StarterKitSlotInfo(code="F1", title="Нападающий 1", position="F", icon="⚡"),
    "F2": StarterKitSlotInfo(code="F2", title="Нападающий 2", position="F", icon="⚡"),
    "F3": StarterKitSlotInfo(code="F3", title="Нападающий 3", position="F", icon="⚡"),
}

STARTER_KIT_SLOT_ORDER = ["G", "D1", "D2", "F1", "F2", "F3"]
POSITION_NAMES = {
    "G": "вратари",
    "D": "защитники",
    "F": "нападающие",
}


def is_valid_starter_slot(slot_code: str | None) -> bool:
    return bool(slot_code and slot_code in STARTER_KIT_SLOTS)


def row_to_starter_card(row, slot_code: str | None = None) -> StarterKitCard:
    return StarterKitCard(
        id=int(row["id"]),
        name=row["name"],
        position=row["position"],
        overall=int(row["overall"]),
        team=row["team"],
        country=row["country"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
        active=bool(row["active"]),
        slot_code=slot_code,
    )


async def get_starter_kit_overview() -> StarterKitOverview:
    slots: dict[str, StarterKitCard | None] = {slot_code: None for slot_code in STARTER_KIT_SLOT_ORDER}

    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                starter_kit_cards.slot_code,
                cards.id,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.active,
                COALESCE(collections.name, 'Без коллекции') AS collection_name
            FROM starter_kit_cards
            JOIN cards ON cards.id = starter_kit_cards.card_id
            LEFT JOIN collections ON collections.id = cards.collection_id
            ORDER BY starter_kit_cards.id ASC
            """
        )
        rows = cursor.fetchall()

    for row in rows:
        slot_code = row["slot_code"]
        if slot_code in slots:
            slots[slot_code] = row_to_starter_card(row, slot_code=slot_code)

    filled_count = len([card for card in slots.values() if card is not None])

    return StarterKitOverview(
        slots=slots,
        filled_count=filled_count,
        total_count=len(STARTER_KIT_SLOT_ORDER),
        is_complete=filled_count == len(STARTER_KIT_SLOT_ORDER),
    )


async def get_starter_kit_cards_page(
    slot_code: str,
    page: int = 1,
    per_page: int = 5,
) -> StarterKitCardsPage:
    if not is_valid_starter_slot(slot_code):
        return StarterKitCardsPage(slot_code="G", cards=[], page=1, pages_count=1, total_count=0)

    slot = STARTER_KIT_SLOTS[slot_code]

    with get_connection() as connection:
        count_cursor = connection.execute(
            """
            SELECT COUNT(*) AS total_count
            FROM cards
            LEFT JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1
              AND cards.position = ?
              AND LOWER(TRIM(COALESCE(collections.name, ''))) != 'leaders'
              AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders'
            """,
            (slot.position,),
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                cards.id,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.active,
                COALESCE(collections.name, 'Без коллекции') AS collection_name
            FROM cards
            LEFT JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1
              AND cards.position = ?
              AND LOWER(TRIM(COALESCE(collections.name, ''))) != 'leaders'
              AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders'
            ORDER BY cards.overall ASC, cards.name ASC, cards.id ASC
            LIMIT ? OFFSET ?
            """,
            (slot.position, per_page, offset),
        )
        rows = cursor.fetchall()

    return StarterKitCardsPage(
        slot_code=slot_code,
        cards=[row_to_starter_card(row) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )


async def set_starter_kit_card(slot_code: str, card_id: int) -> bool:
    if not is_valid_starter_slot(slot_code):
        return False

    slot = STARTER_KIT_SLOTS[slot_code]

    with get_connection() as connection:
        card_row = connection.execute(
            """
            SELECT id, position, active
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()

        if card_row is None:
            return False

        if not bool(card_row["active"]) or card_row["position"] != slot.position:
            return False
        if is_admin_only_card(connection, card_id):
            return False

        connection.execute(
            """
            INSERT INTO starter_kit_cards (slot_code, card_id)
            VALUES (?, ?)
            ON CONFLICT(slot_code) DO UPDATE SET
                card_id = excluded.card_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (slot_code, card_id),
        )
        connection.commit()

    return True


async def clear_starter_kit_slot(slot_code: str) -> None:
    if not is_valid_starter_slot(slot_code):
        return

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM starter_kit_cards WHERE slot_code = ?",
            (slot_code,),
        )
        connection.commit()


async def clear_starter_kit() -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM starter_kit_cards")
        connection.commit()


async def give_starter_kit_to_new_user(user_id: int) -> int:
    """Give starter kit cards and place them into lineup. Returns number of issued cards."""

    with get_connection() as connection:
        cards_count = connection.execute(
            "SELECT COUNT(*) AS total_count FROM user_cards WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total_count"]

        if int(cards_count) > 0:
            return 0

        cursor = connection.execute(
            f"""
            SELECT
                starter_kit_cards.slot_code,
                cards.id AS card_id,
                cards.player_key,
                cards.position,
                cards.active
            FROM starter_kit_cards
            JOIN cards ON cards.id = starter_kit_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1
              AND LOWER(TRIM(COALESCE(collections.name, ''))) != 'leaders'
              AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders'
              AND starter_kit_cards.slot_code IN ({','.join(['?'] * len(STARTER_KIT_SLOT_ORDER))})
            ORDER BY CASE starter_kit_cards.slot_code
                WHEN 'G' THEN 1
                WHEN 'D1' THEN 2
                WHEN 'D2' THEN 3
                WHEN 'F1' THEN 4
                WHEN 'F2' THEN 5
                WHEN 'F3' THEN 6
                ELSE 99
            END
            """,
            STARTER_KIT_SLOT_ORDER,
        )
        rows = cursor.fetchall()

        if not rows:
            return 0

        used_player_keys: set[str] = set()
        issued_count = 0

        for row in rows:
            slot_code = row["slot_code"]
            slot = STARTER_KIT_SLOTS.get(slot_code)

            if slot is None:
                continue

            if row["position"] != slot.position:
                continue

            player_key = str(row["player_key"])

            if player_key in used_player_keys:
                continue

            if is_admin_only_card(connection, int(row["card_id"])):
                continue

            used_player_keys.add(player_key)
            connection.execute(
                """
                INSERT INTO user_cards (
                    user_id,
                    card_id,
                    is_in_lineup,
                    lineup_slot,
                    obtained_from
                )
                VALUES (?, ?, 1, ?, 'starter_kit')
                """,
                (user_id, int(row["card_id"]), slot_code),
            )
            issued_count += 1

        connection.commit()

    return issued_count
