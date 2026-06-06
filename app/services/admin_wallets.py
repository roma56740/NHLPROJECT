from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.currencies import CurrencyBalance, ensure_user_balances, get_user_balances


WALLET_CURRENCY_CODES = ("coins", "energy", "rank_point")


@dataclass(frozen=True)
class WalletUserListItem:
    id: int
    telegram_id: int
    username: str | None
    nickname: str
    league: str
    is_banned: bool


@dataclass(frozen=True)
class WalletUsersPage:
    users: list[WalletUserListItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


@dataclass(frozen=True)
class WalletUserProfile:
    id: int
    telegram_id: int
    username: str | None
    nickname: str
    league: str
    is_banned: bool
    balances: list[CurrencyBalance]


@dataclass(frozen=True)
class WalletCurrency:
    code: str
    name: str
    icon: str
    description: str


@dataclass(frozen=True)
class WalletOperationResult:
    profile: WalletUserProfile
    currency: WalletCurrency
    amount: int
    action: str


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


async def get_wallet_users_page(page: int = 1, per_page: int = 5, search: str | None = None) -> WalletUsersPage:
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
                is_banned
            FROM users
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    return WalletUsersPage(
        users=[
            WalletUserListItem(
                id=row["id"],
                telegram_id=row["telegram_id"],
                username=row["username"],
                nickname=row["nickname"],
                league=row["league"],
                is_banned=bool(row["is_banned"]),
            )
            for row in rows
        ],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        search=clean_search,
    )


async def get_wallet_user_profile(user_id: int) -> WalletUserProfile | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                telegram_id,
                username,
                nickname,
                league,
                is_banned
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return None

    await ensure_user_balances(row["id"], is_new_player=False)
    balances = await get_user_balances(row["id"])

    return WalletUserProfile(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        nickname=row["nickname"],
        league=row["league"],
        is_banned=bool(row["is_banned"]),
        balances=balances,
    )


async def get_wallet_currencies() -> list[WalletCurrency]:
    placeholders = ", ".join("?" for _ in WALLET_CURRENCY_CODES)

    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            SELECT code, name, icon, description
            FROM currencies
            WHERE active = 1 AND code IN ({placeholders})
            ORDER BY
                CASE code
                    WHEN 'coins' THEN 1
                    WHEN 'energy' THEN 2
                    WHEN 'rank_point' THEN 3
                    ELSE 99
                END
            """,
            WALLET_CURRENCY_CODES,
        )
        rows = cursor.fetchall()

    return [
        WalletCurrency(
            code=row["code"],
            name=row["name"],
            icon=row["icon"],
            description=row["description"],
        )
        for row in rows
    ]


async def get_wallet_currency(currency_code: str) -> WalletCurrency | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT code, name, icon, description
            FROM currencies
            WHERE code = ? AND active = 1
            """,
            (currency_code,),
        ).fetchone()

    if row is None:
        return None

    if row["code"] not in WALLET_CURRENCY_CODES:
        return None

    return WalletCurrency(
        code=row["code"],
        name=row["name"],
        icon=row["icon"],
        description=row["description"],
    )


async def change_wallet_balance(user_id: int, currency_code: str, amount: int, action: str) -> WalletOperationResult | None:
    if action not in {"add", "remove"}:
        return None

    if amount <= 0:
        return None

    currency = await get_wallet_currency(currency_code)

    if currency is None:
        return None

    await ensure_user_balances(user_id, is_new_player=False)
    signed_amount = amount if action == "add" else -amount

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE currency_balances
            SET
                amount = MAX(0, amount + ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND currency_code = ?
            """,
            (signed_amount, user_id, currency_code),
        )
        connection.commit()

    profile = await get_wallet_user_profile(user_id)

    if profile is None:
        return None

    return WalletOperationResult(
        profile=profile,
        currency=currency,
        amount=amount,
        action=action,
    )
