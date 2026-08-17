"""Endless Siege THE STRONGHOLD: бесконечные волны после Fortress 15.

FT капается 20/неделю (серверная ISO-неделя, см. docs/THE_STRONGHOLD_SPEC.md, раздел 7).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services import match_guard
from app.services.lineup import get_lineup_overview, lineup_has_collection_card
from app.services.salary import STRONGHOLD_SALARY_CAP
from app.services.stronghold_common import FT_CURRENCY_CODE, StrongholdError, get_active_event, utc_now, week_key
from app.services.stronghold_fortress import COLLECTION_CODE
from app.services.stronghold_wallet import credit

logger = logging.getLogger(__name__)

XP_PER_ENDLESS_WIN = 5


@dataclass(frozen=True)
class EndlessConfig:
    base_opponent_ovr: int
    ovr_growth_per_wave: int
    max_opponent_ovr: int
    weekly_ft_cap: int
    ft_per_wave: int
    modifier_every_n_waves: int


@dataclass(frozen=True)
class EndlessStatus:
    unlocked: bool
    current_wave: int
    best_wave: int
    weekly_ft_earned: int
    weekly_ft_cap: int


@dataclass(frozen=True)
class EndlessWaveResult:
    success: bool
    message: str
    is_win: bool = False
    wave_number: int = 0
    opponent_ovr: int = 0
    ft_awarded: int = 0
    new_best_wave: int = 0


@dataclass(frozen=True)
class LeaderboardRow:
    rank: int
    user_id: int
    nickname: str
    best_wave: int
    achieved_at: str | None


@dataclass(frozen=True)
class LeaderboardPage:
    rows: list[LeaderboardRow]
    page: int
    pages_count: int
    total_count: int
    my_rank: int | None


def _default_config() -> EndlessConfig:
    return EndlessConfig(base_opponent_ovr=75, ovr_growth_per_wave=1, max_opponent_ovr=99, weekly_ft_cap=20, ft_per_wave=2, modifier_every_n_waves=5)


async def _get_config(event_id: int) -> EndlessConfig:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM stronghold_endless_config WHERE event_id = ?", (event_id,)).fetchone()
    if row is None:
        return _default_config()
    return EndlessConfig(
        base_opponent_ovr=int(row["base_opponent_ovr"]),
        ovr_growth_per_wave=int(row["ovr_growth_per_wave"]),
        max_opponent_ovr=int(row["max_opponent_ovr"]),
        weekly_ft_cap=int(row["weekly_ft_cap"]),
        ft_per_wave=int(row["ft_per_wave"]),
        modifier_every_n_waves=int(row["modifier_every_n_waves"]),
    )


async def _is_unlocked(user_id: int, event_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT p.status
            FROM stronghold_user_fortress_progress p
            JOIN stronghold_fortresses f ON f.id = p.fortress_id
            WHERE p.user_id = ? AND f.event_id = ? AND f.order_index = (
                SELECT MAX(order_index) FROM stronghold_fortresses WHERE event_id = ?
            )
            """,
            (user_id, event_id, event_id),
        ).fetchone()
    return row is not None and str(row["status"]) == "COMPLETED"


async def get_status(user_id: int) -> EndlessStatus:
    event = await get_active_event()
    if event is None:
        return EndlessStatus(unlocked=False, current_wave=1, best_wave=0, weekly_ft_earned=0, weekly_ft_cap=20)

    unlocked = await _is_unlocked(user_id, event.id)
    config = await _get_config(event.id)
    key = week_key()

    with get_connection() as connection:
        progress = connection.execute(
            "SELECT * FROM stronghold_user_endless_progress WHERE user_id = ? AND event_id = ?", (user_id, event.id)
        ).fetchone()
        weekly = connection.execute(
            "SELECT ft_earned FROM stronghold_endless_weekly_ft WHERE user_id = ? AND event_id = ? AND week_key = ?",
            (user_id, event.id, key),
        ).fetchone()

    return EndlessStatus(
        unlocked=unlocked,
        current_wave=int(progress["current_wave"]) if progress else 1,
        best_wave=int(progress["best_wave"]) if progress else 0,
        weekly_ft_earned=int(weekly["ft_earned"]) if weekly else 0,
        weekly_ft_cap=config.weekly_ft_cap,
    )


