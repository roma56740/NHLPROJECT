from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.currencies import CurrencyBalance, ensure_user_balances, get_user_balances
from app.services.packs import count_user_packs
from app.services.user_cards import count_user_cards
from app.services.hockey_pass import get_active_pass_row


@dataclass(frozen=True)
class AdminUserListItem:
    id: int
    telegram_id: int
    username: str | None
    nickname: str
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    premium_pass: bool
    is_banned: bool


@dataclass(frozen=True)
class AdminUserProfile:
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    nickname: str
    role: str
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    goals_scored: int
    goals_allowed: int
    bp_points: int
    hockey_pass_level: int
    premium_pass: bool
    hockey_pass_title: str | None
    hockey_pass_premium_unlocked: bool
    team_name: str | None
    team_country: str | None
    team_logo_path: str | None
    privacy_public_cards: bool
    is_banned: bool
    trade_blocked: bool
    cards_count: int
    packs_count: int
    balances: list[CurrencyBalance]


@dataclass(frozen=True)
class AdminUsersPage:
    users: list[AdminUserListItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


LEAGUES = {"NCAA", "AHL", "NHL", "OLYMPICS"}
CURRENCY_CODES = {"coins", "energy", "rank_point"}


def clean_search_query(value: str | None) -> str | None:
    if value is None:
        return None

    clean_value = " ".join(value.strip().split())
    return clean_value or None


def build_search_filter(search: str | None) -> tuple[str, list[object]]:
    clean_search = clean_search_query(search)

    if clean_search is None:
        return "", []

    if clean_search.isdigit():
        return "WHERE telegram_id = ? OR id = ? OR nickname LIKE ? OR username LIKE ?", [
            int(clean_search),
            int(clean_search),
            f"%{clean_search}%",
            f"%{clean_search}%",
        ]

    return "WHERE nickname LIKE ? OR username LIKE ? OR first_name LIKE ? OR last_name LIKE ?", [
        f"%{clean_search}%",
        f"%{clean_search}%",
        f"%{clean_search}%",
        f"%{clean_search}%",
    ]


async def get_users_page(page: int = 1, per_page: int = 5, search: str | None = None) -> AdminUsersPage:
    clean_search = clean_search_query(search)
    where_sql, params = build_search_filter(clean_search)

    with get_connection() as connection:
        count_cursor = connection.execute(
            f"SELECT COUNT(*) AS total_count FROM users {where_sql}",
            params,
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                id,
                telegram_id,
                username,
                nickname,
                league,
                rating_points,
                wins,
                losses,
                matches_played,
                premium_pass,
                is_banned
            FROM users
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    users = [
        AdminUserListItem(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            nickname=row["nickname"],
            league=row["league"],
            rating_points=row["rating_points"],
            wins=row["wins"],
            losses=row["losses"],
            matches_played=row["matches_played"],
            premium_pass=bool(row["premium_pass"]),
            is_banned=bool(row["is_banned"]),
        )
        for row in rows
    ]

    return AdminUsersPage(
        users=users,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
    )


async def get_admin_user_profile(user_id: int) -> AdminUserProfile | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                id,
                telegram_id,
                username,
                first_name,
                last_name,
                nickname,
                role,
                league,
                rating_points,
                wins,
                losses,
                matches_played,
                goals_scored,
                goals_allowed,
                bp_points,
                hockey_pass_level,
                premium_pass,
                team_name,
                team_country,
                team_logo_path,
                privacy_public_cards,
                is_banned,
                trade_blocked
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    await ensure_user_balances(row["id"], is_new_player=False)
    balances = await get_user_balances(row["id"])
    cards_count = await count_user_cards(row["id"])
    packs_count = await count_user_packs(row["id"])
    hockey_pass_title, hockey_pass_premium_unlocked = await get_admin_user_hockey_pass_state(row["id"])

    return AdminUserProfile(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        nickname=row["nickname"],
        role=row["role"],
        league=row["league"],
        rating_points=row["rating_points"],
        wins=row["wins"],
        losses=row["losses"],
        matches_played=row["matches_played"],
        goals_scored=row["goals_scored"],
        goals_allowed=row["goals_allowed"],
        bp_points=row["bp_points"],
        hockey_pass_level=row["hockey_pass_level"],
        premium_pass=bool(row["premium_pass"]),
        hockey_pass_title=hockey_pass_title,
        hockey_pass_premium_unlocked=hockey_pass_premium_unlocked,
        team_name=row["team_name"],
        team_country=row["team_country"],
        team_logo_path=row["team_logo_path"],
        privacy_public_cards=bool(row["privacy_public_cards"]),
        is_banned=bool(row["is_banned"]),
        trade_blocked=bool(row["trade_blocked"]),
        cards_count=cards_count,
        packs_count=packs_count,
        balances=balances,
    )


async def add_currency_to_user(user_id: int, currency_code: str, amount: int) -> AdminUserProfile | None:
    if currency_code not in CURRENCY_CODES:
        return None

    await ensure_user_balances(user_id, is_new_player=False)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE currency_balances
            SET
                amount = MAX(0, amount + ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND currency_code = ?
            """,
            (amount, user_id, currency_code),
        )
        connection.commit()

    return await get_admin_user_profile(user_id)


async def update_user_league(user_id: int, league: str) -> AdminUserProfile | None:
    if league not in LEAGUES:
        return None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                league = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (league, user_id),
        )
        connection.commit()

    return await get_admin_user_profile(user_id)


async def get_admin_user_hockey_pass_state(user_id: int) -> tuple[str | None, bool]:
    with get_connection() as connection:
        pass_row = await get_active_pass_row(connection)

        if pass_row is None:
            return None, False

        connection.execute(
            """
            INSERT INTO user_hockey_passes (user_id, pass_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, pass_id) DO NOTHING
            """,
            (user_id, pass_row["id"]),
        )
        user_pass_row = connection.execute(
            """
            SELECT premium_unlocked
            FROM user_hockey_passes
            WHERE user_id = ? AND pass_id = ?
            """,
            (user_id, pass_row["id"]),
        ).fetchone()
        connection.commit()

    return pass_row["title"], bool(user_pass_row and user_pass_row["premium_unlocked"])


async def toggle_user_premium_pass(user_id: int) -> AdminUserProfile | None:
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        return None

    with get_connection() as connection:
        pass_row = await get_active_pass_row(connection)

        if pass_row is None:
            return profile

        connection.execute(
            """
            INSERT INTO user_hockey_passes (user_id, pass_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, pass_id) DO NOTHING
            """,
            (user_id, pass_row["id"]),
        )
        user_pass_row = connection.execute(
            """
            SELECT premium_unlocked
            FROM user_hockey_passes
            WHERE user_id = ? AND pass_id = ?
            """,
            (user_id, pass_row["id"]),
        ).fetchone()
        new_value = 0 if bool(user_pass_row and user_pass_row["premium_unlocked"]) else 1
        connection.execute(
            """
            UPDATE user_hockey_passes
            SET
                premium_unlocked = ?,
                purchased_at = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE purchased_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND pass_id = ?
            """,
            (new_value, new_value, user_id, pass_row["id"]),
        )
        connection.execute(
            """
            UPDATE users
            SET
                premium_pass = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_value, user_id),
        )
        connection.commit()

    return await get_admin_user_profile(user_id)


async def toggle_user_trade_block(user_id: int) -> AdminUserProfile | None:
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        return None

    new_value = 0 if profile.trade_blocked else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                trade_blocked = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_value, user_id),
        )
        connection.commit()

    return await get_admin_user_profile(user_id)


async def toggle_user_ban(user_id: int) -> AdminUserProfile | None:
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        return None

    new_value = 0 if profile.is_banned else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                is_banned = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_value, user_id),
        )
        connection.commit()

    return await get_admin_user_profile(user_id)
