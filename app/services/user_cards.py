from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.admin_cards import clean_search_query
from app.services.card_sorting import get_user_card_sort_order, order_by_overall


@dataclass(frozen=True)
class PlayerCardListItem:
    id: int
    card_id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    image_path: str
    is_in_lineup: bool
    trade_locked: bool


@dataclass(frozen=True)
class PlayerCardProfile:
    id: int
    card_id: int
    user_id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    collection_code: str
    rarity: str
    image_path: str
    is_in_lineup: bool
    lineup_slot: str | None
    trade_locked: bool
    lock_reason: str | None
    lock_until: str | None
    obtained_from: str
    created_at: str
    salary: int = 0


@dataclass(frozen=True)
class PlayerCardsPage:
    cards: list[PlayerCardListItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None
    position: str | None
    rarity: str | None
    sort_order: str = "ovr_desc"


@dataclass(frozen=True)
class CardChoiceItem:
    id: int
    name: str
    position: str
    overall: int
    team: str
    collection_name: str
    rarity: str
    active: bool


@dataclass(frozen=True)
class CardChoicePage:
    cards: list[CardChoiceItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


POSITIONS = {"G", "D", "F"}
RARITIES = {"Common", "Rare", "Epic", "Legendary", "Event", "Icon"}


def normalize_position(value: str | None) -> str | None:
    if value is None or value == "all":
        return None

    clean_value = value.strip().upper()
    return clean_value if clean_value in POSITIONS else None


def normalize_rarity(value: str | None) -> str | None:
    if value is None or value == "all":
        return None

    clean_value = " ".join(value.strip().split())
    return clean_value if clean_value in RARITIES else None


def build_player_cards_filter(
    search: str | None = None,
    position: str | None = None,
    rarity: str | None = None,
) -> tuple[str, list[object]]:
    filters = ["user_cards.user_id = ?"]
    params: list[object] = []

    clean_search = clean_search_query(search)
    clean_position = normalize_position(position)
    clean_rarity = normalize_rarity(rarity)

    if clean_search:
        if clean_search.isdigit():
            filters.append(
                """
                (
                    user_cards.id = ?
                    OR cards.id = ?
                    OR cards.name LIKE ?
                    OR cards.team LIKE ?
                    OR cards.country LIKE ?
                    OR collections.name LIKE ?
                )
                """
            )
            params.extend(
                [
                    int(clean_search),
                    int(clean_search),
                    f"%{clean_search}%",
                    f"%{clean_search}%",
                    f"%{clean_search}%",
                    f"%{clean_search}%",
                ]
            )
        else:
            filters.append(
                """
                (
                    cards.name LIKE ?
                    OR cards.team LIKE ?
                    OR cards.country LIKE ?
                    OR cards.rarity LIKE ?
                    OR cards.position LIKE ?
                    OR collections.name LIKE ?
                )
                """
            )
            params.extend([f"%{clean_search}%"] * 6)

    if clean_position:
        filters.append("cards.position = ?")
        params.append(clean_position)

    if clean_rarity:
        filters.append("cards.rarity = ?")
        params.append(clean_rarity)

    return "WHERE " + " AND ".join(filters), params


def build_card_choice_filter(search: str | None = None) -> tuple[str, list[object]]:
    clean_search = clean_search_query(search)

    if clean_search is None:
        return "WHERE cards.active = 1", []

    if clean_search.isdigit():
        return """
        WHERE cards.active = 1
          AND (
              cards.id = ?
              OR cards.name LIKE ?
              OR cards.team LIKE ?
              OR cards.country LIKE ?
              OR collections.name LIKE ?
          )
        """, [
            int(clean_search),
            f"%{clean_search}%",
            f"%{clean_search}%",
            f"%{clean_search}%",
            f"%{clean_search}%",
        ]

    return """
    WHERE cards.active = 1
      AND (
          cards.name LIKE ?
          OR cards.team LIKE ?
          OR cards.country LIKE ?
          OR cards.rarity LIKE ?
          OR cards.position LIKE ?
          OR collections.name LIKE ?
      )
    """, [f"%{clean_search}%"] * 6


async def get_player_cards_page(
    user_id: int,
    page: int = 1,
    per_page: int = 5,
    search: str | None = None,
    position: str | None = None,
    rarity: str | None = None,
) -> PlayerCardsPage:
    clean_search = clean_search_query(search)
    clean_position = normalize_position(position)
    clean_rarity = normalize_rarity(rarity)
    where_sql, filter_params = build_player_cards_filter(clean_search, clean_position, clean_rarity)
    params = [user_id, *filter_params]
    sort_order = await get_user_card_sort_order(user_id)
    order_sql = order_by_overall(sort_order, card_alias="cards")

    with get_connection() as connection:
        count_cursor = connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
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
                user_cards.id,
                user_cards.card_id,
                user_cards.is_in_lineup,
                user_cards.trade_locked,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                collections.name AS collection_name
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
            ORDER BY {order_sql}, user_cards.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    cards = [
        PlayerCardListItem(
            id=row["id"],
            card_id=row["card_id"],
            name=row["name"],
            position=row["position"],
            overall=row["overall"],
            team=row["team"],
            country=row["country"],
            collection_name=row["collection_name"],
            rarity=row["rarity"],
            image_path=row["image_path"],
            is_in_lineup=bool(row["is_in_lineup"]),
            trade_locked=bool(row["trade_locked"]),
        )
        for row in rows
    ]

    return PlayerCardsPage(
        cards=cards,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
        position=clean_position,
        rarity=clean_rarity,
        sort_order=sort_order,
    )


async def get_player_card_profile(
    user_card_id: int,
    telegram_id: int | None = None,
) -> PlayerCardProfile | None:
    telegram_filter = "AND users.telegram_id = ?" if telegram_id is not None else ""
    params: list[object] = [user_card_id]

    if telegram_id is not None:
        params.append(telegram_id)

    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            SELECT
                user_cards.id,
                user_cards.card_id,
                user_cards.user_id,
                user_cards.is_in_lineup,
                user_cards.lineup_slot,
                user_cards.trade_locked,
                user_cards.lock_reason,
                user_cards.lock_until,
                user_cards.obtained_from,
                user_cards.created_at,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                cards.salary,
                collections.code AS collection_code,
                collections.name AS collection_name
            FROM user_cards
            JOIN users ON users.id = user_cards.user_id
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE user_cards.id = ?
            {telegram_filter}
            """,
            params,
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return PlayerCardProfile(
        id=row["id"],
        card_id=row["card_id"],
        user_id=row["user_id"],
        name=row["name"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        country=row["country"],
        collection_name=row["collection_name"],
        collection_code=row["collection_code"],
        rarity=row["rarity"],
        image_path=row["image_path"],
        is_in_lineup=bool(row["is_in_lineup"]),
        lineup_slot=row["lineup_slot"],
        trade_locked=bool(row["trade_locked"]),
        lock_reason=row["lock_reason"],
        lock_until=row["lock_until"],
        obtained_from=row["obtained_from"],
        created_at=row["created_at"],
        salary=int(row["salary"] or 0),
    )


async def get_card_choice_page(
    page: int = 1,
    per_page: int = 5,
    search: str | None = None,
) -> CardChoicePage:
    clean_search = clean_search_query(search)
    where_sql, params = build_card_choice_filter(clean_search)

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
                cards.rarity,
                cards.active,
                collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
            ORDER BY cards.overall DESC, cards.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    cards = [
        CardChoiceItem(
            id=row["id"],
            name=row["name"],
            position=row["position"],
            overall=row["overall"],
            team=row["team"],
            collection_name=row["collection_name"],
            rarity=row["rarity"],
            active=bool(row["active"]),
        )
        for row in rows
    ]

    return CardChoicePage(
        cards=cards,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
    )


async def give_card_to_user(
    user_id: int,
    card_id: int,
    obtained_from: str = "admin",
) -> PlayerCardProfile | None:
    with get_connection() as connection:
        user_cursor = connection.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        card_cursor = connection.execute("SELECT id FROM cards WHERE id = ? AND active = 1", (card_id,))

        if user_cursor.fetchone() is None or card_cursor.fetchone() is None:
            return None

        cursor = connection.execute(
            """
            INSERT INTO user_cards (
                user_id,
                card_id,
                obtained_from,
                is_in_lineup,
                trade_locked
            )
            VALUES (?, ?, ?, 0, 0)
            """,
            (user_id, card_id, obtained_from),
        )
        user_card_id = int(cursor.lastrowid)
        connection.commit()

    return await get_player_card_profile(user_card_id)


async def count_user_cards(user_id: int) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            "SELECT COUNT(*) AS total_count FROM user_cards WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

    return int(row["total_count"]) if row else 0
