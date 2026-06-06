from dataclasses import dataclass
from math import ceil
import re

from app.database.db import get_connection


POSITIONS = {"G", "D", "F"}
RARITIES = {"Common", "Rare", "Epic", "Legendary", "Event", "Icon"}


@dataclass(frozen=True)
class CollectionItem:
    id: int
    code: str
    name: str
    description: str
    active: bool
    cards_count: int


@dataclass(frozen=True)
class CardListItem:
    id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    active: bool


@dataclass(frozen=True)
class CardProfile:
    id: int
    name: str
    player_key: str
    position: str
    overall: int
    team: str
    country: str
    collection_id: int
    collection_code: str
    collection_name: str
    rarity: str
    image_path: str
    active: bool


@dataclass(frozen=True)
class CardsPage:
    cards: list[CardListItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


@dataclass(frozen=True)
class CardDraft:
    image_path: str
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str


def clean_text(value: str) -> str:
    return " ".join(value.strip().split())


def build_collection_code(value: str) -> str:
    clean_value = clean_text(value).lower()
    clean_value = clean_value.replace("ё", "е")
    clean_value = re.sub(r"[^a-zа-я0-9]+", "-", clean_value)
    clean_value = clean_value.strip("-")
    return clean_value or "collection"


def build_player_key(name: str) -> str:
    clean_value = clean_text(name).lower()
    clean_value = clean_value.replace("ё", "е")
    return re.sub(r"\s+", " ", clean_value)


def validate_name(value: str) -> str | None:
    clean_value = clean_text(value)

    if 2 <= len(clean_value) <= 64:
        return clean_value

    return None


def validate_short_text(value: str) -> str | None:
    clean_value = clean_text(value)

    if 2 <= len(clean_value) <= 64:
        return clean_value

    return None


def validate_overall(value: str) -> int | None:
    clean_value = value.strip()

    if not clean_value.isdigit():
        return None

    overall = int(clean_value)

    if 1 <= overall <= 99:
        return overall

    return None


def validate_position(value: str) -> str | None:
    clean_value = value.strip().upper()
    return clean_value if clean_value in POSITIONS else None


def validate_rarity(value: str) -> str | None:
    clean_value = clean_text(value)
    return clean_value if clean_value in RARITIES else None


def clean_search_query(value: str | None) -> str | None:
    if value is None:
        return None

    clean_value = clean_text(value)
    return clean_value or None


def build_search_filter(search: str | None) -> tuple[str, list[object]]:
    clean_search = clean_search_query(search)

    if clean_search is None:
        return "", []

    if clean_search.isdigit():
        return """
        WHERE cards.id = ?
           OR cards.name LIKE ?
           OR cards.team LIKE ?
           OR cards.country LIKE ?
           OR collections.name LIKE ?
        """, [
            int(clean_search),
            f"%{clean_search}%",
            f"%{clean_search}%",
            f"%{clean_search}%",
            f"%{clean_search}%",
        ]

    return """
    WHERE cards.name LIKE ?
       OR cards.team LIKE ?
       OR cards.country LIKE ?
       OR cards.rarity LIKE ?
       OR cards.position LIKE ?
       OR collections.name LIKE ?
    """, [
        f"%{clean_search}%",
        f"%{clean_search}%",
        f"%{clean_search}%",
        f"%{clean_search}%",
        f"%{clean_search}%",
        f"%{clean_search}%",
    ]


async def get_cards_page(page: int = 1, per_page: int = 5, search: str | None = None) -> CardsPage:
    clean_search = clean_search_query(search)
    where_sql, params = build_search_filter(clean_search)

    with get_connection() as connection:
        count_cursor = connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
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
                cards.id,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.active,
                collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
            ORDER BY cards.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    cards = [
        CardListItem(
            id=row["id"],
            name=row["name"],
            position=row["position"],
            overall=row["overall"],
            team=row["team"],
            country=row["country"],
            collection_name=row["collection_name"],
            rarity=row["rarity"],
            active=bool(row["active"]),
        )
        for row in rows
    ]

    return CardsPage(
        cards=cards,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
    )


async def get_card_profile(card_id: int) -> CardProfile | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                cards.id,
                cards.name,
                cards.player_key,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.collection_id,
                cards.rarity,
                cards.image_path,
                cards.active,
                collections.code AS collection_code,
                collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.id = ?
            """,
            (card_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return CardProfile(
        id=row["id"],
        name=row["name"],
        player_key=row["player_key"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        country=row["country"],
        collection_id=row["collection_id"],
        collection_code=row["collection_code"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
        image_path=row["image_path"],
        active=bool(row["active"]),
    )


async def get_or_create_collection(name: str) -> int:
    collection_name = clean_text(name)
    collection_code = build_collection_code(collection_name)

    with get_connection() as connection:
        cursor = connection.execute(
            "SELECT id FROM collections WHERE code = ? OR name = ?",
            (collection_code, collection_name),
        )
        row = cursor.fetchone()

        if row is not None:
            return int(row["id"])

        connection.execute(
            """
            INSERT INTO collections (code, name, description, active)
            VALUES (?, ?, '', 1)
            """,
            (collection_code, collection_name),
        )
        connection.commit()

        cursor = connection.execute(
            "SELECT id FROM collections WHERE code = ?",
            (collection_code,),
        )
        return int(cursor.fetchone()["id"])


async def create_card(draft: CardDraft) -> CardProfile:
    collection_id = await get_or_create_collection(draft.collection_name)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO cards (
                name,
                player_key,
                position,
                overall,
                team,
                country,
                collection_id,
                rarity,
                image_path,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                draft.name,
                build_player_key(draft.name),
                draft.position,
                draft.overall,
                draft.team,
                draft.country,
                collection_id,
                draft.rarity,
                draft.image_path,
            ),
        )
        card_id = int(cursor.lastrowid)
        connection.commit()

    profile = await get_card_profile(card_id)

    if profile is None:
        raise RuntimeError("Карточка не найдена после сохранения")

    return profile


async def toggle_card_active(card_id: int) -> CardProfile | None:
    card = await get_card_profile(card_id)

    if card is None:
        return None

    new_value = 0 if card.active else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET
                active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_value, card_id),
        )
        connection.commit()

    return await get_card_profile(card_id)


async def update_card_text_field(card_id: int, field: str, value: str) -> CardProfile | None:
    allowed_fields = {"name", "team", "country"}

    if field not in allowed_fields:
        return None

    clean_value = validate_name(value) if field == "name" else validate_short_text(value)

    if clean_value is None:
        return None

    with get_connection() as connection:
        if field == "name":
            connection.execute(
                """
                UPDATE cards
                SET
                    name = ?,
                    player_key = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (clean_value, build_player_key(clean_value), card_id),
            )
        else:
            connection.execute(
                f"""
                UPDATE cards
                SET
                    {field} = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (clean_value, card_id),
            )

        connection.commit()

    return await get_card_profile(card_id)


async def update_card_overall(card_id: int, value: str) -> CardProfile | None:
    overall = validate_overall(value)

    if overall is None:
        return None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET
                overall = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (overall, card_id),
        )
        connection.commit()

    return await get_card_profile(card_id)


async def update_card_position(card_id: int, position: str) -> CardProfile | None:
    clean_position = validate_position(position)

    if clean_position is None:
        return None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET
                position = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (clean_position, card_id),
        )
        connection.commit()

    return await get_card_profile(card_id)


async def update_card_rarity(card_id: int, rarity: str) -> CardProfile | None:
    clean_rarity = validate_rarity(rarity)

    if clean_rarity is None:
        return None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET
                rarity = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (clean_rarity, card_id),
        )
        connection.commit()

    return await get_card_profile(card_id)


async def update_card_collection(card_id: int, collection_name: str) -> CardProfile | None:
    clean_collection = validate_short_text(collection_name)

    if clean_collection is None:
        return None

    collection_id = await get_or_create_collection(clean_collection)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET
                collection_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (collection_id, card_id),
        )
        connection.commit()

    return await get_card_profile(card_id)


async def update_card_image_path(card_id: int, image_path: str) -> CardProfile | None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET
                image_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (image_path, card_id),
        )
        connection.commit()

    return await get_card_profile(card_id)


async def get_collections() -> list[CollectionItem]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                collections.id,
                collections.code,
                collections.name,
                collections.description,
                collections.active,
                COUNT(cards.id) AS cards_count
            FROM collections
            LEFT JOIN cards ON cards.collection_id = collections.id
            GROUP BY collections.id
            ORDER BY collections.id ASC
            """
        )
        rows = cursor.fetchall()

    return [
        CollectionItem(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            description=row["description"],
            active=bool(row["active"]),
            cards_count=row["cards_count"],
        )
        for row in rows
    ]
