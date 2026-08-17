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
    salary: int
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
    salary: int = 0


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

    if 1 <= overall <= 110:
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
            LEFT JOIN collections ON collections.id = cards.collection_id
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
                COALESCE(collections.name, 'Без коллекции') AS collection_name
            FROM cards
            LEFT JOIN collections ON collections.id = cards.collection_id
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
                cards.salary,
                cards.active,
                COALESCE(collections.code, '') AS collection_code,
                COALESCE(collections.name, 'Без коллекции') AS collection_name
            FROM cards
            LEFT JOIN collections ON collections.id = cards.collection_id
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
        salary=int(row["salary"] or 0),
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
                salary,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
                draft.salary,
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


async def update_card_salary(card_id: int, value: str) -> CardProfile | None:
    from app.services.salary import parse_salary

    salary = parse_salary(value)
    if salary is None:
        return None

    with get_connection() as connection:
        connection.execute(
            "UPDATE cards SET salary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (salary, card_id),
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


@dataclass(frozen=True)
class CardOwnerSummary:
    user_id: int
    telegram_id: int
    username: str | None
    nickname: str
    quantity: int


@dataclass(frozen=True)
class CardOwnersPage:
    card_id: int
    card_name: str
    card_overall: int
    owners: list[CardOwnerSummary]
    page: int
    pages_count: int
    total_owners: int
    total_copies: int


@dataclass(frozen=True)
class CardOwnerCopy:
    user_card_id: int
    user_id: int
    telegram_id: int
    username: str | None
    nickname: str
    is_in_lineup: bool
    lineup_slot: str | None
    trade_locked: bool
    lock_reason: str | None
    obtained_from: str
    has_frame: bool
    is_ranked_captain: bool
    in_open_trade: bool
    created_at: str


@dataclass(frozen=True)
class CardOwnerCopiesPage:
    card_id: int
    card_name: str
    card_overall: int
    owner_user_id: int
    owner_telegram_id: int
    owner_username: str | None
    owner_nickname: str
    copies: list[CardOwnerCopy]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class RevokeOwnedCardResult:
    success: bool
    message: str
    card_id: int | None = None
    card_name: str | None = None
    user_card_id: int | None = None
    owner_user_id: int | None = None
    owner_telegram_id: int | None = None
    owner_nickname: str | None = None


async def get_card_owners_page(card_id: int, page: int = 1, per_page: int = 6) -> CardOwnersPage | None:
    with get_connection() as connection:
        card = connection.execute(
            "SELECT id, name, overall FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        if card is None:
            return None

        totals = connection.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS owners_count, COUNT(*) AS copies_count
            FROM user_cards
            WHERE card_id = ?
            """,
            (card_id,),
        ).fetchone()
        total_owners = int(totals["owners_count"] or 0)
        total_copies = int(totals["copies_count"] or 0)
        pages_count = max(1, ceil(total_owners / per_page))
        safe_page = min(max(int(page), 1), pages_count)
        offset = (safe_page - 1) * per_page

        rows = connection.execute(
            """
            SELECT
                users.id AS user_id,
                users.telegram_id,
                users.username,
                users.nickname,
                COUNT(user_cards.id) AS quantity
            FROM user_cards
            JOIN users ON users.id = user_cards.user_id
            WHERE user_cards.card_id = ?
            GROUP BY users.id
            ORDER BY quantity DESC, users.nickname COLLATE NOCASE, users.id
            LIMIT ? OFFSET ?
            """,
            (card_id, per_page, offset),
        ).fetchall()

    return CardOwnersPage(
        card_id=int(card["id"]),
        card_name=str(card["name"]),
        card_overall=int(card["overall"]),
        owners=[
            CardOwnerSummary(
                user_id=int(row["user_id"]),
                telegram_id=int(row["telegram_id"]),
                username=row["username"],
                nickname=str(row["nickname"]),
                quantity=int(row["quantity"]),
            )
            for row in rows
        ],
        page=safe_page,
        pages_count=pages_count,
        total_owners=total_owners,
        total_copies=total_copies,
    )


async def get_card_owner_copies_page(
    card_id: int,
    owner_user_id: int,
    page: int = 1,
    per_page: int = 6,
) -> CardOwnerCopiesPage | None:
    with get_connection() as connection:
        header = connection.execute(
            """
            SELECT cards.id AS card_id, cards.name AS card_name, cards.overall,
                   users.id AS user_id, users.telegram_id, users.username, users.nickname
            FROM cards CROSS JOIN users
            WHERE cards.id = ? AND users.id = ?
            """,
            (card_id, owner_user_id),
        ).fetchone()
        if header is None:
            return None

        total_count = int(
            connection.execute(
                "SELECT COUNT(*) AS n FROM user_cards WHERE card_id = ? AND user_id = ?",
                (card_id, owner_user_id),
            ).fetchone()["n"]
        )
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(int(page), 1), pages_count)
        offset = (safe_page - 1) * per_page

        rows = connection.execute(
            """
            SELECT
                uc.id AS user_card_id,
                uc.user_id,
                u.telegram_id,
                u.username,
                u.nickname,
                uc.is_in_lineup,
                uc.lineup_slot,
                uc.trade_locked,
                uc.lock_reason,
                uc.obtained_from,
                uc.created_at,
                CASE WHEN ucf.id IS NOT NULL THEN 1 ELSE 0 END AS has_frame,
                CASE WHEN rc.id IS NOT NULL THEN 1 ELSE 0 END AS is_ranked_captain,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM trade_offer_cards toc
                    JOIN trade_offers t ON t.id = toc.offer_id
                    WHERE toc.user_card_id = uc.id AND t.status = 'open'
                ) THEN 1 ELSE 0 END AS in_open_trade
            FROM user_cards uc
            JOIN users u ON u.id = uc.user_id
            LEFT JOIN user_card_frames ucf ON ucf.user_card_id = uc.id
            LEFT JOIN ranked_captains rc ON rc.user_card_id = uc.id
            WHERE uc.card_id = ? AND uc.user_id = ?
            ORDER BY uc.id DESC
            LIMIT ? OFFSET ?
            """,
            (card_id, owner_user_id, per_page, offset),
        ).fetchall()

    copies = [
        CardOwnerCopy(
            user_card_id=int(row["user_card_id"]),
            user_id=int(row["user_id"]),
            telegram_id=int(row["telegram_id"]),
            username=row["username"],
            nickname=str(row["nickname"]),
            is_in_lineup=bool(row["is_in_lineup"]),
            lineup_slot=row["lineup_slot"],
            trade_locked=bool(row["trade_locked"]),
            lock_reason=row["lock_reason"],
            obtained_from=str(row["obtained_from"]),
            has_frame=bool(row["has_frame"]),
            is_ranked_captain=bool(row["is_ranked_captain"]),
            in_open_trade=bool(row["in_open_trade"]),
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]

    return CardOwnerCopiesPage(
        card_id=int(header["card_id"]),
        card_name=str(header["card_name"]),
        card_overall=int(header["overall"]),
        owner_user_id=int(header["user_id"]),
        owner_telegram_id=int(header["telegram_id"]),
        owner_username=header["username"],
        owner_nickname=str(header["nickname"]),
        copies=copies,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )


async def get_owned_card_copy(user_card_id: int) -> CardOwnerCopy | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                uc.id AS user_card_id,
                uc.user_id,
                u.telegram_id,
                u.username,
                u.nickname,
                uc.is_in_lineup,
                uc.lineup_slot,
                uc.trade_locked,
                uc.lock_reason,
                uc.obtained_from,
                uc.created_at,
                CASE WHEN ucf.id IS NOT NULL THEN 1 ELSE 0 END AS has_frame,
                CASE WHEN rc.id IS NOT NULL THEN 1 ELSE 0 END AS is_ranked_captain,
                CASE WHEN EXISTS (
                    SELECT 1 FROM trade_offer_cards toc
                    JOIN trade_offers t ON t.id = toc.offer_id
                    WHERE toc.user_card_id = uc.id AND t.status = 'open'
                ) THEN 1 ELSE 0 END AS in_open_trade
            FROM user_cards uc
            JOIN users u ON u.id = uc.user_id
            LEFT JOIN user_card_frames ucf ON ucf.user_card_id = uc.id
            LEFT JOIN ranked_captains rc ON rc.user_card_id = uc.id
            WHERE uc.id = ?
            """,
            (user_card_id,),
        ).fetchone()
    if row is None:
        return None
    return CardOwnerCopy(
        user_card_id=int(row["user_card_id"]), user_id=int(row["user_id"]), telegram_id=int(row["telegram_id"]),
        username=row["username"], nickname=str(row["nickname"]), is_in_lineup=bool(row["is_in_lineup"]),
        lineup_slot=row["lineup_slot"], trade_locked=bool(row["trade_locked"]), lock_reason=row["lock_reason"],
        obtained_from=str(row["obtained_from"]), has_frame=bool(row["has_frame"]),
        is_ranked_captain=bool(row["is_ranked_captain"]), in_open_trade=bool(row["in_open_trade"]),
        created_at=str(row["created_at"]),
    )


