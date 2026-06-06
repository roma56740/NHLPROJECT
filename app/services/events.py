from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Literal

from app.database.db import get_connection
from app.services.users import get_player_profile_by_telegram_id


MSK = timezone(timedelta(hours=3))
UTC = timezone.utc
EVENT_TARGET_TYPES = {"matches_played", "matches_won", "goals_scored", "shutout_wins"}
EVENT_REWARD_TYPES = {"currency", "pack", "card"}

EVENT_TARGET_TITLES = {
    "matches_played": "сыграть матчи",
    "matches_won": "выиграть матчи",
    "goals_scored": "забить голы",
    "shutout_wins": "сухие победы",
}

EVENT_REWARD_TITLES = {
    "currency": "валюта",
    "pack": "пак",
    "card": "карточка",
}


@dataclass(frozen=True)
class EventDraft:
    title: str
    description: str
    image_path: str | None
    target_type: str
    target_value: int
    reward_type: str
    reward_currency_code: str | None
    reward_amount: int
    reward_pack_id: int | None
    reward_card_id: int | None
    end_at: str | None


@dataclass(frozen=True)
class EventItem:
    id: int
    title: str
    description: str
    image_path: str | None
    target_type: str
    target_value: int
    reward_title: str
    progress: int
    completed: bool
    reward_claimed: bool
    end_at: str | None


