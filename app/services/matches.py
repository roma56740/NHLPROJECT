from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Literal

from app.database.db import get_connection
from app.services.lineup import LineupCard, get_lineup_overview
from app.services.events import apply_match_event_progress
from app.services.quests import apply_match_quest_progress
from app.services.settings import get_int_setting
from app.services.users import PlayerProfile, get_player_profile_by_telegram_id


WIN_COINS_REWARD = 100
LEAGUE_STEP_POINTS = 1500
LEAGUES = ["NCAA", "AHL", "NHL", "OLYMPICS"]
MATCH_QUEUE_MIN_WAIT_SECONDS = 90
MATCH_QUEUE_MAX_WAIT_SECONDS = 110
MATCH_QUEUE_OVR_SPREAD = 10

BOT_NAMES = [
    "Ice Wolves",
    "Frost Hawks",
    "Northern Bears",
    "Polar Kings",
    "Snow Rangers",
    "Glacier Storm",
    "Frozen Knights",
    "Arctic Foxes",
]

EVENT_ICONS = {
    "GOAL": "🥅",
    "SAVE": "🧤",
    "POWERPLAY": "⚡",
    "BIG HIT": "💥",
    "BREAKAWAY": "🏒",
}


def utc_datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class MatchPeriodSummary:
    title: str
    user_goals: int
    opponent_goals: int
    user_shots: int
    opponent_shots: int
    possession_user: int


@dataclass(frozen=True)
class MatchEventInfo:
    period_title: str
    time_text: str
    event_type: str
    description: str


@dataclass(frozen=True)
class MatchPlayResult:
    success: bool
    message: str
    match_id: int | None = None
    opponent_name: str = ""
    opponent_type: str = "bot"
    user_lineup_ovr: int = 0
    opponent_lineup_ovr: int = 0
    user_score: int = 0
    opponent_score: int = 0
    result: str = "loss"
    rating_delta: int = 0
    coins_reward: int = 0
    rank_points_reward: int = 0
    league_before: str = "NCAA"
    league_after: str = "NCAA"
    is_overtime: bool = False
    is_shootout: bool = False
    mvp_title: str = ""
    periods: list[MatchPeriodSummary] | None = None
    events: list[MatchEventInfo] | None = None


@dataclass(frozen=True)
class MatchHistoryItem:
    id: int
    opponent_name: str
    user_score: int
    opponent_score: int
    result: str
    rating_delta: int
    coins_reward: int
    league_before: str
    league_after: str
    created_at: str