async def revoke_owned_card_copy(user_card_id: int, *, admin_telegram_id: int) -> RevokeOwnedCardResult:
    """Remove one exact owned copy, with admin override semantics.

    Any open trade that contains the exact instance is cancelled first.  A bound
    frame is not destroyed: deleting user_card_frames via FK simply returns that
    cosmetic copy to the owner's inventory.  Ranked captain binding is removed by
    FK cascade as well.
    """
    from app.services.audit_log import record

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT uc.id AS user_card_id, uc.card_id, uc.user_id,
                   c.name AS card_name, u.telegram_id, u.nickname
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            JOIN users u ON u.id = uc.user_id
            WHERE uc.id = ?
            """,
            (user_card_id,),
        ).fetchone()
        if row is None:
            connection.rollback()
            return RevokeOwnedCardResult(False, "Экземпляр уже отсутствует.")

        # Cancel affected open offers before the FK cascade removes the offer-card row.
        offer_rows = connection.execute(
            """
            SELECT DISTINCT t.id
            FROM trade_offer_cards toc
            JOIN trade_offers t ON t.id = toc.offer_id
            WHERE toc.user_card_id = ? AND t.status = 'open'
            """,
            (user_card_id,),
        ).fetchall()
        offer_ids = [int(item["id"]) for item in offer_rows]
        if offer_ids:
            placeholders = ",".join("?" for _ in offer_ids)
            connection.execute(
                f"UPDATE trade_offers SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                offer_ids,
            )

        # Avoid leaving a broken available creator-bank row pointing to NULL.
        connection.execute(
            "UPDATE creator_bank_items SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE user_card_id = ? AND status = 'available'",
            (user_card_id,),
        )

        connection.execute("DELETE FROM user_cards WHERE id = ?", (user_card_id,))
        record(
            connection,
            admin_telegram_id,
            "admin_revoke_user_card",
            "user_card",
            int(user_card_id),
            {
                "card_id": int(row["card_id"]),
                "card_name": str(row["card_name"]),
                "owner_user_id": int(row["user_id"]),
                "owner_telegram_id": int(row["telegram_id"]),
                "owner_nickname": str(row["nickname"]),
                "cancelled_trade_offer_ids": offer_ids,
            },
        )
        connection.commit()

    return RevokeOwnedCardResult(
        True,
        "Карточка забрана у владельца.",
        card_id=int(row["card_id"]),
        card_name=str(row["card_name"]),
        user_card_id=int(row["user_card_id"]),
        owner_user_id=int(row["user_id"]),
        owner_telegram_id=int(row["telegram_id"]),
        owner_nickname=str(row["nickname"]),
    )
