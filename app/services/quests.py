from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Literal

from app.database.db import get_connection
from app.services.users import get_player_profile_by_telegram_id


QuestPeriod = Literal["daily", "seasonal"]
TARGET_TYPES = {"matches_played", "matches_won", "goals_scored", "shutout_wins"}
PERIOD_TYPES = {"daily", "seasonal"}

TARGET_TYPE_TITLES = {
    "matches_played": "сыграть матчи",
    "matches_won": "выиграть матчи",
    "goals_scored": "забить голы",
    "shutout_wins": "сухие победы",
}

PERIOD_TYPE_TITLES = {
    "daily": "ежедневное",
    "seasonal": "сезонное",
}


@dataclass(frozen=True)
class QuestProgressItem:
    progress_id: int
    quest_id: int
    code: str
    title: str
    description: str
    period_type: str
    target_type: str
    target_value: int
    progress: int
    completed: bool
    reward_claimed: bool
    bp_reward: int
    coins_reward: int


@dataclass(frozen=True)
class QuestList:
    period_type: QuestPeriod
    period_key: str
    items: list[QuestProgressItem]


@dataclass(frozen=True)
class QuestMainInfo:
    bp_points: int
    hockey_pass_level: int
    daily_total: int
    daily_completed: int
    seasonal_total: int
    seasonal_completed: int


@dataclass(frozen=True)
class QuestRewardResult:
    success: bool
    message: str
    period_type: QuestPeriod = "daily"
    bp_reward: int = 0
    coins_reward: int = 0


@dataclass(frozen=True)
class AdminQuestItem:
    id: int
    code: str
    title: str
    period_type: str
    target_type: str
    target_value: int
    bp_reward: int
    coins_reward: int
    active: bool


