"""Fortress (15 крепостей x 6 матчей) THE STRONGHOLD.

Матчи считает существующий движок (`matches.play_stronghold_match`), эта служба
только: проверяет допуск, ведёт прогресс/звёзды/разблокировку и выдаёт FT за первое
полное прохождение (220 FT суммарно, см. docs/THE_STRONGHOLD_SPEC.md, раздел 6).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services import match_guard
from app.services.lineup import get_lineup_overview, lineup_has_collection_card
from app.services.salary import STRONGHOLD_SALARY_CAP
from app.services.stronghold_common import COINS_CURRENCY_CODE, FT_CURRENCY_CODE, StrongholdError, get_active_event
from app.services.stronghold_schedule import (
    get_fortress_unlock_at,
    get_schedule_config,
    get_total_fortress_count,
    is_fortress_unlocked,
)
from app.services.stronghold_wallet import credit

logger = logging.getLogger(__name__)

COLLECTION_CODE = "the_stronghold"
XP_PER_FORTRESS_WIN = 10


def _log_battle_blocked(reason: str, event, **extra: object) -> None:
    """Раздел диагностики: одна строка перед КАЖДЫМ отказом в запуске Fortress-боя,
    чтобы в логах Railway сразу было видно настоящую причину, а не гадать по
    пользовательскому тексту (который берётся из общего словаря по коду ошибки и не
    всегда совпадает с фактическим условием — см. LINEUP_INCOMPLETE ниже)."""
    event_status = event.status if event is not None else "UNKNOWN"
    config_version = event.config_version if event is not None else "?"
    extra_text = " ".join(f"{key}={value}" for key, value in extra.items())
    logger.warning(
        "[STRONGHOLD_BATTLE_BLOCKED] reason=%s event_status=%s config=%s%s",
        reason, event_status, config_version, f" {extra_text}" if extra_text else "",
    )


@dataclass(frozen=True)
class FortressMatchInfo:
    id: int
    fortress_id: int
    order_index: int
    opponent_name: str
    opponent_ovr: int
    status: str
    stars: int
    attempts: int


@dataclass(frozen=True)
class FortressInfo:
    id: int
    order_index: int
    code: str
    title: str
    description: str
    is_boss: bool
    first_completion_ft: int
    repeat_coins_reward: int
    status: str
    stars_total: int
    first_completion_reward_claimed: bool
    matches: list[FortressMatchInfo]
    unlock_at: str | None = None


@dataclass(frozen=True)
class FortressMatchPlayResult:
    success: bool
    message: str
    is_win: bool = False
    user_score: int = 0
    opponent_score: int = 0
    stars: int = 0
    fortress_completed_now: bool = False
    ft_awarded: int = 0
    coins_awarded: int = 0


def evaluate_stars(star_rules: list[dict], *, is_win: bool, user_score: int, opponent_score: int) -> int:
    if not is_win:
        return 0
    stars = 0
    for rule in star_rules:
        rule_type = rule.get("type")
        if rule_type == "win":
            stars += 1
        elif rule_type == "goal_diff" and (user_score - opponent_score) >= int(rule.get("min", 1)):
            stars += 1
        elif rule_type == "clean_sheet" and opponent_score <= int(rule.get("max_allowed", 0)):
            stars += 1
        elif rule_type == "use_collection_card":
            stars += 1
    return min(stars, 3)


def _match_status_for(row: sqlite3.Row | None, unlocked: bool) -> tuple[str, int, int]:
    if row is None:
        return ("AVAILABLE" if unlocked else "LOCKED"), 0, 0
    return str(row["status"]), int(row["stars"]), int(row["attempts"])


async def list_fortresses(user_id: int) -> list[FortressInfo]:
    event = await get_active_event()
    if event is None:
        return []

    with get_connection() as connection:
        fortresses = connection.execute(
            "SELECT * FROM stronghold_fortresses WHERE event_id = ? AND active = 1 ORDER BY order_index",
            (event.id,),
        ).fetchall()
        progress_rows = {
            int(row["fortress_id"]): row
            for row in connection.execute(
                "SELECT * FROM stronghold_user_fortress_progress WHERE user_id = ? AND event_id = ?",
                (user_id, event.id),
            ).fetchall()
        }
        schedule_config = get_schedule_config(connection, event.id)
        total_fortresses = get_total_fortress_count(connection, event.id)

        result: list[FortressInfo] = []
        for fortress in fortresses:
            progress = progress_rows.get(int(fortress["id"]))
            order_index = int(fortress["order_index"])
            # ГЛОБАЛЬНОЕ РАСПИСАНИЕ БАШЕН: доступность башни определяется ТОЛЬКО
            # датой (см. app/services/stronghold_schedule.py) — НЕ прогрессом
            # прохождения предыдущей башни (ТЗ "не зависит от ... личного прогресса").
            time_unlocked = (
                schedule_config is not None
                and is_fortress_unlocked(schedule_config, order_index, total_fortresses)
            )
            if progress is not None:
                status = str(progress["status"])
            else:
                status = "AVAILABLE" if time_unlocked else "LOCKED"
            unlock_at = None
            if not time_unlocked and schedule_config is not None:
                unlock_dt = get_fortress_unlock_at(schedule_config, order_index)
                unlock_at = unlock_dt.strftime("%Y-%m-%d %H:%M:%S") if unlock_dt else None
            result.append(
                FortressInfo(
                    id=int(fortress["id"]),
                    order_index=order_index,
                    code=fortress["code"],
                    title=fortress["title"],
                    description=fortress["description"] or "",
                    is_boss=bool(fortress["is_boss"]),
                    first_completion_ft=int(fortress["first_completion_ft"]),
                    repeat_coins_reward=int(fortress["repeat_coins_reward"]),
                    status=status,
                    stars_total=int(progress["stars_total"]) if progress else 0,
                    first_completion_reward_claimed=bool(progress["first_completion_reward_claimed"]) if progress else False,
                    matches=[],
                    unlock_at=unlock_at,
                )
            )
    return result


async def get_fortress(user_id: int, fortress_id: int) -> FortressInfo | None:
    event = await get_active_event()
    if event is None:
        return None

    with get_connection() as connection:
        fortress = connection.execute(
            "SELECT * FROM stronghold_fortresses WHERE id = ? AND event_id = ?", (fortress_id, event.id)
        ).fetchone()
        if fortress is None:
            return None

        schedule_config = get_schedule_config(connection, event.id)
        total_fortresses = get_total_fortress_count(connection, event.id)
        fortress_unlocked = schedule_config is not None and is_fortress_unlocked(
            schedule_config, int(fortress["order_index"]), total_fortresses
        )
        unlock_at = None
        if not fortress_unlocked and schedule_config is not None:
            unlock_dt = get_fortress_unlock_at(schedule_config, int(fortress["order_index"]))
            unlock_at = unlock_dt.strftime("%Y-%m-%d %H:%M:%S") if unlock_dt else None

        fortress_progress = connection.execute(
            "SELECT * FROM stronghold_user_fortress_progress WHERE user_id = ? AND fortress_id = ?",
            (user_id, fortress_id),
        ).fetchone()
        fortress_status = str(fortress_progress["status"]) if fortress_progress else ("AVAILABLE" if fortress_unlocked else "LOCKED")

        match_rows = connection.execute(
            "SELECT * FROM stronghold_fortress_matches WHERE fortress_id = ? AND active = 1 ORDER BY order_index",
            (fortress_id,),
        ).fetchall()
        match_progress_rows = {
            int(row["fortress_match_id"]): row
            for row in connection.execute(
                """
                SELECT p.* FROM stronghold_user_fortress_match_progress p
                JOIN stronghold_fortress_matches m ON m.id = p.fortress_match_id
                WHERE p.user_id = ? AND m.fortress_id = ?
                """,
                (user_id, fortress_id),
            ).fetchall()
        }

        matches: list[FortressMatchInfo] = []
        previous_won = fortress_status in ("AVAILABLE", "IN_PROGRESS", "COMPLETED") and fortress_unlocked
        for match_row in match_rows:
            progress_row = match_progress_rows.get(int(match_row["id"]))
            status, stars, attempts = _match_status_for(progress_row, previous_won)
            matches.append(
                FortressMatchInfo(
                    id=int(match_row["id"]),
                    fortress_id=fortress_id,
                    order_index=int(match_row["order_index"]),
                    opponent_name=match_row["opponent_name"],
                    opponent_ovr=int(match_row["opponent_ovr"]),
                    status=status,
                    stars=stars,
                    attempts=attempts,
                )
            )
            previous_won = status in ("WON", "COMPLETED")

    return FortressInfo(
        id=int(fortress["id"]),
        order_index=int(fortress["order_index"]),
        code=fortress["code"],
        title=fortress["title"],
        description=fortress["description"] or "",
        is_boss=bool(fortress["is_boss"]),
        first_completion_ft=int(fortress["first_completion_ft"]),
        repeat_coins_reward=int(fortress["repeat_coins_reward"]),
        status=fortress_status,
        stars_total=int(fortress_progress["stars_total"]) if fortress_progress else 0,
        first_completion_reward_claimed=bool(fortress_progress["first_completion_reward_claimed"]) if fortress_progress else False,
        matches=matches,
        unlock_at=unlock_at,
    )


async def play_fortress_match(telegram_id: int, user_id: int, fortress_match_id: int) -> FortressMatchPlayResult:
    """Публичная обёртка с структурированным логированием (см. stronghold_common.log_stronghold_operation)."""
    from app.services.stronghold_common import OperationTimer, log_stronghold_operation

    with OperationTimer() as timer:
        try:
            result = await _play_fortress_match_impl(telegram_id, user_id, fortress_match_id)
        except StrongholdError as error:
            log_stronghold_operation(
                "fortress_match_play", user_id=user_id, result="error",
                duration_ms=timer.duration_ms, error_code=error.code, fortress_match_id=fortress_match_id,
            )
            raise
    log_stronghold_operation(
        "fortress_match_play", user_id=user_id, result="success", duration_ms=timer.duration_ms,
        fortress_match_id=fortress_match_id, is_win=result.is_win, ft_awarded=result.ft_awarded,
    )
    return result


async def _play_fortress_match_impl(telegram_id: int, user_id: int, fortress_match_id: int) -> FortressMatchPlayResult:
    event = await get_active_event()
    if event is None or event.status != "ACTIVE":
        _log_battle_blocked("EVENT_NOT_ACTIVE", event, fortress_match_id=fortress_match_id)
        raise StrongholdError("EVENT_NOT_ACTIVE", "Fortress доступен только пока событие ACTIVE.")

    with get_connection() as connection:
        match_row = connection.execute(
            "SELECT * FROM stronghold_fortress_matches WHERE id = ? AND active = 1", (fortress_match_id,)
        ).fetchone()
        if match_row is None:
            _log_battle_blocked("FORTRESS_MATCH_LOCKED", event, fortress_match_id=fortress_match_id, detail="match_row not found")
            raise StrongholdError("FORTRESS_MATCH_LOCKED", "Матч не найден.")
        fortress_row = connection.execute(
            "SELECT * FROM stronghold_fortresses WHERE id = ? AND event_id = ?", (match_row["fortress_id"], event.id)
        ).fetchone()
        if fortress_row is None:
            _log_battle_blocked("FORTRESS_LOCKED", event, fortress_match_id=fortress_match_id, detail="fortress_row not found")
            raise StrongholdError("FORTRESS_LOCKED", "Крепость не найдена.")

        # ГЛОБАЛЬНОЕ РАСПИСАНИЕ БАШЕН: допуск к бою крепости определяется ТОЛЬКО
        # датой открытия (см. app/services/stronghold_schedule.py), не тем,
        # пройдена ли предыдущая крепость — см. list_fortresses()/get_fortress()
        # выше для того же правила.
        schedule_config = get_schedule_config(connection, event.id)
        total_fortresses = get_total_fortress_count(connection, event.id)
        if schedule_config is None or not is_fortress_unlocked(
            schedule_config, int(fortress_row["order_index"]), total_fortresses
        ):
            _log_battle_blocked("FORTRESS_LOCKED", event, fortress_match_id=fortress_match_id, detail="fortress not yet unlocked by global schedule")
            raise StrongholdError("FORTRESS_LOCKED", "Эта крепость ещё не открыта по расписанию.")

        if int(match_row["order_index"]) > 1:
            previous_match = connection.execute(
                "SELECT id FROM stronghold_fortress_matches WHERE fortress_id = ? AND order_index = ?",
                (match_row["fortress_id"], int(match_row["order_index"]) - 1),
            ).fetchone()
            prev_match_progress = connection.execute(
                "SELECT status FROM stronghold_user_fortress_match_progress WHERE user_id = ? AND fortress_match_id = ?",
                (user_id, previous_match["id"]),
            ).fetchone()
            if prev_match_progress is None or str(prev_match_progress["status"]) not in ("WON", "COMPLETED"):
                _log_battle_blocked("FORTRESS_MATCH_LOCKED", event, fortress_match_id=fortress_match_id, detail="previous match not completed")
                raise StrongholdError("FORTRESS_MATCH_LOCKED", "Сначала пройдите предыдущий матч крепости.")

        fortress_progress_before = connection.execute(
            "SELECT * FROM stronghold_user_fortress_progress WHERE user_id = ? AND fortress_id = ?",
            (user_id, fortress_row["id"]),
        ).fetchone()
        already_completed_before = fortress_progress_before is not None and str(fortress_progress_before["status"]) == "COMPLETED"

        match_progress_before = connection.execute(
            "SELECT status FROM stronghold_user_fortress_match_progress WHERE user_id = ? AND fortress_match_id = ?",
            (user_id, fortress_match_id),
        ).fetchone()
        # A replay starts only after THIS exact stage was already cleared. Replays
        # are allowed for fun, but must be progression/reward neutral.
        stage_completed_before = (
            match_progress_before is not None
            and str(match_progress_before["status"]) in ("WON", "COMPLETED")
        )

        star_rules = json.loads(match_row["star_rules"] or "[]")
        opponent_name = match_row["opponent_name"]
        opponent_ovr = int(match_row["opponent_ovr"])

    overview = await get_lineup_overview(user_id)
    if not overview.is_complete:
        # ВАЖНО: раньше здесь был код ошибки "EVENT_NOT_ACTIVE" (чужой, для другого
        # условия) — ERROR_MESSAGES.get(code, ...) в app/texts/stronghold.py всегда
        # отдаёт текст ИЗ СЛОВАРЯ по коду, игнорируя переданное сообщение, поэтому
        # игрок видел "Событие недоступно" вместо настоящей причины "состав не заполнен".
        _log_battle_blocked("LINEUP_INCOMPLETE", event, fortress_match_id=fortress_match_id, filled=overview.filled_count, total=overview.total_slots)
        raise StrongholdError("LINEUP_INCOMPLETE", "Заполните весь состав перед матчем.")
    if overview.salary_total > STRONGHOLD_SALARY_CAP:
        _log_battle_blocked("SALARY_CAP_EXCEEDED", event, fortress_match_id=fortress_match_id, salary_total=overview.salary_total)
        raise StrongholdError("SALARY_CAP_EXCEEDED", "Состав превышает зарплатный потолок THE STRONGHOLD.")
    if not await lineup_has_collection_card(user_id, COLLECTION_CODE):
        _log_battle_blocked("COLLECTION_CARD_REQUIRED", event, fortress_match_id=fortress_match_id)
        raise StrongholdError("COLLECTION_CARD_REQUIRED", "В составе должна быть минимум одна карта коллекции THE STRONGHOLD.")

    lock = await match_guard.acquire_player_match_lock(user_id, "stronghold_fortress")
    if not lock.acquired:
        _log_battle_blocked("CARD_IN_ACTIVE_MATCH", event, fortress_match_id=fortress_match_id)
        detail = await match_guard.describe_active_match_short(lock.existing) if lock.existing else ""
        raise StrongholdError("CARD_IN_ACTIVE_MATCH", f"У вас уже идёт матч, дождитесь его завершения. {detail}".strip())

    try:
        from app.services.matches import play_stronghold_match

        match_result = await play_stronghold_match(telegram_id, opponent_ovr, opponent_name)
    except Exception:
        await match_guard.cancel_match(user_id, reason="STRONGHOLD_FORTRESS_MATCH_ERROR")
        raise

    if match_result.success:
        await match_guard.finalize_match(user_id, match_id=match_result.match_id, reason="COMPLETED")
    else:
        # Матч не состоялся (например, состав перестал быть валиден между
        # проверками) — ничего не создано, lock снимается без привязки match_id.
        await match_guard.cancel_match(user_id, reason="STRONGHOLD_FORTRESS_MATCH_NOT_STARTED")

    if not match_result.success:
        return FortressMatchPlayResult(success=False, message=match_result.message)

    is_win = match_result.result == "win"
    stars = evaluate_stars(star_rules, is_win=is_win, user_score=match_result.user_score, opponent_score=match_result.opponent_score)

    ft_awarded = 0
    coins_awarded = 0
    fortress_completed_now = False

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        new_status = "WON" if is_win else "LOST"
        connection.execute(
            """
            INSERT INTO stronghold_user_fortress_match_progress (user_id, fortress_match_id, status, stars, match_id, attempts, completed_at)
            VALUES (?, ?, ?, ?, ?, 1, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON CONFLICT(user_id, fortress_match_id) DO UPDATE SET
                status = CASE
                    WHEN stronghold_user_fortress_match_progress.status IN ('WON', 'COMPLETED')
                    THEN stronghold_user_fortress_match_progress.status
                    ELSE excluded.status
                END,
                stars = MAX(stronghold_user_fortress_match_progress.stars, excluded.stars),
                match_id = excluded.match_id,
                attempts = stronghold_user_fortress_match_progress.attempts + 1,
                completed_at = CASE
                    WHEN stronghold_user_fortress_match_progress.completed_at IS NOT NULL
                    THEN stronghold_user_fortress_match_progress.completed_at
                    WHEN excluded.status IN ('WON', 'COMPLETED') THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, fortress_match_id, new_status, stars, match_result.match_id, is_win),
        )

        connection.execute(
            """
            INSERT INTO stronghold_user_fortress_progress (user_id, event_id, fortress_id, status)
            VALUES (?, ?, ?, 'IN_PROGRESS')
            ON CONFLICT(user_id, fortress_id) DO UPDATE SET
                status = CASE WHEN stronghold_user_fortress_progress.status = 'COMPLETED' THEN 'COMPLETED' ELSE 'IN_PROGRESS' END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, event.id, fortress_row["id"]),
        )

        if is_win:
            all_matches = connection.execute(
                "SELECT id FROM stronghold_fortress_matches WHERE fortress_id = ? AND active = 1", (fortress_row["id"],)
            ).fetchall()
            won_count = connection.execute(
                """
                SELECT COUNT(*) AS c FROM stronghold_user_fortress_match_progress
                WHERE user_id = ? AND status IN ('WON', 'COMPLETED')
                  AND fortress_match_id IN (SELECT id FROM stronghold_fortress_matches WHERE fortress_id = ? AND active = 1)
                """,
                (user_id, fortress_row["id"]),
            ).fetchone()["c"]

            stars_total_row = connection.execute(
                """
                SELECT COALESCE(SUM(stars), 0) AS total FROM stronghold_user_fortress_match_progress
                WHERE user_id = ? AND fortress_match_id IN (SELECT id FROM stronghold_fortress_matches WHERE fortress_id = ? AND active = 1)
                """,
                (user_id, fortress_row["id"]),
            ).fetchone()["total"]

            all_completed_now = int(won_count) >= len(all_matches)

            if all_completed_now and not already_completed_before:
                fortress_completed_now = True
                connection.execute(
                    """
                    UPDATE stronghold_user_fortress_progress
                    SET status = 'COMPLETED', stars_total = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND fortress_id = ?
                    """,
                    (int(stars_total_row), user_id, fortress_row["id"]),
                )
                fresh_progress = connection.execute(
                    "SELECT first_completion_reward_claimed FROM stronghold_user_fortress_progress WHERE user_id = ? AND fortress_id = ?",
                    (user_id, fortress_row["id"]),
                ).fetchone()
                if not bool(fresh_progress["first_completion_reward_claimed"]):
                    ft_awarded = int(fortress_row["first_completion_ft"])
                    if ft_awarded > 0:
                        credit(connection, user_id=user_id, event_id=event.id, currency_code=FT_CURRENCY_CODE,
                               amount=ft_awarded, reason="fortress_first_completion", reference_type="fortress", reference_id=fortress_row["id"])
                    connection.execute(
                        """
                        UPDATE stronghold_user_fortress_progress
                        SET first_completion_reward_claimed = 1
                        WHERE user_id = ? AND fortress_id = ?
                        """,
                        (user_id, fortress_row["id"]),
                    )
            else:
                connection.execute(
                    """
                    UPDATE stronghold_user_fortress_progress
                    SET stars_total = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND fortress_id = ?
                    """,
                    (int(stars_total_row), user_id, fortress_row["id"]),
                )
                # Repeat Fortress stages are intentionally reward-neutral.
                # `repeat_coins_reward` remains in the schema for backward
                # compatibility with old admin data, but is no longer paid.
                if already_completed_before:
                    coins_awarded = 0

        connection.execute(
            """
            INSERT INTO stronghold_analytics_event (event_id, user_id, event_code, payload)
            VALUES (?, ?, 'fortress_match_result', ?)
            """,
            (event.id, user_id, json.dumps({"fortress_match_id": fortress_match_id, "is_win": is_win, "stars": stars})),
        )

        connection.commit()

    try:
        from app.services.stronghold_missions import apply_stronghold_progress
        from app.services.stronghold_season_track import add_event_xp

        if not stage_completed_before:
            await apply_stronghold_progress(user_id, "play_matches", 1)
            if is_win:
                await apply_stronghold_progress(user_id, "win_matches", 1)
                await apply_stronghold_progress(user_id, "fortress_match_complete", 1)
                await apply_stronghold_progress(user_id, "use_collection_card", 1)
                if stars > 0:
                    await apply_stronghold_progress(user_id, "earn_stars", stars)
                await add_event_xp(user_id, XP_PER_FORTRESS_WIN)
                if fortress_completed_now:
                    await apply_stronghold_progress(user_id, "fortress_complete", 1)
    except Exception:
        logger.exception("stronghold fortress progress hooks failed")

    return FortressMatchPlayResult(
        success=True,
        message=match_result.message,
        is_win=is_win,
        user_score=match_result.user_score,
        opponent_score=match_result.opponent_score,
        stars=stars,
        fortress_completed_now=fortress_completed_now,
        ft_awarded=ft_awarded,
        coins_awarded=coins_awarded,
    )
