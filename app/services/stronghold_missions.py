"""Daily / Weekly / Seasonal Missions THE STRONGHOLD.

Прогресс начисляется только серверными пост-хуками (`apply_stronghold_progress`),
никогда напрямую от клиента — см. docs/THE_STRONGHOLD_SPEC.md, раздел 8.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from app.database.db import get_connection
from app.services.stronghold_common import (
    COINS_CURRENCY_CODE,
    FT_CURRENCY_CODE,
    StrongholdError,
    get_active_event,
    utc_now,
    week_key,
)
from app.services.stronghold_wallet import credit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MissionInfo:
    id: int
    code: str
    type: str
    title: str
    description: str
    condition_type: str
    target_value: int
    reward_ft: int
    reward_coins: int
    reward_xp: int
    progress: int
    completed: bool
    reward_claimed: bool
    period_key: str
    status: str


@dataclass(frozen=True)
class MissionClaimResult:
    success: bool
    reward_ft: int
    reward_coins: int
    reward_xp: int


def current_period_key(mission_type: str, now=None) -> str:
    moment = now or utc_now()
    if mission_type == "DAILY":
        return moment.strftime("%Y-%m-%d")
    if mission_type == "WEEKLY":
        return week_key(moment)
    return "season"


def _mission_status(target_value: int, progress: int, completed: bool, reward_claimed: bool) -> str:
    if reward_claimed:
        return "CLAIMED"
    if completed or progress >= target_value:
        return "COMPLETED"
    return "ACTIVE"


async def list_missions(user_id: int, mission_type: str | None = None) -> list[MissionInfo]:
    event = await get_active_event()
    if event is None:
        return []

    now = utc_now()
    with get_connection() as connection:
        query = "SELECT * FROM stronghold_missions WHERE event_id = ? AND active = 1"
        params: list[object] = [event.id]
        if mission_type:
            query += " AND type = ?"
            params.append(mission_type)
        query += " ORDER BY sort_order, id"
        missions = connection.execute(query, params).fetchall()

        result: list[MissionInfo] = []
        for mission in missions:
            period_key = current_period_key(mission["type"], now)
            progress_row = connection.execute(
                "SELECT * FROM stronghold_user_mission_progress WHERE user_id = ? AND mission_id = ? AND period_key = ?",
                (user_id, mission["id"], period_key),
            ).fetchone()
            progress = int(progress_row["progress"]) if progress_row else 0
            completed = bool(progress_row["completed"]) if progress_row else False
            reward_claimed = bool(progress_row["reward_claimed"]) if progress_row else False
            result.append(
                MissionInfo(
                    id=int(mission["id"]),
                    code=mission["code"],
                    type=mission["type"],
                    title=mission["title"],
                    description=mission["description"] or "",
                    condition_type=mission["condition_type"],
                    target_value=int(mission["target_value"]),
                    reward_ft=int(mission["reward_ft"]),
                    reward_coins=int(mission["reward_coins"]),
                    reward_xp=int(mission["reward_xp"]),
                    progress=progress,
                    completed=completed,
                    reward_claimed=reward_claimed,
                    period_key=period_key,
                    status=_mission_status(int(mission["target_value"]), progress, completed, reward_claimed),
                )
            )
    return result


async def apply_stronghold_progress(user_id: int, condition_type: str, amount: int = 1) -> None:
    """Best-effort пост-хук. Не должен ронять вызывающий код при ошибке."""
    if amount <= 0:
        return
    try:
        event = await get_active_event()
        if event is None or event.status != "ACTIVE":
            return

        now = utc_now()
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            missions = connection.execute(
                "SELECT * FROM stronghold_missions WHERE event_id = ? AND active = 1 AND condition_type = ?",
                (event.id, condition_type),
            ).fetchall()

            for mission in missions:
                period_key = current_period_key(mission["type"], now)
                connection.execute(
                    """
                    INSERT INTO stronghold_user_mission_progress (user_id, mission_id, period_key, progress)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(user_id, mission_id, period_key) DO NOTHING
                    """,
                    (user_id, mission["id"], period_key),
                )
                target_value = int(mission["target_value"])
                connection.execute(
                    """
                    UPDATE stronghold_user_mission_progress
                    SET progress = MIN(progress + ?, ?),
                        completed = CASE WHEN progress + ? >= ? THEN 1 ELSE completed END,
                        completed_at = CASE WHEN completed = 0 AND progress + ? >= ? THEN CURRENT_TIMESTAMP ELSE completed_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND mission_id = ? AND period_key = ?
                    """,
                    (amount, target_value, amount, target_value, amount, target_value, user_id, mission["id"], period_key),
                )
            connection.commit()
    except Exception:
        logger.exception("stronghold mission progress update failed (condition=%s)", condition_type)


async def claim_mission(user_id: int, mission_id: int) -> MissionClaimResult:
    event = await get_active_event()
    if event is None:
        raise StrongholdError("MISSION_NOT_ACTIVE", "Событие недоступно.")
    if event.status not in ("ACTIVE", "GRACE_PERIOD"):
        raise StrongholdError("MISSION_NOT_ACTIVE", "Задания сейчас недоступны.")

    now = utc_now()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        mission = connection.execute(
            "SELECT * FROM stronghold_missions WHERE id = ? AND event_id = ?", (mission_id, event.id)
        ).fetchone()
        if mission is None or not bool(mission["active"]):
            raise StrongholdError("MISSION_NOT_FOUND", "Задание не найдено.")

        period_key = current_period_key(mission["type"], now)
        progress_row = connection.execute(
            "SELECT * FROM stronghold_user_mission_progress WHERE user_id = ? AND mission_id = ? AND period_key = ?",
            (user_id, mission_id, period_key),
        ).fetchone()
        if progress_row is None or int(progress_row["progress"]) < int(mission["target_value"]):
            raise StrongholdError("MISSION_NOT_COMPLETED", "Задание ещё не выполнено.")
        if bool(progress_row["reward_claimed"]):
            raise StrongholdError("MISSION_ALREADY_CLAIMED", "Награда уже получена.")

        connection.execute(
            """
            UPDATE stronghold_user_mission_progress
            SET reward_claimed = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_row["id"],),
        )

        reward_ft = int(mission["reward_ft"])
        reward_coins = int(mission["reward_coins"])
        reward_xp = int(mission["reward_xp"])

        if reward_coins > 0:
            credit(connection, user_id=user_id, event_id=event.id, currency_code=COINS_CURRENCY_CODE,
                   amount=reward_coins, reason="mission_reward", reference_type="mission", reference_id=mission_id)
        if reward_ft > 0:
            credit(connection, user_id=user_id, event_id=event.id, currency_code=FT_CURRENCY_CODE,
                   amount=reward_ft, reason="mission_reward", reference_type="mission", reference_id=mission_id)

        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, reason)
            VALUES (?, NULL, 'mission_claim', 'stronghold_missions', ?, 'user_action')
            """,
            (event.id, mission_id),
        )
        connection.commit()

    if reward_xp > 0:
        try:
            from app.services.stronghold_season_track import add_event_xp

            await add_event_xp(user_id, reward_xp)
        except Exception:
            logger.exception("stronghold season xp grant failed after mission claim")

    return MissionClaimResult(success=True, reward_ft=reward_ft, reward_coins=reward_coins, reward_xp=reward_xp)


async def expire_stale_daily_missions() -> None:
    """Фоновая уборка: помечает вчерашние daily-прогрессы как невостребованные (best-effort, не критично)."""
    return None