async def play_wave(telegram_id: int, user_id: int) -> EndlessWaveResult:
    """Публичная обёртка с структурированным логированием (см. stronghold_common.log_stronghold_operation)."""
    from app.services.stronghold_common import OperationTimer, log_stronghold_operation

    with OperationTimer() as timer:
        try:
            result = await _play_wave_impl(telegram_id, user_id)
        except StrongholdError as error:
            log_stronghold_operation(
                "endless_wave_play", user_id=user_id, result="error",
                duration_ms=timer.duration_ms, error_code=error.code,
            )
            raise
    log_stronghold_operation(
        "endless_wave_play", user_id=user_id, result="success", duration_ms=timer.duration_ms,
        wave_number=result.wave_number, is_win=result.is_win, ft_awarded=result.ft_awarded,
    )
    return result


async def _play_wave_impl(telegram_id: int, user_id: int) -> EndlessWaveResult:
    event = await get_active_event()
    if event is None or event.status != "ACTIVE":
        raise StrongholdError("EVENT_NOT_ACTIVE", "Endless Siege доступен только пока событие ACTIVE.")

    if not await _is_unlocked(user_id, event.id):
        raise StrongholdError("ENDLESS_SIEGE_LOCKED", "Endless Siege открывается после прохождения всех 15 Fortress.")

    overview = await get_lineup_overview(user_id)
    if not overview.is_complete:
        # Тот же баг, что был в stronghold_fortress.py: код ошибки не может быть
        # "EVENT_NOT_ACTIVE" для условия "состав не заполнен" — ERROR_MESSAGES в
        # app/texts/stronghold.py игнорирует переданный текст и всегда показывает
        # текст ПО КОДУ, поэтому игрок видел "Событие недоступно" вместо правды.
        raise StrongholdError("LINEUP_INCOMPLETE", "Заполните весь состав перед волной.")
    if overview.salary_total > STRONGHOLD_SALARY_CAP:
        raise StrongholdError("SALARY_CAP_EXCEEDED", "Состав превышает зарплатный потолок THE STRONGHOLD.")
    if not await lineup_has_collection_card(user_id, COLLECTION_CODE):
        raise StrongholdError("COLLECTION_CARD_REQUIRED", "В составе должна быть минимум одна карта коллекции THE STRONGHOLD.")

    config = await _get_config(event.id)
    with get_connection() as connection:
        progress = connection.execute(
            "SELECT * FROM stronghold_user_endless_progress WHERE user_id = ? AND event_id = ?", (user_id, event.id)
        ).fetchone()
    current_wave = int(progress["current_wave"]) if progress else 1
    opponent_ovr = min(config.base_opponent_ovr + (current_wave - 1) * config.ovr_growth_per_wave, config.max_opponent_ovr)
    modifiers: list[str] = []
    if config.modifier_every_n_waves > 0 and current_wave % config.modifier_every_n_waves == 0:
        modifiers.append("elite_opponent")

    lock = await match_guard.acquire_player_match_lock(user_id, "stronghold_endless")
    if not lock.acquired:
        detail = await match_guard.describe_active_match_short(lock.existing) if lock.existing else ""
        raise StrongholdError("CARD_IN_ACTIVE_MATCH", f"У вас уже идёт матч, дождитесь его завершения. {detail}".strip())

    try:
        from app.services.matches import play_stronghold_match

        match_result = await play_stronghold_match(telegram_id, opponent_ovr, f"Siege Wave {current_wave}")
    except Exception:
        await match_guard.cancel_match(user_id, reason="STRONGHOLD_ENDLESS_MATCH_ERROR")
        raise

    if not match_result.success:
        await match_guard.cancel_match(user_id, reason="STRONGHOLD_ENDLESS_MATCH_NOT_STARTED")
        return EndlessWaveResult(success=False, message=match_result.message)

    await match_guard.finalize_match(user_id, match_id=match_result.match_id, reason="COMPLETED")

    is_win = match_result.result == "win"
    ft_awarded = 0
    new_best_wave = int(progress["best_wave"]) if progress else 0

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        key = week_key()
        if is_win:
            weekly_row = connection.execute(
                "SELECT ft_earned FROM stronghold_endless_weekly_ft WHERE user_id = ? AND event_id = ? AND week_key = ?",
                (user_id, event.id, key),
            ).fetchone()
            weekly_earned = int(weekly_row["ft_earned"]) if weekly_row else 0
            ft_awarded = max(0, min(config.ft_per_wave, config.weekly_ft_cap - weekly_earned))

            connection.execute(
                """
                INSERT INTO stronghold_endless_weekly_ft (user_id, event_id, week_key, ft_earned)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, event_id, week_key) DO UPDATE SET
                    ft_earned = ft_earned + excluded.ft_earned,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, event.id, key, ft_awarded),
            )
            if ft_awarded > 0:
                credit(connection, user_id=user_id, event_id=event.id, currency_code=FT_CURRENCY_CODE,
                       amount=ft_awarded, reason="endless_siege_wave", reference_type="endless_wave", reference_id=current_wave)

            next_wave = current_wave + 1
            new_best_wave = max(new_best_wave, current_wave)
            connection.execute(
                """
                INSERT INTO stronghold_user_endless_progress (user_id, event_id, current_wave, best_wave, best_wave_achieved_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, event_id) DO UPDATE SET
                    current_wave = ?,
                    best_wave = MAX(stronghold_user_endless_progress.best_wave, ?),
                    best_wave_achieved_at = CASE WHEN ? > stronghold_user_endless_progress.best_wave THEN CURRENT_TIMESTAMP ELSE stronghold_user_endless_progress.best_wave_achieved_at END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, event.id, next_wave, new_best_wave, next_wave, new_best_wave, new_best_wave),
            )
            connection.execute(
                """
                INSERT INTO stronghold_leaderboard_entries (user_id, event_id, best_wave, achieved_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, event_id) DO UPDATE SET
                    best_wave = MAX(stronghold_leaderboard_entries.best_wave, excluded.best_wave),
                    achieved_at = CASE WHEN excluded.best_wave > stronghold_leaderboard_entries.best_wave THEN CURRENT_TIMESTAMP ELSE stronghold_leaderboard_entries.achieved_at END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, event.id, new_best_wave),
            )
        else:
            connection.execute(
                """
                INSERT INTO stronghold_user_endless_progress (user_id, event_id, current_wave, best_wave)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(user_id, event_id) DO NOTHING
                """,
                (user_id, event.id, current_wave),
            )

        connection.execute(
            """
            INSERT INTO stronghold_endless_waves (user_id, event_id, wave_number, opponent_ovr, modifiers, result, match_id, ft_awarded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, event.id, current_wave, opponent_ovr, json.dumps(modifiers), "win" if is_win else "loss", match_result.match_id, ft_awarded),
        )

        connection.commit()

    try:
        from app.services.stronghold_missions import apply_stronghold_progress
        from app.services.stronghold_season_track import add_event_xp

        await apply_stronghold_progress(user_id, "play_matches", 1)
        if is_win:
            await apply_stronghold_progress(user_id, "win_matches", 1)
            await apply_stronghold_progress(user_id, "endless_wave_complete", 1)
            await add_event_xp(user_id, XP_PER_ENDLESS_WIN)
    except Exception:
        logger.exception("stronghold endless progress hooks failed")

    return EndlessWaveResult(
        success=True,
        message=match_result.message,
        is_win=is_win,
        wave_number=current_wave,
        opponent_ovr=opponent_ovr,
        ft_awarded=ft_awarded,
        new_best_wave=new_best_wave,
    )