@dataclass(frozen=True)
class MatchHistoryPage:
    matches: list[MatchHistoryItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class MatchDetails:
    id: int
    opponent_name: str
    opponent_type: str
    user_lineup_ovr: int
    opponent_lineup_ovr: int
    user_score: int
    opponent_score: int
    result: str
    rating_delta: int
    coins_reward: int
    rank_points_reward: int
    league_before: str
    league_after: str
    is_overtime: bool
    is_shootout: bool
    mvp_title: str
    periods: list[MatchPeriodSummary]
    events: list[MatchEventInfo]
    created_at: str


@dataclass(frozen=True)
class MatchMainInfo:
    is_ready: bool
    filled_count: int
    total_slots: int
    lineup_ovr: int | None
    league: str
    rating_points: int
    matches_played: int
    wins: int
    losses: int


@dataclass(frozen=True)
class MatchQueuedOpponent:
    user_id: int
    telegram_id: int
    chat_id: int
    message_id: int
    nickname: str
    league: str
    rating_points: int
    lineup_ovr: int


@dataclass(frozen=True)
class ExpiredMatchQueueItem:
    queue_id: int
    telegram_id: int
    chat_id: int
    message_id: int


@dataclass(frozen=True)
class MatchmakingResult:
    status: Literal["not_ready", "queued", "already_queued", "matched"]
    message: str
    wait_seconds: int = 0
    opponent: MatchQueuedOpponent | None = None
    current_result: MatchPlayResult | None = None
    opponent_result: MatchPlayResult | None = None


@dataclass(frozen=True)
class MatchQueueCancelResult:
    success: bool
    message: str


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def weighted_success(user_ovr: int, opponent_ovr: int) -> bool:
    chance = clamp(50 + (user_ovr - opponent_ovr) * 2, 35, 65)
    return random.randint(1, 100) <= chance


def choose_scorer(cards: list[LineupCard], fallback: str) -> str:
    candidates = [card for card in cards if card.position != "G"] or cards

    if not candidates:
        return fallback

    return random.choice(candidates).name


def choose_goalie(cards: list[LineupCard], fallback: str) -> str:
    candidates = [card for card in cards if card.position == "G"]

    if not candidates:
        return fallback

    return random.choice(candidates).name


def build_period_events(
    period_title: str,
    user_goals: int,
    opponent_goals: int,
    lineup_cards: list[LineupCard],
    opponent_name: str,
) -> list[MatchEventInfo]:
    events: list[MatchEventInfo] = []
    used_times: set[int] = set()

    def make_time() -> str:
        minute = random.randint(1, 19)
        while minute in used_times:
            minute = random.randint(1, 19)
        used_times.add(minute)
        second = random.randint(0, 59)
        return f"{minute:02d}:{second:02d}"

    for _ in range(user_goals):
        scorer = choose_scorer(lineup_cards, "Твой игрок")
        events.append(MatchEventInfo(period_title, make_time(), "GOAL", f"Гол забивает {scorer}"))

    for _ in range(opponent_goals):
        events.append(MatchEventInfo(period_title, make_time(), "GOAL", f"{opponent_name} отвечает голом"))

    if random.random() < 0.65:
        goalie = choose_goalie(lineup_cards, "вратарь")
        events.append(MatchEventInfo(period_title, make_time(), "SAVE", f"{goalie} спасает команду"))

    if random.random() < 0.35:
        events.append(MatchEventInfo(period_title, make_time(), "POWERPLAY", "Большинство создаёт опасный момент"))

    if random.random() < 0.35:
        events.append(MatchEventInfo(period_title, make_time(), "BIG HIT", "Жёсткий силовой приём у борта"))

    if random.random() < 0.25:
        scorer = choose_scorer(lineup_cards, "форвард")
        events.append(MatchEventInfo(period_title, make_time(), "BREAKAWAY", f"{scorer} убегает один на один"))

    return sorted(events, key=lambda event: event.time_text)


def simulate_period(
    number: int,
    user_ovr: int,
    opponent_ovr: int,
    lineup_cards: list[LineupCard],
    opponent_name: str,
) -> tuple[MatchPeriodSummary, list[MatchEventInfo]]:
    user_shots = random.randint(7, 14) + max(0, user_ovr - opponent_ovr) // 8
    opponent_shots = random.randint(7, 14) + max(0, opponent_ovr - user_ovr) // 8
    user_goal_chance = clamp(7 + (user_ovr - opponent_ovr), 4, 13)
    opponent_goal_chance = clamp(7 + (opponent_ovr - user_ovr), 4, 13)

    user_goals = sum(1 for _ in range(user_shots) if random.randint(1, 100) <= user_goal_chance)
    opponent_goals = sum(1 for _ in range(opponent_shots) if random.randint(1, 100) <= opponent_goal_chance)
    possession_user = clamp(50 + (user_ovr - opponent_ovr) + random.randint(-7, 7), 38, 62)
    title = f"Период {number}"

    summary = MatchPeriodSummary(
        title=title,
        user_goals=user_goals,
        opponent_goals=opponent_goals,
        user_shots=user_shots,
        opponent_shots=opponent_shots,
        possession_user=possession_user,
    )
    events = build_period_events(title, user_goals, opponent_goals, lineup_cards, opponent_name)
    return summary, events


def calculate_rating_delta(user_ovr: int, opponent_ovr: int, is_win: bool) -> int:
    difference = opponent_ovr - user_ovr

    if is_win:
        return clamp(28 + difference, 18, 45)

    return -clamp(16 - difference, 8, 28)


def apply_league_progress(league: str, points: int, delta: int) -> tuple[str, int, int]:
    if league not in LEAGUES:
        league = "NCAA"

    current_league = league
    current_points = max(0, points + delta)
    rank_points_reward = 0

    if current_league == "OLYMPICS":
        return current_league, current_points, rank_points_reward

    league_index = LEAGUES.index(current_league)

    while current_points >= LEAGUE_STEP_POINTS and league_index < len(LEAGUES) - 1:
        current_points -= LEAGUE_STEP_POINTS
        league_index += 1
        current_league = LEAGUES[league_index]
        rank_points_reward += 2 if current_league == "OLYMPICS" else 1

        if current_league == "OLYMPICS":
            current_points = 0
            break

    return current_league, current_points, rank_points_reward


def periods_to_json(periods: list[MatchPeriodSummary]) -> str:
    return json.dumps([period.__dict__ for period in periods], ensure_ascii=False)


def periods_from_json(value: str) -> list[MatchPeriodSummary]:
    try:
        raw_periods = json.loads(value or "[]")
    except json.JSONDecodeError:
        raw_periods = []

    periods: list[MatchPeriodSummary] = []

    for item in raw_periods:
        periods.append(
            MatchPeriodSummary(
                title=str(item.get("title", "Период")),
                user_goals=int(item.get("user_goals", 0)),
                opponent_goals=int(item.get("opponent_goals", 0)),
                user_shots=int(item.get("user_shots", 0)),
                opponent_shots=int(item.get("opponent_shots", 0)),
                possession_user=int(item.get("possession_user", 50)),
            )
        )

    return periods


def mirror_periods(periods: list[MatchPeriodSummary]) -> list[MatchPeriodSummary]:
    return [
        MatchPeriodSummary(
            title=period.title,
            user_goals=period.opponent_goals,
            opponent_goals=period.user_goals,
            user_shots=period.opponent_shots,
            opponent_shots=period.user_shots,
            possession_user=100 - period.possession_user,
        )
        for period in periods
    ]


def row_to_history_item(row) -> MatchHistoryItem:
    return MatchHistoryItem(
        id=row["id"],
        opponent_name=row["opponent_name"],
        user_score=row["user_score"],
        opponent_score=row["opponent_score"],
        result=row["result"],
        rating_delta=row["rating_delta"],
        coins_reward=row["coins_reward"],
        league_before=row["league_before"],
        league_after=row["league_after"],
        created_at=row["created_at"],
    )


def row_to_queue_opponent(row) -> MatchQueuedOpponent:
    return MatchQueuedOpponent(
        user_id=row["user_id"],
        telegram_id=row["telegram_id"],
        chat_id=row["chat_id"],
        message_id=row["message_id"],
        nickname=row["nickname"],
        league=row["league"],
        rating_points=row["rating_points"],
        lineup_ovr=row["lineup_ovr"],
    )


def build_simulation(
    user_ovr: int,
    opponent_ovr: int,
    lineup_cards: list[LineupCard],
    opponent_name: str,
) -> tuple[int, int, bool, bool, list[MatchPeriodSummary], list[MatchEventInfo]]:
    periods: list[MatchPeriodSummary] = []
    events: list[MatchEventInfo] = []

    for number in range(1, 4):
        period, period_events = simulate_period(number, user_ovr, opponent_ovr, lineup_cards, opponent_name)
        periods.append(period)
        events.extend(period_events)

    user_score = sum(period.user_goals for period in periods)
    opponent_score = sum(period.opponent_goals for period in periods)
    is_overtime = False
    is_shootout = False

    if user_score == opponent_score:
        user_wins_extra = weighted_success(user_ovr, opponent_ovr)

        if random.random() < 0.65:
            is_overtime = True
            if user_wins_extra:
                user_score += 1
                scorer = choose_scorer(lineup_cards, "Твой игрок")
                events.append(MatchEventInfo("Овертайм", "03:12", "GOAL", f"{scorer} забивает решающий гол"))
            else:
                opponent_score += 1
                events.append(MatchEventInfo("Овертайм", "04:28", "GOAL", f"{opponent_name} забивает в овертайме"))
        else:
            is_shootout = True
            if user_wins_extra:
                user_score += 1
                scorer = choose_scorer(lineup_cards, "Твой игрок")
                events.append(MatchEventInfo("Буллиты", "SO", "GOAL", f"{scorer} решает серию буллитов"))
            else:
                opponent_score += 1
                events.append(MatchEventInfo("Буллиты", "SO", "SAVE", f"{opponent_name} забирает серию буллитов"))

    return user_score, opponent_score, is_overtime, is_shootout, periods, events


async def get_match_main_info(telegram_id: int) -> MatchMainInfo | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    overview = await get_lineup_overview(profile.id)

    return MatchMainInfo(
        is_ready=overview.is_complete,
        filled_count=overview.filled_count,
        total_slots=overview.total_slots,
        lineup_ovr=overview.final_overall,
        league=profile.league,
        rating_points=profile.rating_points,
        matches_played=profile.matches_played,
        wins=profile.wins,
        losses=profile.losses,
    )


async def cleanup_match_queue() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM match_queue
            WHERE datetime(created_at) < datetime('now', '-10 minutes')
            """
        )
        connection.commit()


async def is_player_in_match_queue(telegram_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "SELECT id FROM match_queue WHERE telegram_id = ?",
            (telegram_id,),
        )
        return cursor.fetchone() is not None


async def cancel_match_search(telegram_id: int) -> MatchQueueCancelResult:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM match_queue WHERE telegram_id = ?",
            (telegram_id,),
        )
        connection.commit()

    if cursor.rowcount:
        return MatchQueueCancelResult(True, "Поиск соперника остановлен.")

    return MatchQueueCancelResult(False, "Активного поиска уже нет.")


async def get_expired_match_queue_items(limit: int = 10) -> list[ExpiredMatchQueueItem]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT id, telegram_id, chat_id, message_id
            FROM match_queue
            WHERE datetime(COALESCE(bot_fallback_at, datetime(created_at, '+90 seconds'))) <= datetime('now')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    return [
        ExpiredMatchQueueItem(
            queue_id=row["id"],
            telegram_id=row["telegram_id"],
            chat_id=row["chat_id"],
            message_id=row["message_id"],
        )
        for row in rows
    ]


async def enter_matchmaking(telegram_id: int, chat_id: int, message_id: int) -> MatchmakingResult:
    await cleanup_match_queue()

    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return MatchmakingResult("not_ready", "Открой игру через /start.")

    overview = await get_lineup_overview(profile.id)

    if not overview.is_complete or overview.average_overall is None:
        return MatchmakingResult("not_ready", "Для матча нужно заполнить все 6 слотов состава.")

    user_ovr = overview.final_overall or overview.average_overall

    with get_connection() as connection:
        existing_cursor = connection.execute(
            "SELECT id FROM match_queue WHERE user_id = ?",
            (profile.id,),
        )

        if existing_cursor.fetchone() is not None:
            connection.execute(
                """
                UPDATE match_queue
                SET chat_id = ?, message_id = ?, lineup_ovr = ?, rating_points = ?, league = ?
                WHERE user_id = ?
                """,
                (chat_id, message_id, user_ovr, profile.rating_points, profile.league, profile.id),
            )
            connection.commit()
            return MatchmakingResult("already_queued", "Поиск соперника уже идёт.")

        opponent_cursor = connection.execute(
            """
            SELECT
                user_id,
                telegram_id,
                chat_id,
                message_id,
                nickname,
                league,
                rating_points,
                lineup_ovr
            FROM match_queue
            WHERE user_id != ?
              AND league = ?
              AND lineup_ovr BETWEEN ? AND ?
            ORDER BY ABS(lineup_ovr - ?) ASC, ABS(rating_points - ?) ASC, created_at ASC
            LIMIT 1
            """,
            (
                profile.id,
                profile.league,
                user_ovr - MATCH_QUEUE_OVR_SPREAD,
                user_ovr + MATCH_QUEUE_OVR_SPREAD,
                user_ovr,
                profile.rating_points,
            ),
        )
        opponent_row = opponent_cursor.fetchone()

        if opponent_row is None:
            min_wait = await get_int_setting("matchmaking_min_wait_seconds", MATCH_QUEUE_MIN_WAIT_SECONDS, minimum=10, maximum=600)
            max_wait = await get_int_setting("matchmaking_max_wait_seconds", MATCH_QUEUE_MAX_WAIT_SECONDS, minimum=min_wait, maximum=900)
            wait_seconds = random.randint(min_wait, max_wait)
            bot_fallback_at = utc_datetime_text(datetime.now(timezone.utc) + timedelta(seconds=wait_seconds))

            connection.execute(
                """
                INSERT INTO match_queue (
                    user_id,
                    telegram_id,
                    chat_id,
                    message_id,
                    nickname,
                    league,
                    rating_points,
                    lineup_ovr,
                    bot_fallback_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.telegram_id,
                    chat_id,
                    message_id,
                    profile.nickname,
                    profile.league,
                    profile.rating_points,
                    user_ovr,
                    bot_fallback_at,
                ),
            )
            connection.commit()
            return MatchmakingResult(
                "queued",
                "Ищем соперника.",
                wait_seconds=wait_seconds,
            )

        opponent = row_to_queue_opponent(opponent_row)
        connection.execute("DELETE FROM match_queue WHERE user_id IN (?, ?)", (profile.id, opponent.user_id))
        connection.commit()

    current_result, opponent_result = await play_player_match(profile.telegram_id, opponent.telegram_id)

    if current_result is None or opponent_result is None:
        return MatchmakingResult("not_ready", "Соперник покинул лёд. Попробуй начать поиск снова.")

    return MatchmakingResult(
        "matched",
        "Соперник найден.",
        opponent=opponent,
        current_result=current_result,
        opponent_result=opponent_result,
    )