@dataclass(frozen=True)
class AdminQuestPage:
    items: list[AdminQuestItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None = None


@dataclass(frozen=True)
class AdminQuestProfile:
    id: int
    code: str
    title: str
    description: str
    period_type: str
    target_type: str
    target_value: int
    bp_reward: int
    coins_reward: int
    active: bool
    sort_order: int
    progress_count: int
    completed_count: int
    claimed_count: int


@dataclass(frozen=True)
class QuestDraft:
    title: str
    description: str
    period_type: str
    target_type: str
    target_value: int
    bp_reward: int
    coins_reward: int


@dataclass(frozen=True)
class AdminActionResult:
    success: bool
    message: str


def get_daily_period_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_period_key(period_type: str) -> str:
    if period_type == "daily":
        return get_daily_period_key()

    return "season-1"


def calculate_pass_level(bp_points: int) -> int:
    return min(40, max(1, bp_points // 5 + 1))


def normalize_code(value: str) -> str:
    safe_chars: list[str] = []

    for char in value.lower().strip():
        if char.isalnum():
            safe_chars.append(char)
        elif char in {" ", "-", "_"}:
            safe_chars.append("_")

    code = "".join(safe_chars).strip("_")

    while "__" in code:
        code = code.replace("__", "_")

    return code or "quest"


def make_unique_quest_code(connection, title: str, period_type: str) -> str:
    base_code = normalize_code(f"{period_type}_{title}")
    code = base_code
    counter = 1

    while connection.execute("SELECT 1 FROM quests WHERE code = ?", (code,)).fetchone() is not None:
        counter += 1
        code = f"{base_code}_{counter}"

    return code


def row_to_quest_item(row) -> QuestProgressItem:
    return QuestProgressItem(
        progress_id=row["progress_id"],
        quest_id=row["quest_id"],
        code=row["code"],
        title=row["title"],
        description=row["description"],
        period_type=row["period_type"],
        target_type=row["target_type"],
        target_value=row["target_value"],
        progress=row["progress"],
        completed=bool(row["completed"]),
        reward_claimed=bool(row["reward_claimed"]),
        bp_reward=row["bp_reward"],
        coins_reward=row["coins_reward"],
    )


def row_to_admin_quest_item(row) -> AdminQuestItem:
    return AdminQuestItem(
        id=row["id"],
        code=row["code"],
        title=row["title"],
        period_type=row["period_type"],
        target_type=row["target_type"],
        target_value=row["target_value"],
        bp_reward=row["bp_reward"],
        coins_reward=row["coins_reward"],
        active=bool(row["active"]),
    )


def ensure_user_quest_progress(connection, user_id: int, period_type: str) -> None:
    period_key = get_period_key(period_type)
    quest_rows = connection.execute(
        """
        SELECT id
        FROM quests
        WHERE active = 1
          AND period_type = ?
        """,
        (period_type,),
    ).fetchall()

    for row in quest_rows:
        connection.execute(
            """
            INSERT OR IGNORE INTO user_quest_progress (user_id, quest_id, period_key)
            VALUES (?, ?, ?)
            """,
            (user_id, row["id"], period_key),
        )


async def get_quest_main_info(telegram_id: int) -> QuestMainInfo | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    with get_connection() as connection:
        ensure_user_quest_progress(connection, profile.id, "daily")
        ensure_user_quest_progress(connection, profile.id, "seasonal")
        connection.commit()

        daily = get_completion_summary(connection, profile.id, "daily")
        seasonal = get_completion_summary(connection, profile.id, "seasonal")

    return QuestMainInfo(
        bp_points=profile.bp_points,
        hockey_pass_level=profile.hockey_pass_level,
        daily_total=daily["total"],
        daily_completed=daily["completed"],
        seasonal_total=seasonal["total"],
        seasonal_completed=seasonal["completed"],
    )


def get_completion_summary(connection, user_id: int, period_type: str) -> dict[str, int]:
    period_key = get_period_key(period_type)
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN uqp.completed = 1 THEN 1 ELSE 0 END) AS completed
        FROM quests q
        JOIN user_quest_progress uqp ON uqp.quest_id = q.id
        WHERE q.active = 1
          AND q.period_type = ?
          AND uqp.user_id = ?
          AND uqp.period_key = ?
        """,
        (period_type, user_id, period_key),
    ).fetchone()

    return {
        "total": int(row["total"] or 0),
        "completed": int(row["completed"] or 0),
    }


async def get_user_quests(telegram_id: int, period_type: QuestPeriod) -> QuestList | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    period_key = get_period_key(period_type)

    with get_connection() as connection:
        ensure_user_quest_progress(connection, profile.id, period_type)
        connection.commit()

        rows = connection.execute(
            """
            SELECT
                uqp.id AS progress_id,
                q.id AS quest_id,
                q.code,
                q.title,
                q.description,
                q.period_type,
                q.target_type,
                q.target_value,
                uqp.progress,
                uqp.completed,
                uqp.reward_claimed,
                q.bp_reward,
                q.coins_reward
            FROM quests q
            JOIN user_quest_progress uqp ON uqp.quest_id = q.id
            WHERE q.active = 1
              AND q.period_type = ?
              AND uqp.user_id = ?
              AND uqp.period_key = ?
            ORDER BY q.sort_order ASC, q.id ASC
            """,
            (period_type, profile.id, period_key),
        ).fetchall()

    return QuestList(
        period_type=period_type,
        period_key=period_key,
        items=[row_to_quest_item(row) for row in rows],
    )


def get_match_increment(target_type: str, is_win: bool, goals_scored: int, goals_allowed: int) -> int:
    if target_type == "matches_played":
        return 1

    if target_type == "matches_won":
        return 1 if is_win else 0

    if target_type == "goals_scored":
        return max(0, goals_scored)

    if target_type == "shutout_wins":
        return 1 if is_win and goals_allowed == 0 else 0

    return 0


async def apply_match_quest_progress(
    *,
    user_id: int,
    is_win: bool,
    goals_scored: int,
    goals_allowed: int,
) -> None:
    with get_connection() as connection:
        quests = connection.execute(
            """
            SELECT id, period_type, target_type, target_value
            FROM quests
            WHERE active = 1
              AND target_type IN ('matches_played', 'matches_won', 'goals_scored', 'shutout_wins')
            """
        ).fetchall()

        for quest in quests:
            increment = get_match_increment(
                target_type=quest["target_type"],
                is_win=is_win,
                goals_scored=goals_scored,
                goals_allowed=goals_allowed,
            )

            if increment <= 0:
                continue

            period_key = get_period_key(quest["period_type"])
            connection.execute(
                """
                INSERT OR IGNORE INTO user_quest_progress (user_id, quest_id, period_key)
                VALUES (?, ?, ?)
                """,
                (user_id, quest["id"], period_key),
            )
            progress_row = connection.execute(
                """
                SELECT id, progress, completed, reward_claimed
                FROM user_quest_progress
                WHERE user_id = ?
                  AND quest_id = ?
                  AND period_key = ?
                """,
                (user_id, quest["id"], period_key),
            ).fetchone()

            if progress_row is None or progress_row["reward_claimed"]:
                continue

            new_progress = min(int(quest["target_value"]), int(progress_row["progress"]) + increment)
            completed = 1 if new_progress >= int(quest["target_value"]) else int(progress_row["completed"])

            connection.execute(
                """
                UPDATE user_quest_progress
                SET progress = ?,
                    completed = ?,
                    completed_at = CASE WHEN ? = 1 AND completed = 0 THEN CURRENT_TIMESTAMP ELSE completed_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_progress, completed, completed, progress_row["id"]),
            )

        connection.commit()