async def get_leaderboard(page: int = 1, per_page: int = 10, user_id: int | None = None) -> LeaderboardPage:
    event = await get_active_event()
    if event is None:
        return LeaderboardPage(rows=[], page=1, pages_count=1, total_count=0, my_rank=None)

    with get_connection() as connection:
        total_count = int(
            connection.execute(
                "SELECT COUNT(*) AS c FROM stronghold_leaderboard_entries WHERE event_id = ? AND best_wave > 0", (event.id,)
            ).fetchone()["c"]
        )
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        rows = connection.execute(
            """
            SELECT le.user_id, le.best_wave, le.achieved_at, u.nickname
            FROM stronghold_leaderboard_entries le
            JOIN users u ON u.id = le.user_id
            WHERE le.event_id = ? AND le.best_wave > 0
            ORDER BY le.best_wave DESC, le.achieved_at ASC
            LIMIT ? OFFSET ?
            """,
            (event.id, per_page, offset),
        ).fetchall()

        my_rank = None
        if user_id is not None:
            rank_row = connection.execute(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM stronghold_leaderboard_entries me
                WHERE me.event_id = ? AND me.best_wave > (
                    SELECT COALESCE(best_wave, 0) FROM stronghold_leaderboard_entries WHERE user_id = ? AND event_id = ?
                )
                """,
                (event.id, user_id, event.id),
            ).fetchone()
            has_entry = connection.execute(
                "SELECT 1 FROM stronghold_leaderboard_entries WHERE user_id = ? AND event_id = ? AND best_wave > 0",
                (user_id, event.id),
            ).fetchone()
            my_rank = int(rank_row["rank"]) if has_entry else None

    leaderboard_rows = [
        LeaderboardRow(rank=offset + index + 1, user_id=int(row["user_id"]), nickname=row["nickname"], best_wave=int(row["best_wave"]), achieved_at=row["achieved_at"])
        for index, row in enumerate(rows)
    ]
    return LeaderboardPage(rows=leaderboard_rows, page=safe_page, pages_count=pages_count, total_count=total_count, my_rank=my_rank)
