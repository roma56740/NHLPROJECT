"""CLAN WAR 2.0 — сезон, билеты, подбор соперника, оркестрация матча, симуляция и
персист результата. См. docs/CLAN_WAR_2_SPEC.md.

ВАЖНО: `record_war2_match_result()` намеренно НЕ вызывает
`app.services.matches.save_match_result()` — тот безусловно (a) меняет
users.matches_played/wins/losses/rating_points/league (лестница обычных матчей) и
переиспользуем только математику симуляции (`build_simulation`/`choose_scorer`/
`calculate_rating_delta`), не побочные эффекты записи.
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services import match_guard
from app.services.lineup import LineupCard
from app.services.matches import (
    BOT_NAMES,
    MatchEventInfo,
    MatchPeriodSummary,
    build_simulation,
    calculate_rating_delta,
    choose_scorer,
)
from app.services.quests import get_daily_period_key
from app.services.settings import get_int_setting
from app.services.war2_common import War2Error
from app.services.war2_draft import build_ephemeral_lineup, compute_war2_lineup_ovr
from app.services.war2_modes import War2ModeDefinition, WAR2_MODE_REGISTRY, roll_active_mode

ABANDONED_MATCH_TIMEOUT_MINUTES = 10
DEFAULT_PLAYER_RATING = 1000
DEFAULT_SEASON_LENGTH_DAYS = 28


@dataclass(frozen=True)
class War2Season:
    id: int
    season_number: int
    status: str
    starts_at: str | None
    ends_at: str | None


@dataclass(frozen=True)
class War2Opponent:
    user_id: int | None
    clan_id: int | None
    name: str
    type: str  # 'player' | 'bot'


@dataclass(frozen=True)
class War2MatchStart:
    match_id: int
    mode: War2ModeDefinition
    opponent: War2Opponent


@dataclass(frozen=True)
class War2MatchResult:
    match_id: int
    user_score: int
    opponent_score: int
    result: str
    rating_delta: int
    mvp_title: str
    is_overtime: bool
    is_shootout: bool
    periods: list[MatchPeriodSummary]
    events: list[MatchEventInfo]


def _row_to_season(row: sqlite3.Row) -> War2Season:
    return War2Season(
        id=int(row["id"]),
        season_number=int(row["season_number"]),
        status=row["status"],
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
    )


async def get_active_season() -> War2Season | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM war2_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _row_to_season(row) if row is not None else None


async def get_remaining_tickets(user_id: int) -> int:
    day_key = get_daily_period_key()
    limit = await get_int_setting("war2_daily_tickets", 5, minimum=0)
    with get_connection() as connection:
        row = connection.execute(
            "SELECT tickets_used FROM war2_daily_tickets WHERE user_id = ? AND day_key = ?",
            (user_id, day_key),
        ).fetchone()
    used = int(row["tickets_used"]) if row is not None else 0
    return max(limit - used, 0)


async def spend_ticket(connection: sqlite3.Connection, user_id: int) -> None:
    """Списывает билет ВНУТРИ уже открытой транзакции `connection` — вызывается только
    из record_war2_match_result(), в момент завершения матча (раздел ТЗ "MATCH FLOW":
    шаг 9 "списать билет" идёт после шага 8 "провести матч", не раньше)."""
    day_key = get_daily_period_key()
    connection.execute(
        """
        INSERT INTO war2_daily_tickets (user_id, day_key, tickets_used) VALUES (?, ?, 1)
        ON CONFLICT(user_id, day_key) DO UPDATE SET tickets_used = tickets_used + 1, updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, day_key),
    )


async def _get_user_clan_id(user_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["clan_id"]) if row is not None else None


async def _get_player_rating(user_id: int, season_id: int | None) -> int:
    if season_id is None:
        return DEFAULT_PLAYER_RATING
    with get_connection() as connection:
        row = connection.execute(
            "SELECT rating_points FROM war2_player_stats WHERE season_id = ? AND user_id = ?",
            (season_id, user_id),
        ).fetchone()
    return int(row["rating_points"]) if row is not None else DEFAULT_PLAYER_RATING