async def claim_quest_reward(telegram_id: int, progress_id: int) -> QuestRewardResult:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return QuestRewardResult(False, "Открой игру через /start.")

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                uqp.id,
                uqp.user_id,
                uqp.completed,
                uqp.reward_claimed,
                q.period_type,
                q.bp_reward,
                q.coins_reward
            FROM user_quest_progress uqp
            JOIN quests q ON q.id = uqp.quest_id
            WHERE uqp.id = ?
              AND uqp.user_id = ?
              AND q.active = 1
            """,
            (progress_id, profile.id),
        ).fetchone()

        if row is None:
            return QuestRewardResult(False, "Задание уже недоступно.")

        if not row["completed"]:
            return QuestRewardResult(False, "Задание ещё не выполнено.", period_type=row["period_type"])

        if row["reward_claimed"]:
            return QuestRewardResult(False, "Награда уже получена.", period_type=row["period_type"])

        bp_reward = int(row["bp_reward"] or 0)
        coins_reward = int(row["coins_reward"] or 0)
        new_bp_points = int(profile.bp_points) + bp_reward
        new_pass_level = calculate_pass_level(new_bp_points)

        connection.execute(
            """
            UPDATE user_quest_progress
            SET reward_claimed = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_id,),
        )
        connection.execute(
            """
            UPDATE users
            SET bp_points = ?,
                hockey_pass_level = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_bp_points, new_pass_level, profile.id),
        )

        if coins_reward > 0:
            connection.execute(
                """
                INSERT INTO currency_balances (user_id, currency_code, amount)
                VALUES (?, 'coins', ?)
                ON CONFLICT(user_id, currency_code) DO UPDATE SET
                    amount = amount + excluded.amount,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (profile.id, coins_reward),
            )

        connection.commit()

    return QuestRewardResult(
        True,
        "Награда получена.",
        period_type=row["period_type"],
        bp_reward=bp_reward,
        coins_reward=coins_reward,
    )


async def get_admin_quests_page(page: int, per_page: int, search: str | None = None) -> AdminQuestPage:
    page = max(1, page)
    query = (search or "").strip()
    where_parts: list[str] = []
    params: list[object] = []

    if query:
        like = f"%{query}%"
        where_parts.append(
            """
            (title LIKE ? OR description LIKE ? OR code LIKE ? OR period_type LIKE ? OR target_type LIKE ?)
            """
        )
        params.extend([like, like, like, like, like])

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    with get_connection() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS count FROM quests {where_sql}",
            params,
        ).fetchone()
        total_count = int(total_row["count"] or 0)
        pages_count = max(1, ceil(total_count / per_page))
        page = min(page, pages_count)
        offset = (page - 1) * per_page

        rows = connection.execute(
            f"""
            SELECT id, code, title, period_type, target_type, target_value, bp_reward, coins_reward, active
            FROM quests
            {where_sql}
            ORDER BY active DESC, period_type ASC, sort_order ASC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    return AdminQuestPage(
        items=[row_to_admin_quest_item(row) for row in rows],
        page=page,
        pages_count=pages_count,
        total_count=total_count,
        search=query or None,
    )


async def get_admin_quest_profile(quest_id: int) -> AdminQuestProfile | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                q.id,
                q.code,
                q.title,
                q.description,
                q.period_type,
                q.target_type,
                q.target_value,
                q.bp_reward,
                q.coins_reward,
                q.active,
                q.sort_order,
                COUNT(uqp.id) AS progress_count,
                SUM(CASE WHEN uqp.completed = 1 THEN 1 ELSE 0 END) AS completed_count,
                SUM(CASE WHEN uqp.reward_claimed = 1 THEN 1 ELSE 0 END) AS claimed_count
            FROM quests q
            LEFT JOIN user_quest_progress uqp ON uqp.quest_id = q.id
            WHERE q.id = ?
            GROUP BY q.id
            """,
            (quest_id,),
        ).fetchone()

    if row is None:
        return None

    return AdminQuestProfile(
        id=row["id"],
        code=row["code"],
        title=row["title"],
        description=row["description"],
        period_type=row["period_type"],
        target_type=row["target_type"],
        target_value=row["target_value"],
        bp_reward=row["bp_reward"],
        coins_reward=row["coins_reward"],
        active=bool(row["active"]),
        sort_order=row["sort_order"],
        progress_count=int(row["progress_count"] or 0),
        completed_count=int(row["completed_count"] or 0),
        claimed_count=int(row["claimed_count"] or 0),
    )


