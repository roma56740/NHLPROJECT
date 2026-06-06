from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection


@dataclass(frozen=True)
class SecuritySummary:
    banned_users_count: int
    locked_cards_count: int
    open_trades_count: int
    logs_count: int


@dataclass(frozen=True)
class SecurityLogItem:
    id: int
    user_id: int | None
    telegram_id: int | None
    action: str
    details: str
    created_at: str


@dataclass(frozen=True)
class SecurityLogsPage:
    logs: list[SecurityLogItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class SecurityUserItem:
    id: int
    telegram_id: int
    nickname: str
    username: str | None
    league: str
    is_banned: bool
    locked_cards_count: int


@dataclass(frozen=True)
class SecurityUsersPage:
    users: list[SecurityUserItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None = None


@dataclass(frozen=True)
class SecurityUserProfile:
    id: int
    telegram_id: int
    nickname: str
    username: str | None
    league: str
    rating_points: int
    matches_played: int
    is_banned: bool
    cards_count: int
    locked_cards_count: int
    open_trades_count: int


@dataclass(frozen=True)
class SecurityCardItem:
    user_card_id: int
    card_id: int
    name: str
    position: str
    overall: int
    rarity: str
    collection_name: str
    is_in_lineup: bool
    trade_locked: bool
    lock_reason: str | None
    lock_until: str | None


@dataclass(frozen=True)
class SecurityCardsPage:
    cards: list[SecurityCardItem]
    page: int
    pages_count: int
    total_count: int


async def add_security_log(
    *,
    action: str,
    details: str = "",
    user_id: int | None = None,
    telegram_id: int | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO security_logs (user_id, telegram_id, action, details)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, telegram_id, action, details),
        )
        connection.commit()


async def get_security_summary() -> SecuritySummary:
    with get_connection() as connection:
        banned_users_count = connection.execute(
            "SELECT COUNT(*) AS count FROM users WHERE is_banned = 1"
        ).fetchone()["count"]
        locked_cards_count = connection.execute(
            "SELECT COUNT(*) AS count FROM user_cards WHERE trade_locked = 1"
        ).fetchone()["count"]
        open_trades_count = connection.execute(
            "SELECT COUNT(*) AS count FROM trade_offers WHERE status = 'open'"
        ).fetchone()["count"]
        logs_count = connection.execute(
            "SELECT COUNT(*) AS count FROM security_logs"
        ).fetchone()["count"]

    return SecuritySummary(
        banned_users_count=banned_users_count,
        locked_cards_count=locked_cards_count,
        open_trades_count=open_trades_count,
        logs_count=logs_count,
    )


async def get_security_logs_page(page: int, per_page: int) -> SecurityLogsPage:
    safe_page = max(page, 1)

    with get_connection() as connection:
        total_count = connection.execute("SELECT COUNT(*) AS count FROM security_logs").fetchone()["count"]
        pages_count = max(ceil(total_count / per_page), 1)
        safe_page = min(safe_page, pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT id, user_id, telegram_id, action, details, created_at
            FROM security_logs
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        )
        rows = cursor.fetchall()

    logs = [
        SecurityLogItem(
            id=row["id"],
            user_id=row["user_id"],
            telegram_id=row["telegram_id"],
            action=row["action"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return SecurityLogsPage(logs=logs, page=safe_page, pages_count=pages_count, total_count=total_count)


async def get_security_users_page(page: int, per_page: int, search: str | None = None) -> SecurityUsersPage:
    safe_page = max(page, 1)
    where_sql = ""
    params: list[object] = []

    if search:
        like = f"%{search.strip()}%"
        where_sql = """
        WHERE CAST(u.id AS TEXT) LIKE ?
           OR CAST(u.telegram_id AS TEXT) LIKE ?
           OR u.nickname LIKE ?
           OR COALESCE(u.username, '') LIKE ?
           OR COALESCE(u.first_name, '') LIKE ?
           OR COALESCE(u.last_name, '') LIKE ?
        """
        params.extend([like, like, like, like, like, like])

    with get_connection() as connection:
        total_count = connection.execute(
            f"SELECT COUNT(*) AS count FROM users u {where_sql}",
            params,
        ).fetchone()["count"]
        pages_count = max(ceil(total_count / per_page), 1)
        safe_page = min(safe_page, pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                u.id,
                u.telegram_id,
                u.nickname,
                u.username,
                u.league,
                u.is_banned,
                COALESCE(SUM(CASE WHEN uc.trade_locked = 1 THEN 1 ELSE 0 END), 0) AS locked_cards_count
            FROM users u
            LEFT JOIN user_cards uc ON uc.user_id = u.id
            {where_sql}
            GROUP BY u.id
            ORDER BY u.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    users = [
        SecurityUserItem(
            id=row["id"],
            telegram_id=row["telegram_id"],
            nickname=row["nickname"],
            username=row["username"],
            league=row["league"],
            is_banned=bool(row["is_banned"]),
            locked_cards_count=row["locked_cards_count"],
        )
        for row in rows
    ]

    return SecurityUsersPage(
        users=users,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=search,
    )


async def get_security_user_profile(user_id: int) -> SecurityUserProfile | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                u.id,
                u.telegram_id,
                u.nickname,
                u.username,
                u.league,
                u.rating_points,
                u.matches_played,
                u.is_banned,
                COUNT(DISTINCT uc.id) AS cards_count,
                COALESCE(SUM(CASE WHEN uc.trade_locked = 1 THEN 1 ELSE 0 END), 0) AS locked_cards_count,
                (
                    SELECT COUNT(*)
                    FROM trade_offers t
                    WHERE t.creator_user_id = u.id AND t.status = 'open'
                ) AS open_trades_count
            FROM users u
            LEFT JOIN user_cards uc ON uc.user_id = u.id
            WHERE u.id = ?
            GROUP BY u.id
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return None

    return SecurityUserProfile(
        id=row["id"],
        telegram_id=row["telegram_id"],
        nickname=row["nickname"],
        username=row["username"],
        league=row["league"],
        rating_points=row["rating_points"],
        matches_played=row["matches_played"],
        is_banned=bool(row["is_banned"]),
        cards_count=row["cards_count"],
        locked_cards_count=row["locked_cards_count"],
        open_trades_count=row["open_trades_count"],
    )


async def toggle_security_user_ban(user_id: int, admin_telegram_id: int) -> bool | None:
    profile = await get_security_user_profile(user_id)

    if profile is None:
        return None

    new_value = 0 if profile.is_banned else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET is_banned = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_value, user_id),
        )
        connection.commit()

    await add_security_log(
        user_id=user_id,
        telegram_id=profile.telegram_id,
        action="Блокировка игрока" if new_value else "Снятие блокировки",
        details=f"Решение администратора {admin_telegram_id}",
    )
    return bool(new_value)


async def get_security_user_cards_page(user_id: int, page: int, per_page: int) -> SecurityCardsPage:
    safe_page = max(page, 1)

    with get_connection() as connection:
        total_count = connection.execute(
            "SELECT COUNT(*) AS count FROM user_cards WHERE user_id = ?",
            (user_id,),
        ).fetchone()["count"]
        pages_count = max(ceil(total_count / per_page), 1)
        safe_page = min(safe_page, pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                uc.id AS user_card_id,
                c.id AS card_id,
                c.name,
                c.position,
                c.overall,
                c.rarity,
                co.name AS collection_name,
                uc.is_in_lineup,
                uc.trade_locked,
                uc.lock_reason,
                uc.lock_until
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            JOIN collections co ON co.id = c.collection_id
            WHERE uc.user_id = ?
            ORDER BY uc.trade_locked DESC, c.overall DESC, uc.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, offset),
        )
        rows = cursor.fetchall()

    cards = [
        SecurityCardItem(
            user_card_id=row["user_card_id"],
            card_id=row["card_id"],
            name=row["name"],
            position=row["position"],
            overall=row["overall"],
            rarity=row["rarity"],
            collection_name=row["collection_name"],
            is_in_lineup=bool(row["is_in_lineup"]),
            trade_locked=bool(row["trade_locked"]),
            lock_reason=row["lock_reason"],
            lock_until=row["lock_until"],
        )
        for row in rows
    ]

    return SecurityCardsPage(cards=cards, page=safe_page, pages_count=pages_count, total_count=total_count)


async def get_security_card_owner(user_card_id: int) -> tuple[int, int, str] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT u.id AS user_id, u.telegram_id, c.name
            FROM user_cards uc
            JOIN users u ON u.id = uc.user_id
            JOIN cards c ON c.id = uc.card_id
            WHERE uc.id = ?
            """,
            (user_card_id,),
        ).fetchone()

    if row is None:
        return None

    return row["user_id"], row["telegram_id"], row["name"]


async def lock_user_card_trade(user_card_id: int, reason: str, admin_telegram_id: int) -> int | None:
    owner = await get_security_card_owner(user_card_id)

    if owner is None:
        return None

    user_id, telegram_id, card_name = owner

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_cards
            SET trade_locked = 1,
                lock_reason = ?,
                lock_until = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (reason, user_card_id),
        )
        connection.commit()

    await add_security_log(
        user_id=user_id,
        telegram_id=telegram_id,
        action="Trade Lock карточки",
        details=f"{card_name}: {reason}. Администратор {admin_telegram_id}",
    )
    return user_id


async def unlock_user_card_trade(user_card_id: int, admin_telegram_id: int) -> int | None:
    owner = await get_security_card_owner(user_card_id)

    if owner is None:
        return None

    user_id, telegram_id, card_name = owner

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE user_cards
            SET trade_locked = 0,
                lock_reason = NULL,
                lock_until = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user_card_id,),
        )
        connection.commit()

    await add_security_log(
        user_id=user_id,
        telegram_id=telegram_id,
        action="Trade Lock снят",
        details=f"{card_name}. Администратор {admin_telegram_id}",
    )
    return user_id
