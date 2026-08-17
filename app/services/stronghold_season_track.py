"""Season Track (Event XP -> уровни -> награды) THE STRONGHOLD.

Модель по аналогии с `hockey_passes`/`hockey_pass_rewards`, но отдельная таблица под
событие (см. docs/THE_STRONGHOLD_SPEC.md, раздел 8). Суммарно выдаёт 50 FT.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.rewards import grant_pack
from app.services.stronghold_common import COINS_CURRENCY_CODE, FT_CURRENCY_CODE, StrongholdError, get_active_event
from app.services.stronghold_wallet import credit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeasonLevelInfo:
    id: int
    level: int
    xp_threshold: int
    reward_ft: int
    reward_coins: int
    reward_pack_id: int | None
    title: str
    status: str


@dataclass(frozen=True)
class SeasonTrackInfo:
    xp: int
    current_level: int
    levels: list[SeasonLevelInfo]


@dataclass(frozen=True)
class SeasonClaimResult:
    success: bool
    reward_ft: int
    reward_coins: int


async def get_track(user_id: int) -> SeasonTrackInfo:
    event = await get_active_event()
    if event is None:
        return SeasonTrackInfo(xp=0, current_level=0, levels=[])

    with get_connection() as connection:
        progress_row = connection.execute(
            "SELECT xp FROM stronghold_user_season_progress WHERE user_id = ? AND event_id = ?",
            (user_id, event.id),
        ).fetchone()
        xp = int(progress_row["xp"]) if progress_row else 0

        level_rows = connection.execute(
            "SELECT * FROM stronghold_season_track_levels WHERE event_id = ? ORDER BY level",
            (event.id,),
        ).fetchall()
        claimed_ids = {
            int(row["season_level_id"])
            for row in connection.execute(
                """
                SELECT ussc.season_level_id
                FROM stronghold_user_season_claims ussc
                JOIN stronghold_season_track_levels l ON l.id = ussc.season_level_id
                WHERE ussc.user_id = ? AND l.event_id = ?
                """,
                (user_id, event.id),
            ).fetchall()
        }

    levels: list[SeasonLevelInfo] = []
    current_level = 0
    for row in level_rows:
        level_id = int(row["id"])
        threshold = int(row["xp_threshold"])
        if level_id in claimed_ids:
            status = "CLAIMED"
        elif xp >= threshold:
            status = "AVAILABLE"
        else:
            status = "LOCKED"
        if xp >= threshold:
            current_level = int(row["level"])
        levels.append(
            SeasonLevelInfo(
                id=level_id,
                level=int(row["level"]),
                xp_threshold=threshold,
                reward_ft=int(row["reward_ft"]),
                reward_coins=int(row["reward_coins"]),
                reward_pack_id=row["reward_pack_id"],
                title=row["title"] or "",
                status=status,
            )
        )

    return SeasonTrackInfo(xp=xp, current_level=current_level, levels=levels)


async def add_event_xp(user_id: int, amount: int) -> None:
    if amount <= 0:
        return
    event = await get_active_event()
    if event is None or event.status != "ACTIVE":
        return
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO stronghold_user_season_progress (user_id, event_id, xp)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, event_id) DO UPDATE SET
                xp = xp + excluded.xp,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, event.id, amount),
        )
        connection.commit()


async def claim_level(user_id: int, season_level_id: int) -> SeasonClaimResult:
    event = await get_active_event()
    if event is None:
        raise StrongholdError("SEASON_LEVEL_LOCKED", "Событие недоступно.")
    if event.status not in ("ACTIVE", "GRACE_PERIOD"):
        raise StrongholdError("SEASON_LEVEL_LOCKED", "Season Track сейчас недоступен.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        level_row = connection.execute(
            "SELECT * FROM stronghold_season_track_levels WHERE id = ? AND event_id = ?",
            (season_level_id, event.id),
        ).fetchone()
        if level_row is None:
            raise StrongholdError("SEASON_LEVEL_LOCKED", "Уровень не найден.")

        progress_row = connection.execute(
            "SELECT xp FROM stronghold_user_season_progress WHERE user_id = ? AND event_id = ?",
            (user_id, event.id),
        ).fetchone()
        xp = int(progress_row["xp"]) if progress_row else 0
        if xp < int(level_row["xp_threshold"]):
            raise StrongholdError("SEASON_LEVEL_LOCKED", "Уровень ещё не открыт.")

        cursor = connection.execute(
            "INSERT OR IGNORE INTO stronghold_user_season_claims (user_id, season_level_id) VALUES (?, ?)",
            (user_id, season_level_id),
        )
        if cursor.rowcount == 0:
            raise StrongholdError("SEASON_REWARD_ALREADY_CLAIMED", "Награда уже получена.")

        reward_ft = int(level_row["reward_ft"])
        reward_coins = int(level_row["reward_coins"])
        if reward_coins > 0:
            credit(connection, user_id=user_id, event_id=event.id, currency_code=COINS_CURRENCY_CODE,
                   amount=reward_coins, reason="season_track_reward", reference_type="season_level", reference_id=season_level_id)
        if reward_ft > 0:
            credit(connection, user_id=user_id, event_id=event.id, currency_code=FT_CURRENCY_CODE,
                   amount=reward_ft, reason="season_track_reward", reference_type="season_level", reference_id=season_level_id)
        if level_row["reward_pack_id"] is not None:
            grant_pack(connection, user_id, int(level_row["reward_pack_id"]), 1)

        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, reason)
            VALUES (?, NULL, 'season_track_claim', 'stronghold_season_track_levels', ?, 'user_action')
            """,
            (event.id, season_level_id),
        )
        connection.commit()

    return SeasonClaimResult(success=True, reward_ft=reward_ft, reward_coins=reward_coins)