async def create_admin_quest(draft: QuestDraft) -> int:
    with get_connection() as connection:
        sort_row = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 AS next_order FROM quests WHERE period_type = ?",
            (draft.period_type,),
        ).fetchone()
        code = make_unique_quest_code(connection, draft.title, draft.period_type)
        cursor = connection.execute(
            """
            INSERT INTO quests (
                code,
                title,
                description,
                period_type,
                target_type,
                target_value,
                bp_reward,
                coins_reward,
                active,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                code,
                draft.title.strip(),
                draft.description.strip(),
                draft.period_type,
                draft.target_type,
                draft.target_value,
                draft.bp_reward,
                draft.coins_reward,
                int(sort_row["next_order"] or 10),
            ),
        )
        quest_id = int(cursor.lastrowid)
        connection.commit()

    return quest_id


async def toggle_admin_quest_active(quest_id: int) -> AdminActionResult:
    profile = await get_admin_quest_profile(quest_id)

    if profile is None:
        return AdminActionResult(False, "Задание не найдено.")

    new_value = 0 if profile.active else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE quests
            SET active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_value, quest_id),
        )
        connection.commit()

    return AdminActionResult(True, "Статус задания обновлён.")


async def delete_admin_quest(quest_id: int) -> AdminActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM quests WHERE id = ?", (quest_id,)).fetchone()

        if row is None:
            return AdminActionResult(False, "Задание не найдено.")

        connection.execute("DELETE FROM quests WHERE id = ?", (quest_id,))
        connection.commit()

    return AdminActionResult(True, "Задание удалено.")


async def update_admin_quest_text_field(quest_id: int, field: str, value: str) -> AdminActionResult:
    if field not in {"title", "description"}:
        return AdminActionResult(False, "Поле недоступно.")

    text = value.strip()

    if field == "title" and not validate_quest_title(text):
        return AdminActionResult(False, "Название должно быть от 3 до 80 символов.")

    if field == "description" and not validate_quest_description(text):
        return AdminActionResult(False, "Описание должно быть до 300 символов.")

    with get_connection() as connection:
        connection.execute(
            f"""
            UPDATE quests
            SET {field} = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (text, quest_id),
        )
        connection.commit()

    return AdminActionResult(True, "Задание обновлено.")


async def update_admin_quest_number_field(quest_id: int, field: str, value: int) -> AdminActionResult:
    if field not in {"target_value", "bp_reward", "coins_reward"}:
        return AdminActionResult(False, "Поле недоступно.")

    if field == "target_value" and not validate_positive_int(value, 1, 100000):
        return AdminActionResult(False, "Цель должна быть от 1 до 100000.")

    if field == "bp_reward" and not validate_positive_int(value, 0, 100000):
        return AdminActionResult(False, "BP Points должны быть от 0 до 100000.")

    if field == "coins_reward" and not validate_positive_int(value, 0, 1000000000):
        return AdminActionResult(False, "Coins должны быть от 0 до 1000000000.")

    with get_connection() as connection:
        connection.execute(
            f"""
            UPDATE quests
            SET {field} = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (value, quest_id),
        )
        connection.commit()

    return AdminActionResult(True, "Задание обновлено.")


async def update_admin_quest_choice_field(quest_id: int, field: str, value: str) -> AdminActionResult:
    if field == "period_type" and value not in PERIOD_TYPES:
        return AdminActionResult(False, "Тип задания недоступен.")

    if field == "target_type" and value not in TARGET_TYPES:
        return AdminActionResult(False, "Цель задания недоступна.")

    if field not in {"period_type", "target_type"}:
        return AdminActionResult(False, "Поле недоступно.")

    with get_connection() as connection:
        connection.execute(
            f"""
            UPDATE quests
            SET {field} = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (value, quest_id),
        )
        connection.commit()

    return AdminActionResult(True, "Задание обновлено.")


def validate_quest_title(value: str) -> bool:
    text = value.strip()
    return 3 <= len(text) <= 80


def validate_quest_description(value: str) -> bool:
    return len(value.strip()) <= 300


def validate_positive_int(value: int, min_value: int = 0, max_value: int = 1000000000) -> bool:
    return min_value <= value <= max_value


def parse_int_value(value: str) -> int | None:
    text = value.strip().replace(" ", "")

    if not text.isdigit():
        return None

    return int(text)
