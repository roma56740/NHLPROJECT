from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from zoneinfo import ZoneInfo

from app.database.db import get_connection
from app.services.user_cards import give_card_to_user
from app.services.packs import give_pack_to_user


MOSCOW_TZ = ZoneInfo("Europe/Moscow")
LEVELS_COUNT = 40
POINTS_PER_LEVEL = 5
PER_PAGE = 5

TRACK_TITLES = {
    "free": "Free",
    "premium": "Premium",
}

REWARD_TYPE_TITLES = {
    "currency": "Валюта",
    "pack": "Пак",
    "card": "Карточка",
}


@dataclass(frozen=True)
class HockeyPassDraft:
    title: str
    description: str
    end_at: str
    premium_currency_code: str | None
    premium_price_amount: int


@dataclass(frozen=True)
class HockeyPassListItem:
    id: int
    title: str
    end_at: str
    premium_currency_code: str | None
    premium_price_amount: int
    active: bool
    rewards_count: int


@dataclass(frozen=True)
class HockeyPassPage:
    items: list[HockeyPassListItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class HockeyPassProfile:
    id: int
    title: str
    description: str
    start_at: str
    end_at: str
    premium_currency_code: str | None
    premium_currency_name: str | None
    premium_currency_icon: str | None
    premium_price_amount: int
    levels_count: int
    points_per_level: int
    active: bool
    rewards_count: int
    users_count: int
    premium_users_count: int
    is_finished: bool


@dataclass(frozen=True)
class UserHockeyPassInfo:
    pass_id: int | None
    title: str
    description: str
    end_at: str | None
    bp_points: int
    level: int
    levels_count: int
    points_per_level: int
    points_to_next: int
    premium_unlocked: bool
    premium_currency_code: str | None
    premium_currency_name: str | None
    premium_currency_icon: str | None
    premium_price_amount: int
    free_total: int
    free_claimed: int
    premium_total: int
    premium_claimed: int
    is_finished: bool


@dataclass(frozen=True)
class HockeyPassRewardItem:
    id: int
    pass_id: int
    level: int
    track: str
    reward_type: str
    title: str
    amount: int
    currency_code: str | None
    currency_name: str | None
    currency_icon: str | None
    pack_id: int | None
    pack_name: str | None
    pack_image_path: str | None
    card_id: int | None
    card_name: str | None
    card_image_path: str | None
    card_position: str | None
    card_overall: int | None
    active: bool
    claimed: bool
    available: bool
    locked_reason: str | None


@dataclass(frozen=True)
class UserRewardsPage:
    pass_id: int
    items: list[HockeyPassRewardItem]
    page: int
    pages_count: int
    total_count: int
    user_level: int
    premium_unlocked: bool


@dataclass(frozen=True)
class AdminRewardsPage:
    pass_id: int
    pass_title: str
    items: list[HockeyPassRewardItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class RewardDraft:
    pass_id: int
    level: int
    track: str
    reward_type: str
    title: str
    amount: int = 0
    currency_code: str | None = None
    pack_id: int | None = None
    card_id: int | None = None


@dataclass(frozen=True)
class ChoiceItem:
    id: int | str
    title: str
    subtitle: str
    image_path: str | None = None


@dataclass(frozen=True)
class ChoicePage:
    items: list[ChoiceItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


@dataclass(frozen=True)
class ClaimResult:
    reward: HockeyPassRewardItem
    message: str
    image_path: str | None


@dataclass(frozen=True)
class PurchaseResult:
    title: str
    price_text: str
    balance_after: int | None


def now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def to_moscow_iso(value: datetime) -> str:
    return value.astimezone(MOSCOW_TZ).isoformat(timespec="minutes")


def parse_moscow_datetime(value: str) -> str | None:
    clean_value = " ".join(value.strip().split())

    for pattern in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(clean_value, pattern)
            if pattern == "%d.%m.%Y":
                parsed = parsed.replace(hour=23, minute=59)
            return to_moscow_iso(parsed.replace(tzinfo=MOSCOW_TZ))
        except ValueError:
            continue

    return None


def parse_stored_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)

    return parsed.astimezone(MOSCOW_TZ)


def is_pass_finished(end_at: str | None) -> bool:
    parsed = parse_stored_datetime(end_at)
    return bool(parsed and parsed < now_moscow())


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def validate_title(value: str) -> str | None:
    clean = clean_text(value)
    if 3 <= len(clean) <= 80:
        return clean
    return None


def validate_description(value: str) -> str | None:
    clean = clean_text(value)
    if clean == "-":
        return ""
    if len(clean) <= 300:
        return clean
    return None


def parse_positive_int(value: str, min_value: int = 0, max_value: int = 1_000_000_000) -> int | None:
    clean = value.strip().replace(" ", "")
    if not clean.isdigit():
        return None
    number = int(clean)
    if min_value <= number <= max_value:
        return number
    return None


def calculate_level(bp_points: int, levels_count: int = LEVELS_COUNT, points_per_level: int = POINTS_PER_LEVEL) -> int:
    if bp_points <= 0:
        return 1
    return min(levels_count, max(1, bp_points // points_per_level + 1))


def points_to_next_level(bp_points: int, level: int, levels_count: int = LEVELS_COUNT, points_per_level: int = POINTS_PER_LEVEL) -> int:
    if level >= levels_count:
        return 0
    next_level_points = level * points_per_level
    return max(0, next_level_points - bp_points)


def format_price(amount: int, icon: str | None, name: str | None, code: str | None) -> str:
    if amount <= 0:
        return "бесплатно"
    title = name or code or "валюта"
    prefix = icon or "💠"
    return f"{prefix} {amount:,} {title}".replace(",", " ")


async def get_active_pass_row(connection=None):
    own_connection = connection is None
    connection = connection or get_connection()
    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM hockey_passes
            WHERE active = 1
            ORDER BY datetime(end_at) DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None or is_pass_finished(row["end_at"]):
            return None
        return row
    finally:
        if own_connection:
            connection.close()


async def ensure_user_pass(user_id: int, pass_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_hockey_passes (user_id, pass_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, pass_id) DO NOTHING
            """,
            (user_id, pass_id),
        )
        connection.commit()


async def get_user_hockey_pass_info(telegram_id: int) -> UserHockeyPassInfo | None:
    with get_connection() as connection:
        user_cursor = connection.execute(
            """
            SELECT id, bp_points, hockey_pass_level
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        user_row = user_cursor.fetchone()

        if user_row is None:
            return None

        pass_row = await get_active_pass_row(connection)

        if pass_row is None:
            return UserHockeyPassInfo(
                pass_id=None,
                title="Hockey Pass",
                description="",
                end_at=None,
                bp_points=int(user_row["bp_points"] or 0),
                level=int(user_row["hockey_pass_level"] or 1),
                levels_count=LEVELS_COUNT,
                points_per_level=POINTS_PER_LEVEL,
                points_to_next=0,
                premium_unlocked=False,
                premium_currency_code=None,
                premium_currency_name=None,
                premium_currency_icon=None,
                premium_price_amount=0,
                free_total=0,
                free_claimed=0,
                premium_total=0,
                premium_claimed=0,
                is_finished=False,
            )

        connection.execute(
            """
            INSERT INTO user_hockey_passes (user_id, pass_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, pass_id) DO NOTHING
            """,
            (user_row["id"], pass_row["id"]),
        )

        user_pass_cursor = connection.execute(
            """
            SELECT premium_unlocked
            FROM user_hockey_passes
            WHERE user_id = ? AND pass_id = ?
            """,
            (user_row["id"], pass_row["id"]),
        )
        user_pass_row = user_pass_cursor.fetchone()

        rewards_cursor = connection.execute(
            """
            SELECT
                COUNT(CASE WHEN r.track = 'free' THEN 1 END) AS free_total,
                COUNT(CASE WHEN r.track = 'premium' THEN 1 END) AS premium_total,
                COUNT(CASE WHEN r.track = 'free' AND cr.id IS NOT NULL THEN 1 END) AS free_claimed,
                COUNT(CASE WHEN r.track = 'premium' AND cr.id IS NOT NULL THEN 1 END) AS premium_claimed
            FROM hockey_pass_rewards r
            LEFT JOIN user_hockey_pass_rewards cr ON cr.reward_id = r.id AND cr.user_id = ?
            WHERE r.pass_id = ? AND r.active = 1
            """,
            (user_row["id"], pass_row["id"]),
        )
        rewards_row = rewards_cursor.fetchone()

        currency_cursor = connection.execute(
            """
            SELECT name, icon
            FROM currencies
            WHERE code = ?
            """,
            (pass_row["premium_currency_code"],),
        )
        currency_row = currency_cursor.fetchone()
        connection.commit()

    bp_points = int(user_row["bp_points"] or 0)
    levels_count = int(pass_row["levels_count"] or LEVELS_COUNT)
    points_per_level = int(pass_row["points_per_level"] or POINTS_PER_LEVEL)
    level = calculate_level(bp_points, levels_count, points_per_level)

    return UserHockeyPassInfo(
        pass_id=pass_row["id"],
        title=pass_row["title"],
        description=pass_row["description"],
        end_at=pass_row["end_at"],
        bp_points=bp_points,
        level=level,
        levels_count=levels_count,
        points_per_level=points_per_level,
        points_to_next=points_to_next_level(bp_points, level, levels_count, points_per_level),
        premium_unlocked=bool(user_pass_row and user_pass_row["premium_unlocked"]),
        premium_currency_code=pass_row["premium_currency_code"],
        premium_currency_name=currency_row["name"] if currency_row else None,
        premium_currency_icon=currency_row["icon"] if currency_row else None,
        premium_price_amount=int(pass_row["premium_price_amount"] or 0),
        free_total=int(rewards_row["free_total"] or 0),
        free_claimed=int(rewards_row["free_claimed"] or 0),
        premium_total=int(rewards_row["premium_total"] or 0),
        premium_claimed=int(rewards_row["premium_claimed"] or 0),
        is_finished=is_pass_finished(pass_row["end_at"]),
    )


async def get_passes_page(page: int = 1, per_page: int = PER_PAGE) -> HockeyPassPage:
    with get_connection() as connection:
        count_cursor = connection.execute("SELECT COUNT(*) AS total_count FROM hockey_passes")
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                p.id,
                p.title,
                p.end_at,
                p.premium_currency_code,
                p.premium_price_amount,
                p.active,
                COUNT(r.id) AS rewards_count
            FROM hockey_passes p
            LEFT JOIN hockey_pass_rewards r ON r.pass_id = p.id
            GROUP BY p.id
            ORDER BY p.id DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        )
        rows = cursor.fetchall()

    items = [
        HockeyPassListItem(
            id=row["id"],
            title=row["title"],
            end_at=row["end_at"],
            premium_currency_code=row["premium_currency_code"],
            premium_price_amount=int(row["premium_price_amount"] or 0),
            active=bool(row["active"]),
            rewards_count=int(row["rewards_count"] or 0),
        )
        for row in rows
    ]

    return HockeyPassPage(items=items, page=safe_page, pages_count=pages_count, total_count=total_count)


async def get_pass_profile(pass_id: int) -> HockeyPassProfile | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                p.*,
                c.name AS premium_currency_name,
                c.icon AS premium_currency_icon,
                COUNT(DISTINCT r.id) AS rewards_count,
                COUNT(DISTINCT up.user_id) AS users_count,
                COUNT(DISTINCT CASE WHEN up.premium_unlocked = 1 THEN up.user_id END) AS premium_users_count
            FROM hockey_passes p
            LEFT JOIN currencies c ON c.code = p.premium_currency_code
            LEFT JOIN hockey_pass_rewards r ON r.pass_id = p.id
            LEFT JOIN user_hockey_passes up ON up.pass_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (pass_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return HockeyPassProfile(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        premium_currency_code=row["premium_currency_code"],
        premium_currency_name=row["premium_currency_name"],
        premium_currency_icon=row["premium_currency_icon"],
        premium_price_amount=int(row["premium_price_amount"] or 0),
        levels_count=int(row["levels_count"] or LEVELS_COUNT),
        points_per_level=int(row["points_per_level"] or POINTS_PER_LEVEL),
        active=bool(row["active"]),
        rewards_count=int(row["rewards_count"] or 0),
        users_count=int(row["users_count"] or 0),
        premium_users_count=int(row["premium_users_count"] or 0),
        is_finished=is_pass_finished(row["end_at"]),
    )


async def create_pass(draft: HockeyPassDraft) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO hockey_passes (
                title,
                description,
                start_at,
                end_at,
                premium_currency_code,
                premium_price_amount,
                levels_count,
                points_per_level,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, 40, 5, 1)
            """,
            (
                draft.title,
                draft.description,
                to_moscow_iso(now_moscow()),
                draft.end_at,
                draft.premium_currency_code,
                draft.premium_price_amount,
            ),
        )
        pass_id = int(cursor.lastrowid)
        connection.commit()

    return pass_id


async def update_pass_text_field(pass_id: int, field: str, value: str) -> bool:
    if field not in {"title", "description", "end_at"}:
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE hockey_passes
            SET {field} = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (value, pass_id),
        )
        connection.commit()

    return cursor.rowcount > 0


async def update_pass_price(pass_id: int, currency_code: str | None, amount: int) -> bool:
    with get_connection() as connection:
        if currency_code is not None:
            currency_cursor = connection.execute("SELECT code FROM currencies WHERE code = ? AND active = 1", (currency_code,))
            if currency_cursor.fetchone() is None:
                return False

        cursor = connection.execute(
            """
            UPDATE hockey_passes
            SET premium_currency_code = ?, premium_price_amount = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (currency_code, amount, pass_id),
        )
        connection.commit()

    return cursor.rowcount > 0


async def toggle_pass_active(pass_id: int) -> bool | None:
    with get_connection() as connection:
        cursor = connection.execute("SELECT active FROM hockey_passes WHERE id = ?", (pass_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        new_value = 0 if row["active"] else 1
        connection.execute(
            "UPDATE hockey_passes SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_value, pass_id),
        )
        connection.commit()

    return bool(new_value)


async def delete_pass(pass_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM hockey_passes WHERE id = ?", (pass_id,))
        connection.commit()
    return cursor.rowcount > 0


def reward_from_row(row, user_level: int = 1, premium_unlocked: bool = False) -> HockeyPassRewardItem:
    claimed = bool(row["claimed"] if "claimed" in row.keys() else False)
    level = int(row["level"])
    track = row["track"]
    active = bool(row["active"])
    available = active and not claimed and user_level >= level and (track == "free" or premium_unlocked)
    locked_reason = None

    if not active:
        locked_reason = "Награда выключена"
    elif claimed:
        locked_reason = "Уже получена"
    elif user_level < level:
        locked_reason = f"Откроется на уровне {level}"
    elif track == "premium" and not premium_unlocked:
        locked_reason = "Нужен Premium"

    title = row["title"] or auto_reward_title(row)

    return HockeyPassRewardItem(
        id=row["id"],
        pass_id=row["pass_id"],
        level=level,
        track=track,
        reward_type=row["reward_type"],
        title=title,
        amount=int(row["amount"] or 0),
        currency_code=row["currency_code"],
        currency_name=row["currency_name"],
        currency_icon=row["currency_icon"],
        pack_id=row["pack_id"],
        pack_name=row["pack_name"],
        pack_image_path=row["pack_image_path"],
        card_id=row["card_id"],
        card_name=row["card_name"],
        card_image_path=row["card_image_path"],
        card_position=row["card_position"],
        card_overall=row["card_overall"],
        active=active,
        claimed=claimed,
        available=available,
        locked_reason=locked_reason,
    )


def auto_reward_title(row) -> str:
    reward_type = row["reward_type"]
    if reward_type == "currency":
        icon = row["currency_icon"] or "💠"
        name = row["currency_name"] or row["currency_code"] or "валюта"
        return f"{icon} {int(row['amount'] or 0):,} {name}".replace(",", " ")
    if reward_type == "pack":
        return f"🎁 {row['pack_name'] or 'Пак'}"
    if reward_type == "card":
        return f"🃏 {row['card_name'] or 'Карточка'}"
    return "🎁 Награда"


REWARD_SELECT_SQL = """
SELECT
    r.id,
    r.pass_id,
    r.level,
    r.track,
    r.reward_type,
    r.currency_code,
    r.amount,
    r.pack_id,
    r.card_id,
    r.title,
    r.active,
    c.name AS currency_name,
    c.icon AS currency_icon,
    p.name AS pack_name,
    p.image_path AS pack_image_path,
    cards.name AS card_name,
    cards.image_path AS card_image_path,
    cards.position AS card_position,
    cards.overall AS card_overall,
    {claimed_expr} AS claimed
FROM hockey_pass_rewards r
LEFT JOIN currencies c ON c.code = r.currency_code
LEFT JOIN packs p ON p.id = r.pack_id
LEFT JOIN cards ON cards.id = r.card_id
"""


async def get_user_rewards_page(telegram_id: int, page: int = 1, per_page: int = PER_PAGE) -> UserRewardsPage | None:
    with get_connection() as connection:
        user_cursor = connection.execute(
            "SELECT id, bp_points FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        user_row = user_cursor.fetchone()
        if user_row is None:
            return None

        pass_row = await get_active_pass_row(connection)
        if pass_row is None:
            return None

        connection.execute(
            "INSERT INTO user_hockey_passes (user_id, pass_id) VALUES (?, ?) ON CONFLICT(user_id, pass_id) DO NOTHING",
            (user_row["id"], pass_row["id"]),
        )
        user_pass_cursor = connection.execute(
            "SELECT premium_unlocked FROM user_hockey_passes WHERE user_id = ? AND pass_id = ?",
            (user_row["id"], pass_row["id"]),
        )
        user_pass_row = user_pass_cursor.fetchone()
        premium_unlocked = bool(user_pass_row and user_pass_row["premium_unlocked"])
        user_level = calculate_level(int(user_row["bp_points"] or 0), int(pass_row["levels_count"] or 40), int(pass_row["points_per_level"] or 5))

        count_cursor = connection.execute(
            "SELECT COUNT(*) AS total_count FROM hockey_pass_rewards WHERE pass_id = ? AND active = 1",
            (pass_row["id"],),
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            REWARD_SELECT_SQL.format(claimed_expr="CASE WHEN cr.id IS NULL THEN 0 ELSE 1 END")
            + """
            LEFT JOIN user_hockey_pass_rewards cr ON cr.reward_id = r.id AND cr.user_id = ?
            WHERE r.pass_id = ? AND r.active = 1
            ORDER BY r.level, CASE r.track WHEN 'free' THEN 1 ELSE 2 END, r.id
            LIMIT ? OFFSET ?
            """,
            (user_row["id"], pass_row["id"], per_page, offset),
        )
        rows = cursor.fetchall()
        connection.commit()

    # add claimed manually for sqlite rows by selecting alias not included yet due key access hack
    items = []
    for row in rows:
        # sqlite Row has no mutable alias; repeat fetch with claimed included in SQL impossible? It is possible by selecting cr.id AS claimed, but appended not currently.
        items.append(reward_from_row(row, user_level=user_level, premium_unlocked=premium_unlocked))

    return UserRewardsPage(pass_id=pass_row["id"], items=items, page=safe_page, pages_count=pages_count, total_count=total_count, user_level=user_level, premium_unlocked=premium_unlocked)


async def get_admin_rewards_page(pass_id: int, page: int = 1, per_page: int = PER_PAGE) -> AdminRewardsPage | None:
    with get_connection() as connection:
        pass_cursor = connection.execute("SELECT title FROM hockey_passes WHERE id = ?", (pass_id,))
        pass_row = pass_cursor.fetchone()
        if pass_row is None:
            return None

        count_cursor = connection.execute("SELECT COUNT(*) AS total_count FROM hockey_pass_rewards WHERE pass_id = ?", (pass_id,))
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        cursor = connection.execute(
            REWARD_SELECT_SQL.format(claimed_expr="0")
            + """
            WHERE r.pass_id = ?
            ORDER BY r.level, CASE r.track WHEN 'free' THEN 1 ELSE 2 END, r.id
            LIMIT ? OFFSET ?
            """,
            (pass_id, per_page, offset),
        )
        rows = cursor.fetchall()

    return AdminRewardsPage(
        pass_id=pass_id,
        pass_title=pass_row["title"],
        items=[reward_from_row(row, user_level=40, premium_unlocked=True) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )


async def get_reward_profile(reward_id: int, telegram_id: int | None = None) -> HockeyPassRewardItem | None:
    user_id = None
    user_level = 40
    premium_unlocked = True

    with get_connection() as connection:
        if telegram_id is not None:
            user_cursor = connection.execute("SELECT id, bp_points FROM users WHERE telegram_id = ?", (telegram_id,))
            user_row = user_cursor.fetchone()
            if user_row is None:
                return None
            user_id = user_row["id"]

        if user_id is not None:
            query = REWARD_SELECT_SQL.format(claimed_expr="CASE WHEN cr.id IS NULL THEN 0 ELSE 1 END") + """
            LEFT JOIN user_hockey_pass_rewards cr ON cr.reward_id = r.id AND cr.user_id = ?
            WHERE r.id = ?
            """
            params = (user_id, reward_id)
        else:
            query = REWARD_SELECT_SQL.format(claimed_expr="0") + """
            WHERE r.id = ?
            """
            params = (reward_id,)

        cursor = connection.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None

        if user_id is not None:
            pass_cursor = connection.execute("SELECT levels_count, points_per_level FROM hockey_passes WHERE id = ?", (row["pass_id"],))
            pass_row = pass_cursor.fetchone()
            user_level = calculate_level(int(user_row["bp_points"] or 0), int(pass_row["levels_count"] or 40), int(pass_row["points_per_level"] or 5))
            up_cursor = connection.execute("SELECT premium_unlocked FROM user_hockey_passes WHERE user_id = ? AND pass_id = ?", (user_id, row["pass_id"]))
            up_row = up_cursor.fetchone()
            premium_unlocked = bool(up_row and up_row["premium_unlocked"])

    return reward_from_row(row, user_level=user_level, premium_unlocked=premium_unlocked)


async def create_reward(draft: RewardDraft) -> int | None:
    with get_connection() as connection:
        pass_cursor = connection.execute("SELECT id FROM hockey_passes WHERE id = ?", (draft.pass_id,))
        if pass_cursor.fetchone() is None:
            return None

        cursor = connection.execute(
            """
            INSERT INTO hockey_pass_rewards (
                pass_id,
                level,
                track,
                reward_type,
                currency_code,
                amount,
                pack_id,
                card_id,
                title,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                draft.pass_id,
                draft.level,
                draft.track,
                draft.reward_type,
                draft.currency_code,
                draft.amount,
                draft.pack_id,
                draft.card_id,
                draft.title,
            ),
        )
        reward_id = int(cursor.lastrowid)
        connection.commit()

    return reward_id


async def update_reward_basic_field(reward_id: int, field: str, value: object) -> bool:
    if field not in {"title", "level", "amount", "track"}:
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE hockey_pass_rewards SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, reward_id),
        )
        connection.commit()
    return cursor.rowcount > 0


async def replace_reward_payload(draft: RewardDraft, reward_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE hockey_pass_rewards
            SET
                reward_type = ?,
                currency_code = ?,
                amount = ?,
                pack_id = ?,
                card_id = ?,
                title = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                draft.reward_type,
                draft.currency_code,
                draft.amount,
                draft.pack_id,
                draft.card_id,
                draft.title,
                reward_id,
            ),
        )
        connection.commit()
    return cursor.rowcount > 0


async def toggle_reward_active(reward_id: int) -> bool | None:
    with get_connection() as connection:
        cursor = connection.execute("SELECT active FROM hockey_pass_rewards WHERE id = ?", (reward_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        new_value = 0 if row["active"] else 1
        connection.execute("UPDATE hockey_pass_rewards SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_value, reward_id))
        connection.commit()
    return bool(new_value)


async def delete_reward(reward_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM hockey_pass_rewards WHERE id = ?", (reward_id,))
        connection.commit()
    return cursor.rowcount > 0


async def get_currency_choices() -> list[ChoiceItem]:
    with get_connection() as connection:
        cursor = connection.execute("SELECT code, name, icon FROM currencies WHERE active = 1 ORDER BY name")
        rows = cursor.fetchall()
    return [ChoiceItem(id=row["code"], title=f"{row['icon']} {row['name']}", subtitle=row["code"]) for row in rows]


async def get_pack_choices_page(page: int = 1, per_page: int = PER_PAGE, search: str | None = None) -> ChoicePage:
    clean = clean_text(search)
    where = "WHERE active = 1"
    params: list[object] = []
    if clean:
        where += " AND (name LIKE ? OR code LIKE ? OR description LIKE ?)"
        params.extend([f"%{clean}%", f"%{clean}%", f"%{clean}%"])
    with get_connection() as connection:
        count = connection.execute(f"SELECT COUNT(*) AS total_count FROM packs {where}", params).fetchone()["total_count"]
        pages = max(1, ceil(int(count) / per_page))
        safe_page = min(max(page, 1), pages)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"SELECT id, name, code, image_path FROM packs {where} ORDER BY name LIMIT ? OFFSET ?",
            [*params, per_page, offset],
        ).fetchall()
    return ChoicePage(
        items=[ChoiceItem(id=row["id"], title=row["name"], subtitle=row["code"], image_path=row["image_path"]) for row in rows],
        page=safe_page,
        pages_count=pages,
        total_count=int(count),
        search=clean or None,
    )


async def get_card_choices_page(page: int = 1, per_page: int = PER_PAGE, search: str | None = None) -> ChoicePage:
    clean = clean_text(search)
    where = "WHERE cards.active = 1"
    params: list[object] = []
    if clean:
        where += " AND (cards.name LIKE ? OR cards.team LIKE ? OR cards.country LIKE ? OR cards.rarity LIKE ? OR collections.name LIKE ?)"
        params.extend([f"%{clean}%"] * 5)
    with get_connection() as connection:
        count = connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where}
            """,
            params,
        ).fetchone()["total_count"]
        pages = max(1, ceil(int(count) / per_page))
        safe_page = min(max(page, 1), pages)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT cards.id, cards.name, cards.position, cards.overall, cards.rarity, cards.image_path, collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            {where}
            ORDER BY cards.overall DESC, cards.name
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()
    return ChoicePage(
        items=[ChoiceItem(id=row["id"], title=f"{row['name']} · {row['overall']} OVR", subtitle=f"{row['position']} · {row['rarity']} · {row['collection_name']}", image_path=row["image_path"]) for row in rows],
        page=safe_page,
        pages_count=pages,
        total_count=int(count),
        search=clean or None,
    )


async def claim_reward(telegram_id: int, reward_id: int) -> tuple[ClaimResult | None, str | None]:
    with get_connection() as connection:
        user_cursor = connection.execute("SELECT id, bp_points FROM users WHERE telegram_id = ?", (telegram_id,))
        user_row = user_cursor.fetchone()
        if user_row is None:
            return None, "Открой игру через /start."

        cursor = connection.execute(REWARD_SELECT_SQL.format(claimed_expr="0") + " WHERE r.id = ? AND r.active = 1", (reward_id,))
        row = cursor.fetchone()
        if row is None:
            return None, "Награда уже недоступна."

        pass_cursor = connection.execute("SELECT id, active, end_at, levels_count, points_per_level FROM hockey_passes WHERE id = ?", (row["pass_id"],))
        pass_row = pass_cursor.fetchone()
        if pass_row is None or not pass_row["active"] or is_pass_finished(pass_row["end_at"]):
            return None, "Сезон Hockey Pass уже завершён."

        level = calculate_level(int(user_row["bp_points"] or 0), int(pass_row["levels_count"] or 40), int(pass_row["points_per_level"] or 5))
        if level < int(row["level"]):
            return None, "Уровень ещё не открыт."

        connection.execute(
            "INSERT INTO user_hockey_passes (user_id, pass_id) VALUES (?, ?) ON CONFLICT(user_id, pass_id) DO NOTHING",
            (user_row["id"], pass_row["id"]),
        )
        up_row = connection.execute("SELECT premium_unlocked FROM user_hockey_passes WHERE user_id = ? AND pass_id = ?", (user_row["id"], pass_row["id"])).fetchone()

        if row["track"] == "premium" and not bool(up_row and up_row["premium_unlocked"]):
            return None, "Premium-ветка ещё не открыта."

        claimed_cursor = connection.execute("SELECT id FROM user_hockey_pass_rewards WHERE user_id = ? AND reward_id = ?", (user_row["id"], reward_id))
        if claimed_cursor.fetchone() is not None:
            return None, "Награда уже получена."

        reward = reward_from_row(row, user_level=level, premium_unlocked=bool(up_row and up_row["premium_unlocked"]))

        try:
            if row["reward_type"] == "currency":
                code = row["currency_code"]
                amount = int(row["amount"] or 0)
                if not code or amount <= 0:
                    return None, "Награда пока не готова."
                connection.execute(
                    """
                    INSERT INTO currency_balances (user_id, currency_code, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, currency_code) DO UPDATE SET
                        amount = currency_balances.amount + excluded.amount,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_row["id"], code, amount),
                )
            elif row["reward_type"] == "pack":
                if row["pack_id"] is None:
                    return None, "Пак пока не выбран."
                quantity = max(1, int(row["amount"] or 1))
                connection.execute(
                    """
                    INSERT INTO user_packs (user_id, pack_id, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, pack_id) DO UPDATE SET
                        quantity = user_packs.quantity + excluded.quantity,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_row["id"], row["pack_id"], quantity),
                )
            elif row["reward_type"] == "card":
                if row["card_id"] is None:
                    return None, "Карточка пока не выбрана."
                quantity = max(1, int(row["amount"] or 1))
                for _ in range(quantity):
                    connection.execute(
                        """
                        INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked)
                        VALUES (?, ?, 'hockey_pass', 0, 0)
                        """,
                        (user_row["id"], row["card_id"]),
                    )
            else:
                return None, "Награда пока не готова."

            connection.execute("INSERT INTO user_hockey_pass_rewards (user_id, reward_id) VALUES (?, ?)", (user_row["id"], reward_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    image_path = reward.card_image_path if reward.reward_type == "card" else reward.pack_image_path if reward.reward_type == "pack" else None
    return ClaimResult(reward=reward, message=f"🎁 Награда получена: {reward.title}", image_path=image_path), None


async def purchase_premium(telegram_id: int) -> tuple[PurchaseResult | None, str | None]:
    with get_connection() as connection:
        user_row = connection.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if user_row is None:
            return None, "Открой игру через /start."

        pass_row = await get_active_pass_row(connection)
        if pass_row is None:
            return None, "Сейчас нет активного Hockey Pass."

        connection.execute("INSERT INTO user_hockey_passes (user_id, pass_id) VALUES (?, ?) ON CONFLICT(user_id, pass_id) DO NOTHING", (user_row["id"], pass_row["id"]))
        user_pass = connection.execute("SELECT premium_unlocked FROM user_hockey_passes WHERE user_id = ? AND pass_id = ?", (user_row["id"], pass_row["id"])).fetchone()

        if user_pass and user_pass["premium_unlocked"]:
            return None, "Premium уже открыт."

        currency_code = pass_row["premium_currency_code"]
        price = int(pass_row["premium_price_amount"] or 0)
        currency_row = None
        balance_after = None

        try:
            if price > 0:
                if currency_code is None:
                    return None, "Для покупки Premium пока не выбрана валюта."

                currency_row = connection.execute("SELECT name, icon FROM currencies WHERE code = ? AND active = 1", (currency_code,)).fetchone()
                balance_row = connection.execute("SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?", (user_row["id"], currency_code)).fetchone()
                balance = int(balance_row["amount"] if balance_row else 0)

                if balance < price:
                    return None, "Недостаточно средств для Premium."

                balance_after = balance - price
                connection.execute("UPDATE currency_balances SET amount = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND currency_code = ?", (balance_after, user_row["id"], currency_code))

            connection.execute(
                """
                UPDATE user_hockey_passes
                SET premium_unlocked = 1, purchased_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND pass_id = ?
                """,
                (user_row["id"], pass_row["id"]),
            )
            connection.execute(
                """
                UPDATE users
                SET premium_pass = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (user_row["id"],),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    price_text = format_price(price, currency_row["icon"] if currency_row else None, currency_row["name"] if currency_row else None, currency_code)
    return PurchaseResult(title=pass_row["title"], price_text=price_text, balance_after=balance_after), None
