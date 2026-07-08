from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

from app.database.db import get_connection
from app.services.admin_users import clean_search_query

COMMUNITY_PER_PAGE = 5
CLAN_MAX_MEMBERS = 10
TRADE_CARD_LIMIT = 3


@dataclass(frozen=True)
class CommunityPlayerItem:
    id: int
    nickname: str
    username: str | None
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    privacy_public_cards: bool


@dataclass(frozen=True)
class CommunityPlayersPage:
    players: list[CommunityPlayerItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


@dataclass(frozen=True)
class PublicCardItem:
    id: int
    name: str
    position: str
    overall: int
    team: str
    collection_name: str
    rarity: str
    image_path: str


@dataclass(frozen=True)
class PublicPlayerProfile:
    id: int
    nickname: str
    username: str | None
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    goals_scored: int
    goals_allowed: int
    hockey_pass_level: int
    privacy_public_cards: bool
    lineup_ovr: int
    lineup_count: int
    public_cards_count: int
    lineup_cards: list[PublicCardItem]
    top_cards: list[PublicCardItem]


@dataclass(frozen=True)
class TradeUserCardItem:
    id: int
    card_id: int
    name: str
    position: str
    overall: int
    team: str
    collection_name: str
    rarity: str


@dataclass(frozen=True)
class TradeUserCardsPage:
    cards: list[TradeUserCardItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None
    selected_ids: list[int]


@dataclass(frozen=True)
class TradeCardChoiceItem:
    id: int
    name: str
    position: str
    overall: int
    team: str
    collection_name: str
    rarity: str


@dataclass(frozen=True)
class TradeCardChoicesPage:
    cards: list[TradeCardChoiceItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None
    selected_card_ids: list[int]


@dataclass(frozen=True)
class TradeOfferListItem:
    id: int
    creator_user_id: int
    creator_nickname: str
    target_user_id: int | None
    target_nickname: str | None
    wanted_type: str
    wanted_currency_code: str | None
    wanted_currency_icon: str | None
    wanted_currency_name: str | None
    wanted_currency_amount: int
    offered_count: int
    wanted_cards_count: int
    status: str
    created_at: str


@dataclass(frozen=True)
class TradeOffersPage:
    offers: list[TradeOfferListItem]
    page: int
    pages_count: int
    total_count: int
    mode: str


@dataclass(frozen=True)
class TradeOfferProfile:
    id: int
    creator_user_id: int
    creator_nickname: str
    target_user_id: int | None
    target_nickname: str | None
    accepted_by_user_id: int | None
    accepted_by_nickname: str | None
    wanted_type: str
    wanted_currency_code: str | None
    wanted_currency_icon: str | None
    wanted_currency_name: str | None
    wanted_currency_amount: int
    status: str
    created_at: str
    accepted_at: str | None
    offered_cards: list[TradeUserCardItem]
    wanted_cards: list[tuple[TradeCardChoiceItem, int]]


@dataclass(frozen=True)
class ClanListItem:
    id: int
    name: str
    description: str
    rating_points: int
    wins: int
    members_count: int
    active: bool


@dataclass(frozen=True)
class ClansPage:
    clans: list[ClanListItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


@dataclass(frozen=True)
class ClanMemberItem:
    user_id: int
    nickname: str
    role: str
    joined_at: str


@dataclass(frozen=True)
class ClanProfile:
    id: int
    name: str
    description: str
    rating_points: int
    wins: int
    active: bool
    created_by_user_id: int | None
    created_by_nickname: str | None
    members_count: int
    viewer_role: str | None
    members: list[ClanMemberItem]


@dataclass(frozen=True)
class CommunityActionResult:
    ok: bool
    title: str
    description: str
    offer_id: int | None = None
    target_telegram_id: int | None = None
    creator_telegram_id: int | None = None


def normalize_ids(values: list[int] | None) -> list[int]:
    if not values:
        return []
    clean_values: list[int] = []
    for value in values:
        if value not in clean_values:
            clean_values.append(int(value))
    return clean_values[:TRADE_CARD_LIMIT]


def get_user_id_by_telegram_id(telegram_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
    return int(row["id"]) if row else None


def build_player_search_filter(search: str | None) -> tuple[str, list[object]]:
    clean_search = clean_search_query(search)

    if clean_search is None:
        return "WHERE is_banned = 0", []

    if clean_search.isdigit():
        return """
        WHERE is_banned = 0
          AND (
              id = ?
              OR telegram_id = ?
              OR nickname LIKE ?
              OR username LIKE ?
          )
        """, [int(clean_search), int(clean_search), f"%{clean_search}%", f"%{clean_search}%"]

    return """
    WHERE is_banned = 0
      AND (
          nickname LIKE ?
          OR username LIKE ?
          OR first_name LIKE ?
          OR last_name LIKE ?
      )
    """, [f"%{clean_search}%"] * 4


async def get_players_page(page: int = 1, per_page: int = COMMUNITY_PER_PAGE, search: str | None = None) -> CommunityPlayersPage:
    clean_search = clean_search_query(search)
    where_sql, params = build_player_search_filter(clean_search)

    with get_connection() as connection:
        total_count = int(connection.execute(
            f"SELECT COUNT(*) AS total_count FROM users {where_sql}",
            params,
        ).fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT id, nickname, username, league, rating_points, wins, losses, matches_played, privacy_public_cards
            FROM users
            {where_sql}
            ORDER BY rating_points DESC, wins DESC, matches_played DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return CommunityPlayersPage(
        players=[
            CommunityPlayerItem(
                id=row["id"],
                nickname=row["nickname"],
                username=row["username"],
                league=row["league"],
                rating_points=row["rating_points"],
                wins=row["wins"],
                losses=row["losses"],
                matches_played=row["matches_played"],
                privacy_public_cards=bool(row["privacy_public_cards"]),
            )
            for row in rows
        ],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
    )


async def get_direct_trade_players_page(user_id: int, page: int = 1, per_page: int = COMMUNITY_PER_PAGE, search: str | None = None) -> CommunityPlayersPage:
    clean_search = clean_search_query(search)
    where_sql, params = build_player_search_filter(clean_search)
    extra = "privacy_public_cards = 1 AND is_banned = 0 AND trade_blocked = 0 AND id != ?"
    if where_sql:
        where_sql = where_sql.replace("WHERE", f"WHERE {extra} AND", 1)
        params = [user_id, *params]
    else:
        where_sql = f"WHERE {extra}"
        params = [user_id]

    with get_connection() as connection:
        total_count = int(connection.execute(f"SELECT COUNT(*) AS total_count FROM users {where_sql}", params).fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT id, nickname, username, league, rating_points, wins, losses, matches_played, privacy_public_cards
            FROM users
            {where_sql}
            ORDER BY rating_points DESC, wins DESC, matches_played DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return CommunityPlayersPage(
        players=[
            CommunityPlayerItem(
                id=row["id"], nickname=row["nickname"], username=row["username"], league=row["league"],
                rating_points=row["rating_points"], wins=row["wins"], losses=row["losses"],
                matches_played=row["matches_played"], privacy_public_cards=bool(row["privacy_public_cards"]),
            )
            for row in rows
        ],
        page=safe_page, pages_count=pages_count, total_count=total_count, search=clean_search,
    )


async def get_trade_offer_creator_telegram_id(offer_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT users.telegram_id
            FROM trade_offers
            JOIN users ON users.id = trade_offers.creator_user_id
            WHERE trade_offers.id = ?
            """,
            (offer_id,),
        ).fetchone()
    return int(row["telegram_id"]) if row else None


def row_to_public_card(row) -> PublicCardItem:
    return PublicCardItem(
        id=row["user_card_id"],
        name=row["name"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
        image_path=row["image_path"],
    )


async def get_public_player_profile(player_id: int, viewer_user_id: int | None = None) -> PublicPlayerProfile | None:
    with get_connection() as connection:
        user_row = connection.execute(
            """
            SELECT id, nickname, username, league, rating_points, wins, losses, matches_played,
                   goals_scored, goals_allowed, hockey_pass_level, privacy_public_cards
            FROM users
            WHERE id = ? AND is_banned = 0
            """,
            (player_id,),
        ).fetchone()

        if user_row is None:
            return None

        lineup_rows = connection.execute(
            """
            SELECT user_cards.id AS user_card_id, cards.name, cards.position, cards.overall, cards.team,
                   collections.name AS collection_name, cards.rarity, cards.image_path
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE user_cards.user_id = ? AND user_cards.is_in_lineup = 1
            ORDER BY
                CASE user_cards.lineup_slot
                    WHEN 'G' THEN 1
                    WHEN 'D1' THEN 2
                    WHEN 'D2' THEN 3
                    WHEN 'F1' THEN 4
                    WHEN 'F2' THEN 5
                    WHEN 'F3' THEN 6
                    ELSE 99
                END
            """,
            (player_id,),
        ).fetchall()

        public_cards_count = int(connection.execute(
            "SELECT COUNT(*) AS total_count FROM user_cards WHERE user_id = ?",
            (player_id,),
        ).fetchone()["total_count"])

        top_rows = []
        if bool(user_row["privacy_public_cards"]) or viewer_user_id == player_id:
            top_rows = connection.execute(
                """
                SELECT user_cards.id AS user_card_id, cards.name, cards.position, cards.overall, cards.team,
                       collections.name AS collection_name, cards.rarity, cards.image_path
                FROM user_cards
                JOIN cards ON cards.id = user_cards.card_id
                JOIN collections ON collections.id = cards.collection_id
                WHERE user_cards.user_id = ?
                ORDER BY cards.overall DESC, cards.id DESC
                LIMIT 5
                """,
                (player_id,),
            ).fetchall()

    lineup_cards = [row_to_public_card(row) for row in lineup_rows]
    lineup_count = len(lineup_cards)
    lineup_ovr = round(sum(card.overall for card in lineup_cards) / lineup_count) if lineup_count else 0

    return PublicPlayerProfile(
        id=user_row["id"],
        nickname=user_row["nickname"],
        username=user_row["username"],
        league=user_row["league"],
        rating_points=user_row["rating_points"],
        wins=user_row["wins"],
        losses=user_row["losses"],
        matches_played=user_row["matches_played"],
        goals_scored=user_row["goals_scored"],
        goals_allowed=user_row["goals_allowed"],
        hockey_pass_level=user_row["hockey_pass_level"],
        privacy_public_cards=bool(user_row["privacy_public_cards"]),
        lineup_ovr=lineup_ovr,
        lineup_count=lineup_count,
        public_cards_count=public_cards_count,
        lineup_cards=lineup_cards,
        top_cards=[row_to_public_card(row) for row in top_rows],
    )


def build_available_cards_filter(user_id: int, search: str | None, selected_ids: list[int] | None = None) -> tuple[str, list[object]]:
    clean_search = clean_search_query(search)
    selected_ids = normalize_ids(selected_ids)
    filters = [
        "user_cards.user_id = ?",
        "user_cards.is_in_lineup = 0",
        "user_cards.trade_locked = 0",
        "cards.active = 1",
        "NOT EXISTS (SELECT 1 FROM trade_offer_cards toc JOIN trade_offers t ON t.id = toc.offer_id WHERE toc.user_card_id = user_cards.id AND t.status = 'open')",
    ]
    params: list[object] = [user_id]

    if selected_ids:
        placeholders = ",".join("?" for _ in selected_ids)
        filters.append(f"user_cards.id NOT IN ({placeholders})")
        params.extend(selected_ids)

    if clean_search:
        if clean_search.isdigit():
            filters.append("(user_cards.id = ? OR cards.id = ? OR cards.name LIKE ? OR cards.team LIKE ? OR collections.name LIKE ?)")
            params.extend([int(clean_search), int(clean_search), f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"])
        else:
            filters.append("(cards.name LIKE ? OR cards.team LIKE ? OR cards.rarity LIKE ? OR cards.position LIKE ? OR collections.name LIKE ?)")
            params.extend([f"%{clean_search}%"] * 5)

    return "WHERE " + " AND ".join(filters), params


async def get_available_user_cards_page(
    user_id: int,
    page: int = 1,
    per_page: int = COMMUNITY_PER_PAGE,
    search: str | None = None,
    selected_ids: list[int] | None = None,
) -> TradeUserCardsPage:
    selected_ids = normalize_ids(selected_ids)
    clean_search = clean_search_query(search)
    where_sql, params = build_available_cards_filter(user_id, clean_search, selected_ids)

    with get_connection() as connection:
        total_count = int(connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
            """,
            params,
        ).fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT user_cards.id, cards.id AS card_id, cards.name, cards.position, cards.overall,
                   cards.team, collections.name AS collection_name, cards.rarity
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
            ORDER BY cards.overall DESC, user_cards.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return TradeUserCardsPage(
        cards=[trade_user_card_from_row(row) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
        selected_ids=selected_ids,
    )


def trade_user_card_from_row(row) -> TradeUserCardItem:
    return TradeUserCardItem(
        id=row["id"],
        card_id=row["card_id"],
        name=row["name"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
    )


async def get_selected_user_cards(user_id: int, selected_ids: list[int]) -> list[TradeUserCardItem]:
    selected_ids = normalize_ids(selected_ids)
    if not selected_ids:
        return []

    placeholders = ",".join("?" for _ in selected_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT user_cards.id, cards.id AS card_id, cards.name, cards.position, cards.overall,
                   cards.team, collections.name AS collection_name, cards.rarity
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE user_cards.user_id = ? AND user_cards.id IN ({placeholders})
            ORDER BY cards.overall DESC
            """,
            [user_id, *selected_ids],
        ).fetchall()

    return [trade_user_card_from_row(row) for row in rows]


def build_card_choice_filter(search: str | None) -> tuple[str, list[object]]:
    clean_search = clean_search_query(search)
    if clean_search is None:
        return "WHERE cards.active = 1", []

    if clean_search.isdigit():
        return """
        WHERE cards.active = 1
          AND (cards.id = ? OR cards.name LIKE ? OR cards.team LIKE ? OR collections.name LIKE ?)
        """, [int(clean_search), f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"]

    return """
    WHERE cards.active = 1
      AND (cards.name LIKE ? OR cards.team LIKE ? OR cards.rarity LIKE ? OR cards.position LIKE ? OR collections.name LIKE ?)
    """, [f"%{clean_search}%"] * 5


async def get_card_choices_page(page: int = 1, per_page: int = COMMUNITY_PER_PAGE, search: str | None = None, selected_card_ids: list[int] | None = None) -> TradeCardChoicesPage:
    clean_search = clean_search_query(search)
    selected_card_ids = normalize_ids(selected_card_ids)
    where_sql, params = build_card_choice_filter(clean_search)

    with get_connection() as connection:
        total_count = int(connection.execute(
            f"SELECT COUNT(*) AS total_count FROM cards JOIN collections ON collections.id = cards.collection_id {where_sql}",
            params,
        ).fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT cards.id, cards.name, cards.position, cards.overall, cards.team,
                   collections.name AS collection_name, cards.rarity
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where_sql}
            ORDER BY cards.overall DESC, cards.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return TradeCardChoicesPage(
        cards=[trade_card_choice_from_row(row) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
        selected_card_ids=selected_card_ids,
    )


def trade_card_choice_from_row(row) -> TradeCardChoiceItem:
    return TradeCardChoiceItem(
        id=row["id"],
        name=row["name"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
    )


async def get_selected_card_choices(selected_card_ids: list[int]) -> list[TradeCardChoiceItem]:
    selected_card_ids = normalize_ids(selected_card_ids)
    if not selected_card_ids:
        return []
    placeholders = ",".join("?" for _ in selected_card_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT cards.id, cards.name, cards.position, cards.overall, cards.team,
                   collections.name AS collection_name, cards.rarity
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.id IN ({placeholders}) AND cards.active = 1
            ORDER BY cards.overall DESC
            """,
            selected_card_ids,
        ).fetchall()
    return [trade_card_choice_from_row(row) for row in rows]


def get_user_trade_info(connection, user_id: int):
    return connection.execute(
        """
        SELECT id, telegram_id, nickname, privacy_public_cards, is_banned, trade_blocked
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


def build_direct_trade_notification(creator_nickname: str, offer_id: int) -> str:
    return f"""
<b>🔁 Новое предложение обмена</b>

Игрок <b>{creator_nickname}</b> отправил тебе личный обмен.

Открой предложение и выбери действие: принять или отказаться.
""".strip()


async def create_trade_offer(
    creator_user_id: int,
    offered_user_card_ids: list[int],
    wanted_type: Literal["cards", "currency"],
    wanted_card_ids: list[int] | None = None,
    wanted_currency_code: str | None = None,
    wanted_currency_amount: int = 0,
    target_user_id: int | None = None,
) -> CommunityActionResult:
    offered_user_card_ids = normalize_ids(offered_user_card_ids)
    wanted_card_ids = normalize_ids(wanted_card_ids)

    if not offered_user_card_ids:
        return CommunityActionResult(False, "Обмен не создан", "Выбери хотя бы одну карточку для обмена.")

    if wanted_type == "cards" and not wanted_card_ids:
        return CommunityActionResult(False, "Обмен не создан", "Выбери карточки, на которые хочешь обменяться.")

    if wanted_type == "currency" and (not wanted_currency_code or wanted_currency_amount <= 0):
        return CommunityActionResult(False, "Обмен не создан", "Укажи валюту и сумму для обмена.")

    with get_connection() as connection:
        creator_row = get_user_trade_info(connection, creator_user_id)
        if creator_row is None or bool(creator_row["trade_blocked"]):
            return CommunityActionResult(False, "Обмены закрыты", "Сейчас обмены для игрока недоступны.")

        target_row = None
        if target_user_id is not None:
            if target_user_id == creator_user_id:
                return CommunityActionResult(False, "Обмен не создан", "Нельзя отправить личный обмен самому себе.")
            target_row = get_user_trade_info(connection, target_user_id)
            if target_row is None or bool(target_row["is_banned"]):
                return CommunityActionResult(False, "Игрок не найден", "Выбранный игрок сейчас недоступен.")
            if not bool(target_row["privacy_public_cards"]):
                return CommunityActionResult(False, "Обмен не создан", "Игрок скрыл коллекцию карточек, поэтому личный обмен ему недоступен.")
            if bool(target_row["trade_blocked"]):
                return CommunityActionResult(False, "Обмен не создан", "У выбранного игрока сейчас закрыты обмены.")

        placeholders = ",".join("?" for _ in offered_user_card_ids)
        rows = connection.execute(
            f"""
            SELECT user_cards.id
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ?
              AND user_cards.id IN ({placeholders})
              AND user_cards.is_in_lineup = 0
              AND user_cards.trade_locked = 0
              AND cards.active = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM trade_offer_cards toc
                  JOIN trade_offers t ON t.id = toc.offer_id
                  WHERE toc.user_card_id = user_cards.id AND t.status = 'open'
              )
            """,
            [creator_user_id, *offered_user_card_ids],
        ).fetchall()
        if len(rows) != len(offered_user_card_ids):
            return CommunityActionResult(False, "Обмен не создан", "Одна из карточек уже занята, стоит в составе или недоступна.")

        if wanted_type == "currency":
            currency_row = connection.execute(
                "SELECT code FROM currencies WHERE code = ? AND active = 1",
                (wanted_currency_code,),
            ).fetchone()
            if currency_row is None:
                return CommunityActionResult(False, "Обмен не создан", "Выбранная валюта сейчас недоступна.")

        cursor = connection.execute(
            """
            INSERT INTO trade_offers (
                creator_user_id,
                target_user_id,
                wanted_type,
                wanted_currency_code,
                wanted_currency_amount,
                status
            )
            VALUES (?, ?, ?, ?, ?, 'open')
            """,
            (
                creator_user_id,
                target_user_id,
                wanted_type,
                wanted_currency_code if wanted_type == "currency" else None,
                wanted_currency_amount if wanted_type == "currency" else 0,
            ),
        )
        offer_id = int(cursor.lastrowid)

        for user_card_id in offered_user_card_ids:
            connection.execute(
                "INSERT INTO trade_offer_cards (offer_id, user_card_id) VALUES (?, ?)",
                (offer_id, user_card_id),
            )

        if wanted_type == "cards":
            for card_id in wanted_card_ids:
                connection.execute(
                    """
                    INSERT INTO trade_offer_wanted_cards (offer_id, card_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(offer_id, card_id) DO UPDATE SET quantity = quantity + 1
                    """,
                    (offer_id, card_id),
                )

        connection.commit()

    if target_user_id is not None:
        return CommunityActionResult(
            True,
            "Обмен отправлен",
            "Личное предложение отправлено игроку.",
            offer_id=offer_id,
            target_telegram_id=int(target_row["telegram_id"]) if target_row is not None else None,
            creator_telegram_id=int(creator_row["telegram_id"]),
        )

    return CommunityActionResult(True, "Обмен опубликован", "Предложение появилось на рынке обменов.", offer_id=offer_id, creator_telegram_id=int(creator_row["telegram_id"]))


def build_trade_mode_filter(mode: str, user_id: int | None = None) -> tuple[str, list[object]]:
    if mode == "my" and user_id is not None:
        return "WHERE trade_offers.creator_user_id = ? OR trade_offers.target_user_id = ?", [user_id, user_id]
    if mode == "incoming" and user_id is not None:
        return "WHERE trade_offers.target_user_id = ? AND trade_offers.status = 'open'", [user_id]
    if mode == "admin":
        return "", []
    return "WHERE trade_offers.status = 'open' AND trade_offers.target_user_id IS NULL", []


async def get_trade_offers_page(mode: str = "market", user_id: int | None = None, page: int = 1, per_page: int = COMMUNITY_PER_PAGE) -> TradeOffersPage:
    where_sql, params = build_trade_mode_filter(mode, user_id)
    with get_connection() as connection:
        total_count = int(connection.execute(
            f"SELECT COUNT(*) AS total_count FROM trade_offers {where_sql}",
            params,
        ).fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT trade_offers.id, trade_offers.creator_user_id, users.nickname AS creator_nickname,
                   trade_offers.target_user_id, target.nickname AS target_nickname,
                   trade_offers.wanted_type, trade_offers.wanted_currency_code, currencies.icon AS wanted_currency_icon,
                   currencies.name AS wanted_currency_name, trade_offers.wanted_currency_amount, trade_offers.status,
                   trade_offers.created_at,
                   (SELECT COUNT(*) FROM trade_offer_cards WHERE offer_id = trade_offers.id) AS offered_count,
                   (SELECT COALESCE(SUM(quantity), 0) FROM trade_offer_wanted_cards WHERE offer_id = trade_offers.id) AS wanted_cards_count
            FROM trade_offers
            JOIN users ON users.id = trade_offers.creator_user_id
            LEFT JOIN users target ON target.id = trade_offers.target_user_id
            LEFT JOIN currencies ON currencies.code = trade_offers.wanted_currency_code
            {where_sql}
            ORDER BY trade_offers.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return TradeOffersPage(
        offers=[
            TradeOfferListItem(
                id=row["id"],
                creator_user_id=row["creator_user_id"],
                creator_nickname=row["creator_nickname"],
                target_user_id=row["target_user_id"],
                target_nickname=row["target_nickname"],
                wanted_type=row["wanted_type"],
                wanted_currency_code=row["wanted_currency_code"],
                wanted_currency_icon=row["wanted_currency_icon"],
                wanted_currency_name=row["wanted_currency_name"],
                wanted_currency_amount=row["wanted_currency_amount"],
                offered_count=row["offered_count"],
                wanted_cards_count=row["wanted_cards_count"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        mode=mode,
    )


async def get_trade_offer_profile(offer_id: int) -> TradeOfferProfile | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT trade_offers.id, trade_offers.creator_user_id, creator.nickname AS creator_nickname,
                   trade_offers.target_user_id, target.nickname AS target_nickname,
                   trade_offers.accepted_by_user_id, accepter.nickname AS accepted_by_nickname,
                   trade_offers.wanted_type, trade_offers.wanted_currency_code,
                   currencies.icon AS wanted_currency_icon, currencies.name AS wanted_currency_name,
                   trade_offers.wanted_currency_amount, trade_offers.status, trade_offers.created_at, trade_offers.accepted_at
            FROM trade_offers
            JOIN users creator ON creator.id = trade_offers.creator_user_id
            LEFT JOIN users target ON target.id = trade_offers.target_user_id
            LEFT JOIN users accepter ON accepter.id = trade_offers.accepted_by_user_id
            LEFT JOIN currencies ON currencies.code = trade_offers.wanted_currency_code
            WHERE trade_offers.id = ?
            """,
            (offer_id,),
        ).fetchone()
        if row is None:
            return None

        offered_rows = connection.execute(
            """
            SELECT user_cards.id, cards.id AS card_id, cards.name, cards.position, cards.overall,
                   cards.team, collections.name AS collection_name, cards.rarity
            FROM trade_offer_cards
            JOIN user_cards ON user_cards.id = trade_offer_cards.user_card_id
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE trade_offer_cards.offer_id = ?
            ORDER BY cards.overall DESC
            """,
            (offer_id,),
        ).fetchall()

        wanted_rows = connection.execute(
            """
            SELECT cards.id, cards.name, cards.position, cards.overall, cards.team,
                   collections.name AS collection_name, cards.rarity, trade_offer_wanted_cards.quantity
            FROM trade_offer_wanted_cards
            JOIN cards ON cards.id = trade_offer_wanted_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE trade_offer_wanted_cards.offer_id = ?
            ORDER BY cards.overall DESC
            """,
            (offer_id,),
        ).fetchall()

    return TradeOfferProfile(
        id=row["id"],
        creator_user_id=row["creator_user_id"],
        creator_nickname=row["creator_nickname"],
        target_user_id=row["target_user_id"],
        target_nickname=row["target_nickname"],
        accepted_by_user_id=row["accepted_by_user_id"],
        accepted_by_nickname=row["accepted_by_nickname"],
        wanted_type=row["wanted_type"],
        wanted_currency_code=row["wanted_currency_code"],
        wanted_currency_icon=row["wanted_currency_icon"],
        wanted_currency_name=row["wanted_currency_name"],
        wanted_currency_amount=row["wanted_currency_amount"],
        status=row["status"],
        created_at=row["created_at"],
        accepted_at=row["accepted_at"],
        offered_cards=[trade_user_card_from_row(row) for row in offered_rows],
        wanted_cards=[(trade_card_choice_from_row(row), int(row["quantity"])) for row in wanted_rows],
    )


async def accept_trade_offer(offer_id: int, accepter_user_id: int) -> CommunityActionResult:
    with get_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            offer = connection.execute(
                "SELECT * FROM trade_offers WHERE id = ?",
                (offer_id,),
            ).fetchone()
            if offer is None or offer["status"] != "open":
                connection.rollback()
                return CommunityActionResult(False, "Обмен недоступен", "Предложение уже закрыто.")
            if offer["creator_user_id"] == accepter_user_id:
                connection.rollback()
                return CommunityActionResult(False, "Обмен недоступен", "Свое предложение принять нельзя.")
            accepter_row = get_user_trade_info(connection, accepter_user_id)
            creator_row = get_user_trade_info(connection, int(offer["creator_user_id"]))
            if accepter_row is None or bool(accepter_row["trade_blocked"]) or creator_row is None or bool(creator_row["trade_blocked"]):
                connection.rollback()
                return CommunityActionResult(False, "Обмен недоступен", "Для одного из игроков обмены сейчас закрыты.")
            if offer["target_user_id"] is not None and int(offer["target_user_id"]) != accepter_user_id:
                connection.rollback()
                return CommunityActionResult(False, "Обмен недоступен", "Личное предложение адресовано другому игроку.")

            offered_rows = connection.execute(
                "SELECT user_card_id FROM trade_offer_cards WHERE offer_id = ?",
                (offer_id,),
            ).fetchall()
            offered_ids = [int(row["user_card_id"]) for row in offered_rows]
            placeholders = ",".join("?" for _ in offered_ids)
            if not offered_ids:
                connection.rollback()
                return CommunityActionResult(False, "Обмен недоступен", "В предложении нет карточек.")
            valid_offered_count = int(connection.execute(
                f"""
                SELECT COUNT(*) AS total_count
                FROM user_cards
                WHERE id IN ({placeholders})
                  AND user_id = ?
                  AND is_in_lineup = 0
                  AND trade_locked = 0
                """,
                [*offered_ids, offer["creator_user_id"]],
            ).fetchone()["total_count"])
            if valid_offered_count != len(offered_ids):
                connection.rollback()
                return CommunityActionResult(False, "Обмен недоступен", "Одна из карточек владельца уже недоступна.")

            if offer["wanted_type"] == "currency":
                balance_row = connection.execute(
                    "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
                    (accepter_user_id, offer["wanted_currency_code"]),
                ).fetchone()
                balance = int(balance_row["amount"]) if balance_row else 0
                amount = int(offer["wanted_currency_amount"])
                if balance < amount:
                    connection.rollback()
                    return CommunityActionResult(False, "Не хватает валюты", "На балансе недостаточно средств для обмена.")

                deduct_cursor = connection.execute(
                    "UPDATE currency_balances SET amount = amount - ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND currency_code = ? AND amount >= ?",
                    (amount, accepter_user_id, offer["wanted_currency_code"], amount),
                )
                if deduct_cursor.rowcount != 1:
                    connection.rollback()
                    return CommunityActionResult(False, "Не хватает валюты", "На балансе недостаточно средств для обмена.")
                connection.execute(
                    """
                    INSERT INTO currency_balances (user_id, currency_code, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, currency_code) DO UPDATE SET
                        amount = amount + excluded.amount,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (offer["creator_user_id"], offer["wanted_currency_code"], amount),
                )
            else:
                wanted_rows = connection.execute(
                    "SELECT card_id, quantity FROM trade_offer_wanted_cards WHERE offer_id = ?",
                    (offer_id,),
                ).fetchall()
                wanted_user_card_ids: list[int] = []
                for wanted in wanted_rows:
                    owned_rows = connection.execute(
                        """
                        SELECT id
                        FROM user_cards
                        WHERE user_id = ?
                          AND card_id = ?
                          AND is_in_lineup = 0
                          AND trade_locked = 0
                        ORDER BY id ASC
                        LIMIT ?
                        """,
                        (accepter_user_id, wanted["card_id"], wanted["quantity"]),
                    ).fetchall()
                    if len(owned_rows) < int(wanted["quantity"]):
                        connection.rollback()
                        return CommunityActionResult(False, "Не хватает карточек", "В коллекции нет всех карточек для обмена.")
                    wanted_user_card_ids.extend(int(row["id"]) for row in owned_rows)

                for user_card_id in wanted_user_card_ids:
                    connection.execute(
                        "UPDATE user_cards SET user_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (offer["creator_user_id"], user_card_id),
                    )

            for user_card_id in offered_ids:
                connection.execute(
                    "UPDATE user_cards SET user_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (accepter_user_id, user_card_id),
                )

            connection.execute(
                """
                UPDATE trade_offers
                SET status = 'accepted', accepted_by_user_id = ?, accepted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (accepter_user_id, offer_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return CommunityActionResult(True, "Обмен завершён", "Карточки и награды уже в новых коллекциях.")


async def decline_trade_offer(offer_id: int, user_id: int) -> CommunityActionResult:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, creator_user_id, target_user_id, status
            FROM trade_offers
            WHERE id = ?
            """,
            (offer_id,),
        ).fetchone()
        if row is None or row["status"] != "open" or row["target_user_id"] != user_id:
            return CommunityActionResult(False, "Обмен недоступен", "Предложение уже закрыто или адресовано другому игроку.")
        connection.execute(
            "UPDATE trade_offers SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (offer_id,),
        )
        connection.commit()
    return CommunityActionResult(True, "Обмен отклонён", "Предложение закрыто без обмена.", offer_id=offer_id)


async def cancel_trade_offer(offer_id: int, user_id: int | None = None, admin: bool = False) -> CommunityActionResult:
    with get_connection() as connection:
        if admin:
            row = connection.execute("SELECT id FROM trade_offers WHERE id = ? AND status = 'open'", (offer_id,)).fetchone()
            params = (offer_id,)
            query = "UPDATE trade_offers SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'"
        else:
            row = connection.execute("SELECT id FROM trade_offers WHERE id = ? AND creator_user_id = ? AND status = 'open'", (offer_id, user_id)).fetchone()
            params = (offer_id, user_id)
            query = "UPDATE trade_offers SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND creator_user_id = ? AND status = 'open'"
        if row is None:
            return CommunityActionResult(False, "Обмен не изменён", "Предложение уже закрыто или недоступно.")
        connection.execute(query, params)
        connection.commit()
    return CommunityActionResult(True, "Обмен отменён", "Предложение больше не отображается на рынке.")


async def delete_trade_offer(offer_id: int) -> CommunityActionResult:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM trade_offers WHERE id = ?",
            (offer_id,),
        ).fetchone()
        if row is None:
            return CommunityActionResult(False, "Обмен не найден", "Предложение уже отсутствует на рынке.")

        connection.execute("DELETE FROM trade_offers WHERE id = ?", (offer_id,))
        connection.commit()

    return CommunityActionResult(True, "Обмен удалён", "Предложение полностью убрано из рынка обменов.")


async def get_clans_page(page: int = 1, per_page: int = COMMUNITY_PER_PAGE, search: str | None = None, include_inactive: bool = False) -> ClansPage:
    clean_search = clean_search_query(search)
    filters = [] if include_inactive else ["clans.active = 1"]
    params: list[object] = []
    if clean_search:
        filters.append("(clans.name LIKE ? OR clans.description LIKE ?)")
        params.extend([f"%{clean_search}%", f"%{clean_search}%"])
    where_sql = "WHERE " + " AND ".join(filters) if filters else ""

    with get_connection() as connection:
        total_count = int(connection.execute(
            f"SELECT COUNT(*) AS total_count FROM clans {where_sql}",
            params,
        ).fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT clans.id, clans.name, clans.description, clans.rating_points, clans.wins, clans.active,
                   COUNT(clan_members.id) AS members_count
            FROM clans
            LEFT JOIN clan_members ON clan_members.clan_id = clans.id
            {where_sql}
            GROUP BY clans.id
            ORDER BY clans.rating_points DESC, clans.wins DESC, clans.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return ClansPage(
        clans=[
            ClanListItem(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                rating_points=row["rating_points"],
                wins=row["wins"],
                members_count=row["members_count"],
                active=bool(row["active"]),
            )
            for row in rows
        ],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
    )


async def get_user_clan(user_id: int) -> ClanProfile | None:
    with get_connection() as connection:
        row = connection.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return await get_clan_profile(int(row["clan_id"]), viewer_user_id=user_id)


async def get_clan_profile(clan_id: int, viewer_user_id: int | None = None) -> ClanProfile | None:
    with get_connection() as connection:
        clan_row = connection.execute(
            """
            SELECT clans.id, clans.name, clans.description, clans.rating_points, clans.wins, clans.active,
                   clans.created_by_user_id, users.nickname AS created_by_nickname,
                   COUNT(cm.id) AS members_count
            FROM clans
            LEFT JOIN users ON users.id = clans.created_by_user_id
            LEFT JOIN clan_members cm ON cm.clan_id = clans.id
            WHERE clans.id = ?
            GROUP BY clans.id
            """,
            (clan_id,),
        ).fetchone()
        if clan_row is None:
            return None

        role_row = None
        if viewer_user_id is not None:
            role_row = connection.execute(
                "SELECT role FROM clan_members WHERE clan_id = ? AND user_id = ?",
                (clan_id, viewer_user_id),
            ).fetchone()

        member_rows = connection.execute(
            """
            SELECT clan_members.user_id, users.nickname, clan_members.role, clan_members.joined_at
            FROM clan_members
            JOIN users ON users.id = clan_members.user_id
            WHERE clan_members.clan_id = ?
            ORDER BY
                CASE clan_members.role
                    WHEN 'leader' THEN 1
                    WHEN 'officer' THEN 2
                    ELSE 3
                END,
                users.nickname
            LIMIT 10
            """,
            (clan_id,),
        ).fetchall()

    return ClanProfile(
        id=clan_row["id"],
        name=clan_row["name"],
        description=clan_row["description"],
        rating_points=clan_row["rating_points"],
        wins=clan_row["wins"],
        active=bool(clan_row["active"]),
        created_by_user_id=clan_row["created_by_user_id"],
        created_by_nickname=clan_row["created_by_nickname"],
        members_count=clan_row["members_count"],
        viewer_role=role_row["role"] if role_row else None,
        members=[
            ClanMemberItem(
                user_id=row["user_id"],
                nickname=row["nickname"],
                role=row["role"],
                joined_at=row["joined_at"],
            )
            for row in member_rows
        ],
    )


async def create_clan(user_id: int, name: str, description: str) -> CommunityActionResult:
    clean_name = " ".join(name.strip().split())
    clean_description = " ".join(description.strip().split())
    if len(clean_name) < 3 or len(clean_name) > 32:
        return CommunityActionResult(False, "Клан не создан", "Название должно быть от 3 до 32 символов.")
    if len(clean_description) > 300:
        return CommunityActionResult(False, "Клан не создан", "Описание должно быть до 300 символов.")

    with get_connection() as connection:
        existing_member = connection.execute("SELECT id FROM clan_members WHERE user_id = ?", (user_id,)).fetchone()
        if existing_member:
            return CommunityActionResult(False, "Клан не создан", "Ты уже состоишь в клане.")
        existing_name = connection.execute("SELECT id FROM clans WHERE LOWER(name) = LOWER(?)", (clean_name,)).fetchone()
        if existing_name:
            return CommunityActionResult(False, "Клан не создан", "Клан с таким названием уже есть.")
        cursor = connection.execute(
            "INSERT INTO clans (name, description, created_by_user_id) VALUES (?, ?, ?)",
            (clean_name, clean_description, user_id),
        )
        clan_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, 'leader')",
            (clan_id, user_id),
        )
        connection.commit()
    return CommunityActionResult(True, "Клан создан", "Новая команда уже ждёт игроков.")


async def join_clan(user_id: int, clan_id: int) -> CommunityActionResult:
    """Создаёт заявку на вступление. Игрок попадает в клан только после одобрения президента."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_member = connection.execute("SELECT id FROM clan_members WHERE user_id = ?", (user_id,)).fetchone()
        if existing_member:
            connection.rollback()
            return CommunityActionResult(False, "Вступление недоступно", "Сначала нужно выйти из текущего клана.")
        clan = connection.execute("SELECT id FROM clans WHERE id = ? AND active = 1", (clan_id,)).fetchone()
        if clan is None:
            connection.rollback()
            return CommunityActionResult(False, "Клан недоступен", "Клан закрыт или уже расформирован.")
        members_count = int(connection.execute(
            "SELECT COUNT(*) AS total_count FROM clan_members WHERE clan_id = ?",
            (clan_id,),
        ).fetchone()["total_count"])
        if members_count >= CLAN_MAX_MEMBERS:
            connection.rollback()
            return CommunityActionResult(False, "Клан заполнен", f"В клане уже {CLAN_MAX_MEMBERS} игроков — это максимум. Попробуй другой клан.")

        pending = connection.execute(
            "SELECT id FROM clan_join_requests WHERE clan_id = ? AND user_id = ? AND status = 'pending'",
            (clan_id, user_id),
        ).fetchone()
        if pending is not None:
            connection.rollback()
            return CommunityActionResult(False, "Заявка уже отправлена", "Твоя заявка на рассмотрении у президента клана.")

        connection.execute(
            "INSERT INTO clan_join_requests (clan_id, user_id, status) VALUES (?, ?, 'pending')",
            (clan_id, user_id),
        )
        connection.commit()
    return CommunityActionResult(True, "Заявка отправлена", "Президент клана рассмотрит её. Придёт уведомление о решении.")


async def get_clan_leaders_telegram_ids(clan_id: int) -> list[int]:
    """Telegram-id президента и вице (кому слать уведомление о заявке)."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT users.telegram_id
            FROM clan_members
            JOIN users ON users.id = clan_members.user_id
            WHERE clan_members.clan_id = ? AND clan_members.role IN ('leader', 'officer')
              AND users.is_banned = 0
            """,
            (clan_id,),
        ).fetchall()
    return [int(row["telegram_id"]) for row in rows]


async def get_pending_requests(clan_id: int) -> list:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT r.id, r.user_id, u.nickname, u.telegram_id
            FROM clan_join_requests r
            JOIN users u ON u.id = r.user_id
            WHERE r.clan_id = ? AND r.status = 'pending'
            ORDER BY r.created_at
            """,
            (clan_id,),
        ).fetchall()
    return [dict(row) for row in rows]


async def count_pending_requests(clan_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM clan_join_requests WHERE clan_id = ? AND status = 'pending'",
            (clan_id,),
        ).fetchone()
    return int(row["n"])


async def resolve_join_request(actor_user_id: int, request_id: int, approve: bool) -> tuple[CommunityActionResult, int | None]:
    """Одобряет/отклоняет заявку. Возвращает (результат, telegram_id заявителя для уведомления)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        actor = connection.execute(
            "SELECT clan_id, role FROM clan_members WHERE user_id = ?",
            (actor_user_id,),
        ).fetchone()
        if actor is None or actor["role"] not in ("leader", "officer"):
            connection.rollback()
            return CommunityActionResult(False, "Нет прав", "Рассматривать заявки могут президент и вице-президент."), None

        request = connection.execute(
            "SELECT id, clan_id, user_id, status FROM clan_join_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if request is None or request["status"] != "pending":
            connection.rollback()
            return CommunityActionResult(False, "Заявка недоступна", "Эта заявка уже обработана."), None
        if int(request["clan_id"]) != int(actor["clan_id"]):
            connection.rollback()
            return CommunityActionResult(False, "Чужая заявка", "Эта заявка относится к другому клану."), None

        applicant_id = int(request["user_id"])
        applicant_row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (applicant_id,)).fetchone()
        applicant_tg = int(applicant_row["telegram_id"]) if applicant_row else None

        if not approve:
            connection.execute(
                "UPDATE clan_join_requests SET status = 'rejected', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                (request_id,),
            )
            connection.commit()
            return CommunityActionResult(True, "Заявка отклонена", "Игрок получит уведомление."), applicant_tg

        # одобрение: проверяем, что игрок ещё не в клане и есть место
        already = connection.execute("SELECT id FROM clan_members WHERE user_id = ?", (applicant_id,)).fetchone()
        if already is not None:
            connection.execute(
                "UPDATE clan_join_requests SET status = 'rejected', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                (request_id,),
            )
            connection.commit()
            return CommunityActionResult(False, "Игрок уже в клане", "Заявка закрыта."), None

        members_count = int(connection.execute(
            "SELECT COUNT(*) AS n FROM clan_members WHERE clan_id = ?",
            (int(actor["clan_id"]),),
        ).fetchone()["n"])
        if members_count >= CLAN_MAX_MEMBERS:
            connection.rollback()
            return CommunityActionResult(False, "Клан заполнен", f"В клане уже {CLAN_MAX_MEMBERS} игроков."), None

        connection.execute(
            "INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, 'member')",
            (int(actor["clan_id"]), applicant_id),
        )
        connection.execute(
            "UPDATE clan_join_requests SET status = 'approved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
            (request_id,),
        )
        # прочие ожидающие заявки этого игрока отклоняем
        connection.execute(
            "UPDATE clan_join_requests SET status = 'rejected', resolved_at = CURRENT_TIMESTAMP WHERE user_id = ? AND status = 'pending'",
            (applicant_id,),
        )
        connection.commit()
        return CommunityActionResult(True, "Игрок принят", "Он получит уведомление о вступлении."), applicant_tg


async def leave_clan(user_id: int) -> CommunityActionResult:
    with get_connection() as connection:
        member = connection.execute("SELECT clan_id, role FROM clan_members WHERE user_id = ?", (user_id,)).fetchone()
        if member is None:
            return CommunityActionResult(False, "Клана нет", "Ты сейчас не состоишь в клане.")
        if member["role"] == "leader":
            members_count = int(connection.execute(
                "SELECT COUNT(*) AS total_count FROM clan_members WHERE clan_id = ?",
                (member["clan_id"],),
            ).fetchone()["total_count"])
            if members_count > 1:
                return CommunityActionResult(False, "Выход недоступен", "Лидер может выйти только после удаления остальных участников.")
            connection.execute("DELETE FROM clans WHERE id = ?", (member["clan_id"],))
        else:
            connection.execute("DELETE FROM clan_members WHERE user_id = ?", (user_id,))
        connection.commit()
    return CommunityActionResult(True, "Клан покинут", "Теперь можно вступить в другую команду.")


def get_clan_member_row(connection, user_id: int):
    return connection.execute(
        "SELECT clan_id, role FROM clan_members WHERE user_id = ?",
        (user_id,),
    ).fetchone()


async def kick_clan_member(actor_user_id: int, target_user_id: int) -> CommunityActionResult:
    if actor_user_id == target_user_id:
        return CommunityActionResult(False, "Действие недоступно", "Себя выгнать нельзя — используй выход из клана.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        actor = get_clan_member_row(connection, actor_user_id)
        target = get_clan_member_row(connection, target_user_id)

        if actor is None or actor["role"] not in ("leader", "officer"):
            connection.rollback()
            return CommunityActionResult(False, "Нет прав", "Исключать игроков могут только президент и вице-президент.")
        if target is None or int(target["clan_id"]) != int(actor["clan_id"]):
            connection.rollback()
            return CommunityActionResult(False, "Игрок не найден", "Этот игрок уже не состоит в вашем клане.")
        if target["role"] == "leader":
            connection.rollback()
            return CommunityActionResult(False, "Нет прав", "Президента клана исключить нельзя.")
        if actor["role"] == "officer" and target["role"] == "officer":
            connection.rollback()
            return CommunityActionResult(False, "Нет прав", "Вице-президент может исключать только обычных участников.")

        connection.execute("DELETE FROM clan_members WHERE user_id = ?", (target_user_id,))
        connection.commit()

    return CommunityActionResult(True, "Игрок исключён", "Место в клане освободилось.")


async def toggle_clan_vice(actor_user_id: int, target_user_id: int) -> CommunityActionResult:
    if actor_user_id == target_user_id:
        return CommunityActionResult(False, "Действие недоступно", "Президент не может назначить вице-президентом себя.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        actor = get_clan_member_row(connection, actor_user_id)
        target = get_clan_member_row(connection, target_user_id)

        if actor is None or actor["role"] != "leader":
            connection.rollback()
            return CommunityActionResult(False, "Нет прав", "Назначать вице-президента может только президент клана.")
        if target is None or int(target["clan_id"]) != int(actor["clan_id"]):
            connection.rollback()
            return CommunityActionResult(False, "Игрок не найден", "Этот игрок уже не состоит в вашем клане.")

        if target["role"] == "officer":
            connection.execute(
                "UPDATE clan_members SET role = 'member' WHERE user_id = ?",
                (target_user_id,),
            )
            connection.commit()
            return CommunityActionResult(True, "Роль снята", "Игрок снова обычный участник клана.")

        # Вице-президент в клане один: прежнего понижаем до участника.
        connection.execute(
            "UPDATE clan_members SET role = 'member' WHERE clan_id = ? AND role = 'officer'",
            (actor["clan_id"],),
        )
        connection.execute(
            "UPDATE clan_members SET role = 'officer' WHERE user_id = ?",
            (target_user_id,),
        )
        connection.commit()

    return CommunityActionResult(True, "Вице-президент назначен", "Теперь у клана есть правая рука президента.")


async def get_clan_member_row_public(user_id: int):
    with get_connection() as connection:
        row = connection.execute("SELECT nickname FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


async def get_clan_member_telegram_id(user_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"]) if row else None


async def toggle_clan_active(clan_id: int) -> CommunityActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT active FROM clans WHERE id = ?", (clan_id,)).fetchone()
        if row is None:
            return CommunityActionResult(False, "Клан не найден", "Клан уже удалён.")
        new_value = 0 if int(row["active"]) == 1 else 1
        connection.execute("UPDATE clans SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_value, clan_id))
        connection.commit()
    return CommunityActionResult(True, "Клан обновлён", "Статус клана изменён.")


async def delete_clan(clan_id: int) -> CommunityActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM clans WHERE id = ?", (clan_id,)).fetchone()
        if row is None:
            return CommunityActionResult(False, "Клан не найден", "Клан уже удалён.")
        connection.execute("DELETE FROM clans WHERE id = ?", (clan_id,))
        connection.commit()
    return CommunityActionResult(True, "Клан расформирован", "Участники больше не состоят в этом клане.")