@dataclass(frozen=True)
class UserEventPage:
    items: list[EventItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class UserEventProfile:
    id: int
    title: str
    description: str
    image_path: str | None
    target_type: str
    target_value: int
    reward_title: str
    progress_id: int
    progress: int
    completed: bool
    reward_claimed: bool
    start_at: str
    end_at: str | None


@dataclass(frozen=True)
class EventClaimResult:
    success: bool
    message: str
    reward_title: str = ""
    image_path: str | None = None
    page: int = 1


@dataclass(frozen=True)
class AdminEventItem:
    id: int
    title: str
    target_type: str
    target_value: int
    reward_title: str
    active: bool
    announcement_sent: bool
    end_at: str | None


@dataclass(frozen=True)
class AdminEventPage:
    items: list[AdminEventItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None = None


@dataclass(frozen=True)
class AdminEventProfile:
    id: int
    title: str
    description: str
    image_path: str | None
    target_type: str
    target_value: int
    reward_type: str
    reward_title: str
    reward_amount: int
    reward_currency_code: str | None
    reward_pack_id: int | None
    reward_card_id: int | None
    active: bool
    announcement_sent: bool
    start_at: str
    end_at: str | None
    progress_count: int
    completed_count: int
    claimed_count: int


@dataclass(frozen=True)
class AdminActionResult:
    success: bool
    message: str
    event_id: int | None = None


@dataclass(frozen=True)
class ChoiceItem:
    id: int
    title: str
    subtitle: str
    image_path: str | None = None


@dataclass(frozen=True)
class ChoicePage:
    items: list[ChoiceItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None = None


def utc_now_text() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    return None


def format_msk_datetime(value: str | None) -> str:
    dt = parse_db_datetime(value)
    if dt is None:
        return "не ограничено"

    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M МСК")


def parse_msk_datetime(value: str) -> str | None:
    text = value.strip()

    if text in {"-", "нет", "без срока"}:
        return None

    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == "%d.%m.%Y":
                dt = dt.replace(hour=23, minute=59)
            return dt.replace(tzinfo=MSK).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    raise ValueError("bad_datetime")


def is_event_active_now(row) -> bool:
    if not bool(row["active"]):
        return False

    now = datetime.now(UTC)
    start_at = parse_db_datetime(row["start_at"])
    end_at = parse_db_datetime(row["end_at"])

    if start_at and start_at > now:
        return False

    if end_at and end_at < now:
        return False

    return True


def clean_search_query(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def calculate_pages(total_count: int, per_page: int) -> int:
    return max(1, ceil(total_count / per_page))


def get_reward_title(row) -> str:
    reward_type = row["reward_type"]
    amount = int(row["reward_amount"] or 0)

    if reward_type == "currency":
        icon = row["currency_icon"] or "💱"
        name = row["currency_name"] or row["reward_currency_code"] or "валюта"
        return f"{icon} {format_number(amount)} {name}"

    if reward_type == "pack":
        name = row["pack_name"] or "пак"
        return f"🎁 {amount} × {name}"

    if reward_type == "card":
        name = row["card_name"] or "карточка"
        return f"🃏 {amount} × {name}"

    return "🎁 Награда"


def get_reward_image_path(row) -> str | None:
    if row["reward_type"] == "pack":
        return row["pack_image_path"]
    if row["reward_type"] == "card":
        return row["card_image_path"]
    return None


EVENT_SELECT_SQL = """
SELECT
    e.id,
    e.title,
    e.description,
    e.image_path,
    e.target_type,
    e.target_value,
    e.reward_type,
    e.reward_currency_code,
    e.reward_amount,
    e.reward_pack_id,
    e.reward_card_id,
    e.start_at,
    e.end_at,
    e.active,
    e.announcement_sent,
    c.name AS currency_name,
    c.icon AS currency_icon,
    p.name AS pack_name,
    p.image_path AS pack_image_path,
    cards.name AS card_name,
    cards.image_path AS card_image_path
FROM events e
LEFT JOIN currencies c ON c.code = e.reward_currency_code
LEFT JOIN packs p ON p.id = e.reward_pack_id
LEFT JOIN cards ON cards.id = e.reward_card_id
"""

USER_EVENT_SELECT_SQL = """
SELECT
    e.id,
    e.title,
    e.description,
    e.image_path,
    e.target_type,
    e.target_value,
    e.reward_type,
    e.reward_currency_code,
    e.reward_amount,
    e.reward_pack_id,
    e.reward_card_id,
    e.start_at,
    e.end_at,
    e.active,
    e.announcement_sent,
    c.name AS currency_name,
    c.icon AS currency_icon,
    p.name AS pack_name,
    p.image_path AS pack_image_path,
    cards.name AS card_name,
    cards.image_path AS card_image_path,
    uep.id AS progress_id,
    uep.progress,
    uep.completed,
    uep.reward_claimed
FROM events e
LEFT JOIN currencies c ON c.code = e.reward_currency_code
LEFT JOIN packs p ON p.id = e.reward_pack_id
LEFT JOIN cards ON cards.id = e.reward_card_id
"""


def ensure_user_event_progress(connection, user_id: int) -> None:
    rows = connection.execute(
        """
        SELECT id
        FROM events
        WHERE active = 1
          AND datetime(start_at) <= datetime('now')
          AND (end_at IS NULL OR datetime(end_at) >= datetime('now'))
        """
    ).fetchall()

    for row in rows:
        connection.execute(
            """
            INSERT OR IGNORE INTO user_event_progress (user_id, event_id)
            VALUES (?, ?)
            """,
            (user_id, row["id"]),
        )


def row_to_user_event_item(row) -> EventItem:
    return EventItem(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        image_path=row["image_path"],
        target_type=row["target_type"],
        target_value=int(row["target_value"]),
        reward_title=get_reward_title(row),
        progress=int(row["progress"] or 0),
        completed=bool(row["completed"]),
        reward_claimed=bool(row["reward_claimed"]),
        end_at=row["end_at"],
    )


async def get_user_events_page(telegram_id: int, page: int = 1, per_page: int = 5) -> UserEventPage | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    with get_connection() as connection:
        ensure_user_event_progress(connection, profile.id)
        connection.commit()

        count = connection.execute(
            """
            SELECT COUNT(*) AS total_count
            FROM events
            WHERE active = 1
              AND datetime(start_at) <= datetime('now')
              AND (end_at IS NULL OR datetime(end_at) >= datetime('now'))
            """
        ).fetchone()["total_count"]
        pages = calculate_pages(int(count), per_page)
        safe_page = min(max(1, page), pages)
        offset = (safe_page - 1) * per_page

        rows = connection.execute(
            USER_EVENT_SELECT_SQL
            + """
            JOIN user_event_progress uep ON uep.event_id = e.id AND uep.user_id = ?
            WHERE e.active = 1
              AND datetime(e.start_at) <= datetime('now')
              AND (e.end_at IS NULL OR datetime(e.end_at) >= datetime('now'))
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ? OFFSET ?
            """,
            (profile.id, per_page, offset),
        ).fetchall()

    return UserEventPage(
        items=[row_to_user_event_item(row) for row in rows],
        page=safe_page,
        pages_count=pages,
        total_count=int(count),
    )


async def get_user_event_profile(telegram_id: int, event_id: int) -> UserEventProfile | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    with get_connection() as connection:
        ensure_user_event_progress(connection, profile.id)
        connection.commit()
        row = connection.execute(
            USER_EVENT_SELECT_SQL
            + """
            JOIN user_event_progress uep ON uep.event_id = e.id AND uep.user_id = ?
            WHERE e.id = ?
              AND e.active = 1
              AND datetime(e.start_at) <= datetime('now')
              AND (e.end_at IS NULL OR datetime(e.end_at) >= datetime('now'))
            """,
            (profile.id, event_id),
        ).fetchone()

    if row is None:
        return None

    return UserEventProfile(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        image_path=row["image_path"],
        target_type=row["target_type"],
        target_value=int(row["target_value"]),
        reward_title=get_reward_title(row),
        progress_id=row["progress_id"],
        progress=int(row["progress"] or 0),
        completed=bool(row["completed"]),
        reward_claimed=bool(row["reward_claimed"]),
        start_at=row["start_at"],
        end_at=row["end_at"],
    )


async def claim_event_reward(telegram_id: int, progress_id: int) -> EventClaimResult:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return EventClaimResult(False, "Открой игру через /start.")

    with get_connection() as connection:
        row = connection.execute(
            USER_EVENT_SELECT_SQL
            + """
            JOIN user_event_progress uep ON uep.event_id = e.id
            WHERE uep.id = ? AND uep.user_id = ?
            """,
            (progress_id, profile.id),
        ).fetchone()

        if row is None:
            return EventClaimResult(False, "Событие уже недоступно.")

        if not is_event_active_now(row):
            return EventClaimResult(False, "Событие уже завершилось.")

        if int(row["progress"] or 0) < int(row["target_value"] or 1):
            return EventClaimResult(False, "Награда ещё не открыта.")

        if bool(row["reward_claimed"]):
            return EventClaimResult(False, "Награда уже получена.")

        reward_title = get_reward_title(row)
        reward_image_path = get_reward_image_path(row)

        try:
            if row["reward_type"] == "currency":
                code = row["reward_currency_code"]
                amount = int(row["reward_amount"] or 0)
                if not code or amount <= 0:
                    return EventClaimResult(False, "Награда пока не готова.")
                connection.execute(
                    """
                    INSERT INTO currency_balances (user_id, currency_code, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, currency_code) DO UPDATE SET
                        amount = currency_balances.amount + excluded.amount,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (profile.id, code, amount),
                )
            elif row["reward_type"] == "pack":
                if row["reward_pack_id"] is None:
                    return EventClaimResult(False, "Пак пока не выбран.")
                quantity = max(1, int(row["reward_amount"] or 1))
                connection.execute(
                    """
                    INSERT INTO user_packs (user_id, pack_id, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, pack_id) DO UPDATE SET
                        quantity = user_packs.quantity + excluded.quantity,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (profile.id, row["reward_pack_id"], quantity),
                )
            elif row["reward_type"] == "card":
                if row["reward_card_id"] is None:
                    return EventClaimResult(False, "Карточка пока не выбрана.")
                quantity = max(1, int(row["reward_amount"] or 1))
                for _ in range(quantity):
                    connection.execute(
                        """
                        INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked)
                        VALUES (?, ?, 'event', 0, 0)
                        """,
                        (profile.id, row["reward_card_id"]),
                    )
            else:
                return EventClaimResult(False, "Награда пока не готова.")

            connection.execute(
                """
                UPDATE user_event_progress
                SET reward_claimed = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (progress_id,),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO user_event_rewards (user_id, event_id, reward_type, title)
                VALUES (?, ?, ?, ?)
                """,
                (profile.id, row["id"], row["reward_type"], reward_title),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return EventClaimResult(True, "🎁 Награда события получена!", reward_title=reward_title, image_path=reward_image_path)


async def apply_match_event_progress(user_id: int, is_win: bool, goals_scored: int, goals_allowed: int) -> None:
    with get_connection() as connection:
        ensure_user_event_progress(connection, user_id)
        events = connection.execute(
            """
            SELECT e.id, e.target_type, e.target_value, uep.progress
            FROM events e
            JOIN user_event_progress uep ON uep.event_id = e.id AND uep.user_id = ?
            WHERE e.active = 1
              AND uep.reward_claimed = 0
              AND datetime(e.start_at) <= datetime('now')
              AND (e.end_at IS NULL OR datetime(e.end_at) >= datetime('now'))
            """,
            (user_id,),
        ).fetchall()

        for event in events:
            increment = 0
            target_type = event["target_type"]

            if target_type == "matches_played":
                increment = 1
            elif target_type == "matches_won" and is_win:
                increment = 1
            elif target_type == "goals_scored":
                increment = max(0, int(goals_scored))
            elif target_type == "shutout_wins" and is_win and int(goals_allowed) == 0:
                increment = 1

            if increment <= 0:
                continue

            new_progress = min(int(event["target_value"]), int(event["progress"] or 0) + increment)
            completed = 1 if new_progress >= int(event["target_value"]) else 0
            completed_at_sql = ", completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)" if completed else ""
            connection.execute(
                f"""
                UPDATE user_event_progress
                SET progress = ?,
                    completed = ?,
                    updated_at = CURRENT_TIMESTAMP
                    {completed_at_sql}
                WHERE user_id = ? AND event_id = ?
                """,
                (new_progress, completed, user_id, event["id"]),
            )

        connection.commit()


def build_admin_where(search: str | None) -> tuple[str, list[object]]:
    clean = clean_search_query(search)
    if not clean:
        return "", []

    like = f"%{clean}%"
    return "WHERE e.title LIKE ? OR e.description LIKE ? OR e.target_type LIKE ?", [like, like, like]


def row_to_admin_item(row) -> AdminEventItem:
    return AdminEventItem(
        id=row["id"],
        title=row["title"],
        target_type=row["target_type"],
        target_value=int(row["target_value"]),
        reward_title=get_reward_title(row),
        active=bool(row["active"]),
        announcement_sent=bool(row["announcement_sent"]),
        end_at=row["end_at"],
    )


async def get_admin_events_page(page: int = 1, per_page: int = 5, search: str | None = None) -> AdminEventPage:
    where, params = build_admin_where(search)
    clean = clean_search_query(search)

    with get_connection() as connection:
        count = connection.execute(f"SELECT COUNT(*) AS total_count FROM events e {where}", params).fetchone()["total_count"]
        pages = calculate_pages(int(count), per_page)
        safe_page = min(max(1, page), pages)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            EVENT_SELECT_SQL
            + f"""
            {where}
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return AdminEventPage(
        items=[row_to_admin_item(row) for row in rows],
        page=safe_page,
        pages_count=pages,
        total_count=int(count),
        search=clean or None,
    )


async def get_admin_event_profile(event_id: int) -> AdminEventProfile | None:
    with get_connection() as connection:
        row = connection.execute(EVENT_SELECT_SQL + " WHERE e.id = ?", (event_id,)).fetchone()
        if row is None:
            return None

        stats = connection.execute(
            """
            SELECT
                COUNT(*) AS progress_count,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed_count,
                SUM(CASE WHEN reward_claimed = 1 THEN 1 ELSE 0 END) AS claimed_count
            FROM user_event_progress
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()

    return AdminEventProfile(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        image_path=row["image_path"],
        target_type=row["target_type"],
        target_value=int(row["target_value"]),
        reward_type=row["reward_type"],
        reward_title=get_reward_title(row),
        reward_amount=int(row["reward_amount"] or 1),
        reward_currency_code=row["reward_currency_code"],
        reward_pack_id=row["reward_pack_id"],
        reward_card_id=row["reward_card_id"],
        active=bool(row["active"]),
        announcement_sent=bool(row["announcement_sent"]),
        start_at=row["start_at"],
        end_at=row["end_at"],
        progress_count=int(stats["progress_count"] or 0),
        completed_count=int(stats["completed_count"] or 0),
        claimed_count=int(stats["claimed_count"] or 0),
    )


async def create_event(draft: EventDraft) -> AdminActionResult:
    if draft.target_type not in EVENT_TARGET_TYPES:
        return AdminActionResult(False, "Выбери цель события.")
    if draft.reward_type not in EVENT_REWARD_TYPES:
        return AdminActionResult(False, "Выбери награду события.")
    if draft.target_value <= 0:
        return AdminActionResult(False, "Количество должно быть больше нуля.")
    if draft.reward_amount <= 0:
        return AdminActionResult(False, "Награда должна быть больше нуля.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO events (
                title, description, image_path, target_type, target_value,
                reward_type, reward_currency_code, reward_amount, reward_pack_id, reward_card_id,
                start_at, end_at, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                draft.title,
                draft.description,
                draft.image_path,
                draft.target_type,
                draft.target_value,
                draft.reward_type,
                draft.reward_currency_code,
                draft.reward_amount,
                draft.reward_pack_id,
                draft.reward_card_id,
                utc_now_text(),
                draft.end_at,
            ),
        )
        event_id = int(cursor.lastrowid)
        connection.commit()

    return AdminActionResult(True, "✅ Событие создано.", event_id=event_id)


async def toggle_event_active(event_id: int) -> AdminActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT active FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return AdminActionResult(False, "Событие не найдено.")

        new_active = 0 if row["active"] else 1
        connection.execute(
            "UPDATE events SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_active, event_id),
        )
        connection.commit()

    return AdminActionResult(True, "✅ Событие обновлено.")


async def delete_event(event_id: int) -> AdminActionResult:
    with get_connection() as connection:
        connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
        connection.commit()

    return AdminActionResult(True, "🗑 Событие удалено.")


async def update_event_text_field(event_id: int, field: str, value: str) -> AdminActionResult:
    if field not in {"title", "description"}:
        return AdminActionResult(False, "Поле не найдено.")

    with get_connection() as connection:
        connection.execute(
            f"UPDATE events SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, event_id),
        )
        connection.commit()

    return AdminActionResult(True, "✅ Событие обновлено.")


async def update_event_number_field(event_id: int, field: str, value: int) -> AdminActionResult:
    if field not in {"target_value", "reward_amount"}:
        return AdminActionResult(False, "Поле не найдено.")
    if value <= 0:
        return AdminActionResult(False, "Число должно быть больше нуля.")

    with get_connection() as connection:
        connection.execute(
            f"UPDATE events SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, event_id),
        )
        connection.commit()

    return AdminActionResult(True, "✅ Событие обновлено.")


async def update_event_target(event_id: int, target_type: str) -> AdminActionResult:
    if target_type not in EVENT_TARGET_TYPES:
        return AdminActionResult(False, "Цель не найдена.")

    with get_connection() as connection:
        connection.execute("UPDATE events SET target_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (target_type, event_id))
        connection.commit()

    return AdminActionResult(True, "✅ Цель обновлена.")


async def update_event_end_at(event_id: int, end_at: str | None) -> AdminActionResult:
    with get_connection() as connection:
        connection.execute("UPDATE events SET end_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (end_at, event_id))
        connection.commit()

    return AdminActionResult(True, "✅ Дата обновлена.")


async def update_event_image(event_id: int, image_path: str | None) -> AdminActionResult:
    with get_connection() as connection:
        connection.execute("UPDATE events SET image_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (image_path, event_id))
        connection.commit()

    return AdminActionResult(True, "✅ Обложка обновлена.")


async def update_event_reward_currency(event_id: int, currency_code: str, amount: int) -> AdminActionResult:
    with get_connection() as connection:
        currency = connection.execute("SELECT code FROM currencies WHERE code = ? AND active = 1", (currency_code,)).fetchone()
        if currency is None:
            return AdminActionResult(False, "Валюта не найдена.")
        connection.execute(
            """
            UPDATE events
            SET reward_type = 'currency', reward_currency_code = ?, reward_amount = ?, reward_pack_id = NULL, reward_card_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (currency_code, amount, event_id),
        )
        connection.commit()
    return AdminActionResult(True, "✅ Награда обновлена.")


async def update_event_reward_pack(event_id: int, pack_id: int, amount: int) -> AdminActionResult:
    with get_connection() as connection:
        pack = connection.execute("SELECT id FROM packs WHERE id = ?", (pack_id,)).fetchone()
        if pack is None:
            return AdminActionResult(False, "Пак не найден.")
        connection.execute(
            """
            UPDATE events
            SET reward_type = 'pack', reward_currency_code = NULL, reward_amount = ?, reward_pack_id = ?, reward_card_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (amount, pack_id, event_id),
        )
        connection.commit()
    return AdminActionResult(True, "✅ Награда обновлена.")


async def update_event_reward_card(event_id: int, card_id: int, amount: int) -> AdminActionResult:
    with get_connection() as connection:
        card = connection.execute("SELECT id FROM cards WHERE id = ?", (card_id,)).fetchone()
        if card is None:
            return AdminActionResult(False, "Карточка не найдена.")
        connection.execute(
            """
            UPDATE events
            SET reward_type = 'card', reward_currency_code = NULL, reward_amount = ?, reward_pack_id = NULL, reward_card_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (amount, card_id, event_id),
        )
        connection.commit()
    return AdminActionResult(True, "✅ Награда обновлена.")


async def get_currency_choices() -> list[ChoiceItem]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT code, name, icon
            FROM currencies
            WHERE active = 1
            ORDER BY CASE code WHEN 'coins' THEN 1 WHEN 'energy' THEN 2 WHEN 'rank_point' THEN 3 ELSE 99 END, name
            """
        ).fetchall()
    return [ChoiceItem(id=0, title=f"{row['icon']} {row['name']}", subtitle=row['code']) for row in rows]


async def get_pack_choices(page: int = 1, per_page: int = 5, search: str | None = None) -> ChoicePage:
    clean = clean_search_query(search)
    params: list[object] = []
    where = "WHERE active = 1"
    if clean:
        like = f"%{clean}%"
        where += " AND (name LIKE ? OR code LIKE ?)"
        params.extend([like, like])

    with get_connection() as connection:
        count = connection.execute(f"SELECT COUNT(*) AS total_count FROM packs {where}", params).fetchone()["total_count"]
        pages = calculate_pages(int(count), per_page)
        safe_page = min(max(1, page), pages)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            f"""
            SELECT id, name, code, price_amount, image_path
            FROM packs
            {where}
            ORDER BY name
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return ChoicePage(
        items=[ChoiceItem(id=row["id"], title=row["name"], subtitle=row["code"], image_path=row["image_path"]) for row in rows],
        page=safe_page,
        pages_count=pages,
        total_count=int(count),
        search=clean or None,
    )


async def get_card_choices(page: int = 1, per_page: int = 5, search: str | None = None) -> ChoicePage:
    clean = clean_search_query(search)
    params: list[object] = []
    where = "WHERE cards.active = 1"
    if clean:
        like = f"%{clean}%"
        where += " AND (cards.name LIKE ? OR cards.team LIKE ? OR cards.country LIKE ? OR collections.name LIKE ? OR cards.rarity LIKE ? OR CAST(cards.id AS TEXT) LIKE ?)"
        params.extend([like, like, like, like, like, like])

    with get_connection() as connection:
        count = connection.execute(
            f"SELECT COUNT(*) AS total_count FROM cards JOIN collections ON collections.id = cards.collection_id {where}",
            params,
        ).fetchone()["total_count"]
        pages = calculate_pages(int(count), per_page)
        safe_page = min(max(1, page), pages)
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


async def get_announcement_recipients() -> list[int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT telegram_id
            FROM users
            WHERE is_banned = 0
            """
        ).fetchall()
    return [int(row["telegram_id"]) for row in rows]


async def mark_event_announced(event_id: int) -> None:
    with get_connection() as connection:
        connection.execute("UPDATE events SET announcement_sent = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))
        connection.commit()