async def finish_waiting_search_with_bot(telegram_id: int) -> MatchPlayResult | None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "SELECT id FROM match_queue WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cursor.fetchone()

        if row is None:
            connection.commit()
            return None

        cursor = connection.execute("DELETE FROM match_queue WHERE id = ?", (row["id"],))
        connection.commit()

        if cursor.rowcount == 0:
            return None

    return await play_quick_match(telegram_id)


async def finish_waiting_search_with_bot_by_queue_id(queue_id: int) -> MatchPlayResult | None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "SELECT telegram_id FROM match_queue WHERE id = ?",
            (queue_id,),
        )
        row = cursor.fetchone()

        if row is None:
            connection.commit()
            return None

        telegram_id = int(row["telegram_id"])
        cursor = connection.execute("DELETE FROM match_queue WHERE id = ?", (queue_id,))
        connection.commit()

        if cursor.rowcount == 0:
            return None

    return await play_quick_match(telegram_id)


async def save_match_result(
    *,
    profile: PlayerProfile,
    opponent_user_id: int | None,
    opponent_name: str,
    opponent_type: str,
    user_ovr: int,
    opponent_ovr: int,
    user_score: int,
    opponent_score: int,
    is_overtime: bool,
    is_shootout: bool,
    periods: list[MatchPeriodSummary],
    events: list[MatchEventInfo],
    mvp_title: str,
) -> MatchPlayResult:
    is_win = user_score > opponent_score
    result = "win" if is_win else "loss"
    rating_delta = calculate_rating_delta(user_ovr, opponent_ovr, is_win)
    league_before = profile.league
    league_after, new_rating_points, rank_points_reward = apply_league_progress(
        league=profile.league,
        points=profile.rating_points,
        delta=rating_delta,
    )
    win_coins_reward = await get_int_setting("win_coins_reward", WIN_COINS_REWARD, minimum=0, maximum=1000000)
    coins_reward = win_coins_reward if is_win else 0

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO matches (
                user_id,
                opponent_user_id,
                opponent_name,
                opponent_type,
                user_lineup_ovr,
                opponent_lineup_ovr,
                user_score,
                opponent_score,
                result,
                rating_delta,
                coins_reward,
                rank_points_reward,
                league_before,
                league_after,
                is_overtime,
                is_shootout,
                mvp_title,
                periods_summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.id,
                opponent_user_id,
                opponent_name,
                opponent_type,
                user_ovr,
                opponent_ovr,
                user_score,
                opponent_score,
                result,
                rating_delta,
                coins_reward,
                rank_points_reward,
                league_before,
                league_after,
                int(is_overtime),
                int(is_shootout),
                mvp_title,
                periods_to_json(periods),
            ),
        )
        match_id = int(cursor.lastrowid)

        connection.executemany(
            """
            INSERT INTO match_events (match_id, period_title, time_text, event_type, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(match_id, event.period_title, event.time_text, event.event_type, event.description) for event in events],
        )

        connection.execute(
            """
            UPDATE users
            SET matches_played = matches_played + 1,
                wins = wins + ?,
                losses = losses + ?,
                goals_scored = goals_scored + ?,
                goals_allowed = goals_allowed + ?,
                rating_points = ?,
                league = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                1 if is_win else 0,
                0 if is_win else 1,
                user_score,
                opponent_score,
                new_rating_points,
                league_after,
                profile.id,
            ),
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

        if rank_points_reward > 0:
            connection.execute(
                """
                INSERT INTO currency_balances (user_id, currency_code, amount)
                VALUES (?, 'rank_point', ?)
                ON CONFLICT(user_id, currency_code) DO UPDATE SET
                    amount = amount + excluded.amount,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (profile.id, rank_points_reward),
            )

        connection.commit()

    await apply_match_quest_progress(
        user_id=profile.id,
        is_win=is_win,
        goals_scored=user_score,
        goals_allowed=opponent_score,
    )
    await apply_match_event_progress(
        user_id=profile.id,
        is_win=is_win,
        goals_scored=user_score,
        goals_allowed=opponent_score,
    )

    return MatchPlayResult(
        success=True,
        message="Матч завершён.",
        match_id=match_id,
        opponent_name=opponent_name,
        opponent_type=opponent_type,
        user_lineup_ovr=user_ovr,
        opponent_lineup_ovr=opponent_ovr,
        user_score=user_score,
        opponent_score=opponent_score,
        result=result,
        rating_delta=rating_delta,
        coins_reward=coins_reward,
        rank_points_reward=rank_points_reward,
        league_before=league_before,
        league_after=league_after,
        is_overtime=is_overtime,
        is_shootout=is_shootout,
        mvp_title=mvp_title,
        periods=periods,
        events=events,
    )


async def play_quick_match(telegram_id: int) -> MatchPlayResult:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return MatchPlayResult(False, "Открой игру через /start.")

    overview = await get_lineup_overview(profile.id)

    if not overview.is_complete or overview.average_overall is None:
        return MatchPlayResult(False, "Для матча нужно заполнить все 6 слотов состава.")

    lineup_cards = [card for card in overview.slots.values() if card is not None]
    user_ovr = overview.final_overall or overview.average_overall
    opponent_ovr = clamp(user_ovr + random.randint(-4, 4), 55, 99)
    opponent_name = random.choice(BOT_NAMES)
    user_score, opponent_score, is_overtime, is_shootout, periods, events = build_simulation(
        user_ovr=user_ovr,
        opponent_ovr=opponent_ovr,
        lineup_cards=lineup_cards,
        opponent_name=opponent_name,
    )
    mvp_title = choose_scorer(lineup_cards, "Игрок матча") if user_score > opponent_score else f"Лидер {opponent_name}"

    return await save_match_result(
        profile=profile,
        opponent_user_id=None,
        opponent_name=opponent_name,
        opponent_type="bot",
        user_ovr=user_ovr,
        opponent_ovr=opponent_ovr,
        user_score=user_score,
        opponent_score=opponent_score,
        is_overtime=is_overtime,
        is_shootout=is_shootout,
        periods=periods,
        events=events,
        mvp_title=mvp_title,
    )


async def play_player_match(
    first_telegram_id: int,
    second_telegram_id: int,
) -> tuple[MatchPlayResult | None, MatchPlayResult | None]:
    first_profile = await get_player_profile_by_telegram_id(first_telegram_id)
    second_profile = await get_player_profile_by_telegram_id(second_telegram_id)

    if first_profile is None or second_profile is None:
        return None, None

    first_overview = await get_lineup_overview(first_profile.id)
    second_overview = await get_lineup_overview(second_profile.id)

    if (
        not first_overview.is_complete
        or first_overview.average_overall is None
        or not second_overview.is_complete
        or second_overview.average_overall is None
    ):
        return None, None

    first_cards = [card for card in first_overview.slots.values() if card is not None]
    first_ovr = first_overview.final_overall or first_overview.average_overall
    second_ovr = second_overview.final_overall or second_overview.average_overall
    first_score, second_score, is_overtime, is_shootout, periods, events = build_simulation(
        user_ovr=first_ovr,
        opponent_ovr=second_ovr,
        lineup_cards=first_cards,
        opponent_name=second_profile.nickname,
    )
    first_mvp = choose_scorer(first_cards, "Игрок матча") if first_score > second_score else f"Лидер {second_profile.nickname}"
    second_mvp = f"Лидер {second_profile.nickname}" if first_score <= second_score else choose_scorer(first_cards, "Игрок матча")

    first_result = await save_match_result(
        profile=first_profile,
        opponent_user_id=second_profile.id,
        opponent_name=second_profile.nickname,
        opponent_type="player",
        user_ovr=first_ovr,
        opponent_ovr=second_ovr,
        user_score=first_score,
        opponent_score=second_score,
        is_overtime=is_overtime,
        is_shootout=is_shootout,
        periods=periods,
        events=events,
        mvp_title=first_mvp,
    )
    second_result = await save_match_result(
        profile=second_profile,
        opponent_user_id=first_profile.id,
        opponent_name=first_profile.nickname,
        opponent_type="player",
        user_ovr=second_ovr,
        opponent_ovr=first_ovr,
        user_score=second_score,
        opponent_score=first_score,
        is_overtime=is_overtime,
        is_shootout=is_shootout,
        periods=mirror_periods(periods),
        events=events,
        mvp_title=second_mvp,
    )

    return first_result, second_result


async def get_match_history_page(user_id: int, page: int = 1, per_page: int = 5) -> MatchHistoryPage:
    with get_connection() as connection:
        count_cursor = connection.execute(
            "SELECT COUNT(*) AS total_count FROM matches WHERE user_id = ?",
            (user_id,),
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                id,
                opponent_name,
                user_score,
                opponent_score,
                result,
                rating_delta,
                coins_reward,
                league_before,
                league_after,
                created_at
            FROM matches
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, offset),
        )
        rows = cursor.fetchall()

    return MatchHistoryPage(
        matches=[row_to_history_item(row) for row in rows],
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
    )


async def get_match_details(user_id: int, match_id: int) -> MatchDetails | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT *
            FROM matches
            WHERE id = ?
              AND user_id = ?
            """,
            (match_id, user_id),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        event_cursor = connection.execute(
            """
            SELECT period_title, time_text, event_type, description
            FROM match_events
            WHERE match_id = ?
            ORDER BY id ASC
            """,
            (match_id,),
        )
        event_rows = event_cursor.fetchall()

    return MatchDetails(
        id=row["id"],
        opponent_name=row["opponent_name"],
        opponent_type=row["opponent_type"],
        user_lineup_ovr=row["user_lineup_ovr"],
        opponent_lineup_ovr=row["opponent_lineup_ovr"],
        user_score=row["user_score"],
        opponent_score=row["opponent_score"],
        result=row["result"],
        rating_delta=row["rating_delta"],
        coins_reward=row["coins_reward"],
        rank_points_reward=row["rank_points_reward"],
        league_before=row["league_before"],
        league_after=row["league_after"],
        is_overtime=bool(row["is_overtime"]),
        is_shootout=bool(row["is_shootout"]),
        mvp_title=row["mvp_title"],
        periods=periods_from_json(row["periods_summary"]),
        events=[
            MatchEventInfo(
                period_title=event_row["period_title"],
                time_text=event_row["time_text"],
                event_type=event_row["event_type"],
                description=event_row["description"],
            )
            for event_row in event_rows
        ],
        created_at=row["created_at"],
    )