async def find_war2_opponent(user_id: int) -> War2Opponent:
    """Реальный игрок из ДРУГОГО клана, подобранный мгновенно по ближайшему рейтингу
    CLAN WAR 2.0 (без очереди ожидания) — раздел ТЗ "MATCH FLOW" шаг 3. Если подходящего
    игрока нет (нет других кланов/участников), подставляется синтетический бот-соперник."""
    season = await get_active_season()
    season_id = season.id if season else None
    my_rating = await _get_player_rating(user_id, season_id)
    user_clan_id = await _get_user_clan_id(user_id)

    # Соперник ищется среди ростера CLAN WAR 2.0 других кланов (war2_clan_roster), не
    # среди всех clan_members — участвовать в матчах могут только рострированные
    # игроки (раздел ТЗ "Clan size: 5"), с обеих сторон одинаково.
    params: list = [season_id, user_id]
    extra_where = ""
    if user_clan_id is not None:
        extra_where = "AND war2_clan_roster.clan_id != ?"
        params.append(user_clan_id)
    params.extend([DEFAULT_PLAYER_RATING, my_rating])

    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT users.id AS opponent_user_id, war2_clan_roster.clan_id AS opponent_clan_id, users.nickname
            FROM users
            JOIN war2_clan_roster ON war2_clan_roster.user_id = users.id
            LEFT JOIN war2_player_stats stats ON stats.user_id = users.id AND stats.season_id = ?
            WHERE users.id != ?
              {extra_where}
            ORDER BY ABS(COALESCE(stats.rating_points, ?) - ?) ASC, RANDOM()
            LIMIT 1
            """,
            params,
        ).fetchone()

    if row is None:
        return War2Opponent(user_id=None, clan_id=None, name=random.choice(BOT_NAMES), type="bot")

    opponent_clan_id = int(row["opponent_clan_id"]) if row["opponent_clan_id"] is not None else None
    return War2Opponent(
        user_id=int(row["opponent_user_id"]),
        clan_id=opponent_clan_id,
        name=row["nickname"] or "Соперник",
        type="player",
    )


async def cleanup_abandoned_war2_matches() -> None:
    """Помечает зависшие драфты 'abandoned' И сразу освобождает их match lock —
    иначе пользователь оставался бы заблокированным вплоть до истечения TTL
    match lock'а (30 минут для war2, см. match_guard.MATCH_TYPE_TTL_SECONDS),
    что дольше самого таймаута драфта (ABANDONED_MATCH_TIMEOUT_MINUTES=10)."""
    with get_connection() as connection:
        stale_rows = connection.execute(
            "SELECT user_id FROM war2_matches WHERE status = 'drafting' AND datetime(created_at) < datetime('now', ?)",
            (f"-{ABANDONED_MATCH_TIMEOUT_MINUTES} minutes",),
        ).fetchall()
        stale_user_ids = [int(row["user_id"]) for row in stale_rows]

        connection.execute(
            "UPDATE war2_matches SET status = 'abandoned' WHERE status = 'drafting' AND datetime(created_at) < datetime('now', ?)",
            (f"-{ABANDONED_MATCH_TIMEOUT_MINUTES} minutes",),
        )
        connection.commit()

    for user_id in stale_user_ids:
        await match_guard.cancel_match(user_id, reason="WAR2_DRAFT_TIMEOUT")


async def start_war2_match(user_id: int) -> War2MatchStart:
    """Раздел ТЗ "MATCH FLOW", шаги 2-6: билет -> соперник -> War Roulette -> запись
    матча в статусе 'drafting'. Билет тут ЕЩЁ не списывается (см. spend_ticket)."""
    await cleanup_abandoned_war2_matches()

    if await get_remaining_tickets(user_id) <= 0:
        raise War2Error("NO_TICKETS_LEFT", "Билеты на сегодня закончились. Возвращайтесь завтра.")

    user_clan_id = await _get_user_clan_id(user_id)
    if user_clan_id is None:
        raise War2Error("NO_CLAN", "Нужно состоять в клане, чтобы участвовать в CLAN WAR 2.0.")

    from app.services.war2_roster import get_clan_roster

    roster = await get_clan_roster(user_clan_id)
    if not roster:
        raise War2Error(
            "ROSTER_NOT_SET",
            "Клан ещё не сформировал ростер CLAN WAR 2.0. Лидер или офицер клана может "
            "добавить до 5 игроков в разделе «👥 Ростер клана».",
        )
    if user_id not in {member.user_id for member in roster}:
        raise War2Error(
            "NOT_ON_ROSTER",
            "Вы не в ростере CLAN WAR 2.0 своего клана. Обратитесь к лидеру или офицеру клана.",
        )

    # ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: "war2" получает существенно больший TTL (см.
    # match_guard.MATCH_TYPE_TTL_SECONDS) — это единственный режим с реальной
    # многошаговой фазой ожидания ввода игрока (драфт) между стартом и
    # завершением, короткий TTL инстант-режимов мог бы истечь, пока пользователь
    # ещё реально в драфте.
    lock = await match_guard.acquire_player_match_lock(user_id, "war2")
    if not lock.acquired:
        detail = await match_guard.describe_active_match_short(lock.existing) if lock.existing else ""
        raise War2Error("MATCH_ALREADY_ACTIVE", f"У вас уже идёт матч, дождитесь его завершения. {detail}".strip())

    try:
        season = await get_active_season()
        opponent = await find_war2_opponent(user_id)
        mode = await roll_active_mode()

        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO war2_matches
                    (season_id, status, user_id, user_clan_id, opponent_user_id, opponent_clan_id, opponent_name, opponent_type, mode_code)
                VALUES (?, 'drafting', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    season.id if season else None,
                    user_id,
                    user_clan_id,
                    opponent.user_id,
                    opponent.clan_id,
                    opponent.name,
                    opponent.type,
                    mode.code,
                ),
            )
            match_id = int(cursor.lastrowid)
            connection.commit()

        await match_guard.bind_lock_to_match(lock.lock_id, match_id)

        if mode.uses_draft:
            # Пул генерируется сразу здесь, в сервисном слое — а не там, где он
            # понадобится (хендлер экрана драфта). Раньше пул нигде не создавался в
            # общем пути и любой вызов get_draft_state() до первого ручного вызова
            # generate_draft_pool() читал пустой пул (remaining=[] при current_picker
            # уже вычисленном как "user") -> IndexError на первом же экране драфта.
            # generate_draft_pool() идемпотентен (возвращает уже созданный пул повторно).
            from app.services.war2_draft import generate_draft_pool

            await generate_draft_pool(match_id)
    except Exception:
        await match_guard.cancel_match(user_id, reason="WAR2_START_ERROR")
        raise

    return War2MatchStart(match_id=match_id, mode=mode, opponent=opponent)


@dataclass(frozen=True)
class War2Simulation:
    user_ovr: int
    opponent_ovr: int
    user_score: int
    opponent_score: int
    is_overtime: bool
    is_shootout: bool
    periods: list[MatchPeriodSummary]
    events: list[MatchEventInfo]


def simulate_war2_match(
    user_cards: list[LineupCard],
    opponent_cards: list[LineupCard],
    opponent_name: str,
) -> War2Simulation:
    """Тонкая обёртка над app.services.matches.build_simulation — переиспользует всю
    математику симуляции без единой продублированной строки логики. Синхронная (как и
    build_simulation сам по себе) — не делает I/O."""
    user_ovr = compute_war2_lineup_ovr(user_cards)
    opponent_ovr = compute_war2_lineup_ovr(opponent_cards)
    user_score, opponent_score, is_overtime, is_shootout, periods, events = build_simulation(
        user_ovr=user_ovr,
        opponent_ovr=opponent_ovr,
        lineup_cards=user_cards,
        opponent_name=opponent_name,
    )
    return War2Simulation(user_ovr, opponent_ovr, user_score, opponent_score, is_overtime, is_shootout, periods, events)


async def record_war2_match_result(
    *,
    match_id: int,
    user_id: int,
    user_clan_id: int | None,
    opponent_clan_id: int | None,
    user_cards: list[LineupCard],
    opponent_cards: list[LineupCard],
    opponent_name: str,
) -> War2MatchResult:
    """Раздел ТЗ "MATCH FLOW", шаги 7-10: провести матч -> списать билет -> начислить
    рейтинг. Пишет ТОЛЬКО в war2_* таблицы (см. докстринг модуля)."""
    sim = simulate_war2_match(user_cards, opponent_cards, opponent_name)
    user_ovr, opponent_ovr = sim.user_ovr, sim.opponent_ovr
    user_score, opponent_score = sim.user_score, sim.opponent_score
    is_overtime, is_shootout = sim.is_overtime, sim.is_shootout
    periods, events = sim.periods, sim.events
    is_win = user_score > opponent_score
    result = "win" if is_win else "loss"
    rating_delta = calculate_rating_delta(user_ovr, opponent_ovr, is_win)
    mvp_title = choose_scorer(user_cards, "Игрок матча") if is_win else f"Лидер {opponent_name}"

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        match_row = connection.execute(
            "SELECT status, season_id FROM war2_matches WHERE id = ? AND user_id = ?", (match_id, user_id)
        ).fetchone()
        if match_row is None:
            connection.rollback()
            raise War2Error("MATCH_NOT_FOUND", "Матч не найден.")
        if match_row["status"] != "drafting":
            connection.rollback()
            raise War2Error("MATCH_NOT_DRAFTING", "Матч уже завершён или отменён.")

        season_id = match_row["season_id"]

        connection.execute(
            """
            UPDATE war2_matches
            SET status = 'completed', user_lineup_json = ?, opponent_lineup_json = ?,
                user_ovr = ?, opponent_ovr = ?, user_score = ?, opponent_score = ?,
                result = ?, rating_delta = ?, is_overtime = ?, is_shootout = ?,
                mvp_title = ?, periods_summary = ?, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                json.dumps([card.card_id for card in user_cards]),
                json.dumps([card.card_id for card in opponent_cards]),
                user_ovr,
                opponent_ovr,
                user_score,
                opponent_score,
                result,
                rating_delta,
                int(is_overtime),
                int(is_shootout),
                mvp_title,
                json.dumps([period.__dict__ for period in periods]),
                match_id,
            ),
        )

        for event in events:
            connection.execute(
                "INSERT INTO war2_match_events (match_id, period_title, time_text, event_type, description) VALUES (?, ?, ?, ?, ?)",
                (match_id, event.period_title, event.time_text, event.event_type, event.description),
            )

        if season_id is not None:
            connection.execute(
                """
                INSERT INTO war2_player_stats (season_id, user_id, rating_points, matches_played, wins, losses)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(season_id, user_id) DO UPDATE SET
                    rating_points = rating_points + ?,
                    matches_played = matches_played + 1,
                    wins = wins + ?,
                    losses = losses + ?,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    season_id, user_id, DEFAULT_PLAYER_RATING + rating_delta, 1 if is_win else 0, 0 if is_win else 1,
                    rating_delta, 1 if is_win else 0, 0 if is_win else 1,
                ),
            )
            if user_clan_id is not None:
                connection.execute(
                    """
                    INSERT INTO war2_clan_stats (season_id, clan_id, rating_points, wins_contributed, matches_played)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(season_id, clan_id) DO UPDATE SET
                        rating_points = rating_points + ?,
                        wins_contributed = wins_contributed + ?,
                        matches_played = matches_played + 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        season_id, user_clan_id, max(rating_delta, 0), 1 if is_win else 0,
                        max(rating_delta, 0), 1 if is_win else 0,
                    ),
                )

        await spend_ticket(connection, user_id)
        connection.commit()

    await match_guard.finalize_match(user_id, match_id=match_id, reason="COMPLETED")

    return War2MatchResult(
        match_id=match_id,
        user_score=user_score,
        opponent_score=opponent_score,
        result=result,
        rating_delta=rating_delta,
        mvp_title=mvp_title,
        is_overtime=is_overtime,
        is_shootout=is_shootout,
        periods=periods,
        events=events,
    )


async def cancel_war2_match(match_id: int, user_id: int) -> None:
    """Отмена во время драфта (игрок вышел из экрана) — билет НЕ списывается (см.
    докстринг start_war2_match: списание только на 'completed')."""
    with get_connection() as connection:
        connection.execute(
            "UPDATE war2_matches SET status = 'abandoned' WHERE id = ? AND user_id = ? AND status = 'drafting'",
            (match_id, user_id),
        )
        connection.commit()
    await match_guard.cancel_match(user_id, reason="WAR2_DRAFT_ABANDONED")


async def get_match(match_id: int, user_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM war2_matches WHERE id = ? AND user_id = ?", (match_id, user_id)
        ).fetchone()
