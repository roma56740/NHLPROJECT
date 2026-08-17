"""RANKED MODE (v1) — доступ, сезон, подбор соперника, матч, рейтинг/лиги/XP.

Соперник ищется МГНОВЕННО (без очереди ожидания), тем же паттерном, что уже
проверен в этой сессии на CLAN WAR 2.0 (app.services.war2_core.find_war2_opponent) —
осознанное упрощение против дословного "как enter_matchmaking()": реальный
enter_matchmaking() опирается на фоновый watcher-таск и per-поиск sleep-таски,
привязанные к конкретному chat_id/message_id в хендлере — воспроизводить эту
инфраструктуру для Ranked v1 означало бы дублировать довольно много сложной async
инфраструктуры ради результата, который мгновенный подбор уже даёт игроку (реальный
соперник подходящего уровня, либо бот). См. docs/RANKED_MODE_SPEC.md.

`record_ranked_match_result()` намеренно НЕ вызывает `matches.save_match_result()` —
та безусловно меняет `users.matches_played/wins/losses/rating_points/league`
(обычная лестница). Переиспользована только математика (`build_simulation`/
`choose_scorer`/`calculate_rating_delta`), не побочные эффекты записи — тот же
принцип, что и в war2_core.py.
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass, replace

from app.database.db import get_connection
from app.services import match_guard
from app.services.lineup import LineupCard, LineupOverview, get_lineup_overview, get_user_league
from app.services.matches import (
    LEAGUES,
    MatchEventInfo,
    MatchPeriodSummary,
    calculate_rating_delta,
    choose_scorer,
    simulate_period,
    weighted_success,
)
from app.services import ranked_bot, ranked_bot_names, ranked_captain
from app.services.ranked_common import RankedError
from app.services.salary import RANKED_SALARY_CAP, format_salary
from app.services.users import get_player_profile_by_telegram_id

RANKED_ELIGIBLE_LEAGUES = ("AHL", "NHL", "OLYMPICS")
DEFAULT_PLAYER_RATING = 1000
DEFAULT_SEASON_LENGTH_DAYS = 56


def is_ranked_eligible(league: str | None) -> bool:
    """RANKED ACCESS: AHL и выше. Переиспользует существующий порядок лиг
    (app.services.matches.LEAGUES), новый список лиг не изобретается."""
    if league not in LEAGUES:
        return False
    return LEAGUES.index(league) >= LEAGUES.index("AHL")


@dataclass(frozen=True)
class RankedSeason:
    id: int
    season_number: int
    status: str
    starts_at: str | None
    ends_at: str | None


@dataclass(frozen=True)
class RankedOpponent:
    user_id: int | None
    name: str
    type: str  # 'player' | 'bot'
    bot_overview: LineupOverview | None = None


@dataclass(frozen=True)
class RankedLeagueInfo:
    id: int
    division_code: str
    tier_number: int
    title: str
    min_points: int
    icon: str


@dataclass(frozen=True)
class RankedPlayerStats:
    season_id: int
    user_id: int
    rank_points: int
    ranked_league_id: int | None
    ranked_xp: int
    wins: int
    losses: int
    matches_played: int


@dataclass(frozen=True)
class RankedMatchResult:
    match_id: int
    user_score: int
    opponent_score: int
    result: str
    rank_delta: int
    mvp_title: str
    is_overtime: bool
    is_shootout: bool
    periods: list[MatchPeriodSummary]
    events: list[MatchEventInfo]
    new_league: RankedLeagueInfo | None
    league_up: bool
    opponent_name: str
    opponent_type: str
    opponent_user_id: int | None
    opponent_bot_overview: LineupOverview | None
    pending_shootout: bool = False
    shootout_user_goals: int = 0
    shootout_opponent_goals: int = 0
    shootout_log: tuple[dict[str, object], ...] = ()
    user_id: int = 0
    season_id: int | None = None
    user_ovr: int = 0
    opponent_ovr: int = 0
    lineup_cards: tuple[LineupCard, ...] = ()


def _row_to_season(row: sqlite3.Row) -> RankedSeason:
    return RankedSeason(
        id=int(row["id"]),
        season_number=int(row["season_number"]),
        status=row["status"],
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
    )


def _row_to_league(row: sqlite3.Row) -> RankedLeagueInfo:
    return RankedLeagueInfo(
        id=int(row["id"]),
        division_code=row["division_code"],
        tier_number=int(row["tier_number"]),
        title=row["title"],
        min_points=int(row["min_points"]),
        icon=row["icon"],
    )


async def get_active_season() -> RankedSeason | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM ranked_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _row_to_season(row) if row is not None else None


async def compute_ranked_division(rank_points: int) -> RankedLeagueInfo | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM ranked_leagues WHERE active = 1 AND min_points <= ? ORDER BY min_points DESC LIMIT 1",
            (rank_points,),
        ).fetchone()
    return _row_to_league(row) if row is not None else None


async def get_ranked_stats(user_id: int, season_id: int) -> RankedPlayerStats:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM ranked_player_stats WHERE season_id = ? AND user_id = ?",
            (season_id, user_id),
        ).fetchone()
    if row is None:
        return RankedPlayerStats(season_id, user_id, 0, None, 0, 0, 0, 0)
    return RankedPlayerStats(
        season_id=season_id,
        user_id=user_id,
        rank_points=int(row["rank_points"]),
        ranked_league_id=int(row["ranked_league_id"]) if row["ranked_league_id"] is not None else None,
        ranked_xp=int(row["ranked_xp"]),
        wins=int(row["wins"]),
        losses=int(row["losses"]),
        matches_played=int(row["matches_played"]),
    )


async def find_ranked_opponent(user_id: int, season_id: int | None, user_ovr: int) -> RankedOpponent:
    """Return a Ranked bot matched to the player's OVR.

    Ranked is asynchronous and does not require another Telegram user to be
    online. Therefore real user accounts are no longer selected as opponents.
    Every search creates a bot whose cards are exactly the player's effective OVR
    or +1 (99 max), using only real active cards from the global catalog.
    """
    del season_id  # kept in the signature for call-site/API stability

    user_league = await get_user_league(user_id)
    target_ovr = ranked_bot.pick_match_target_ovr(user_ovr)
    bot_result = await ranked_bot.build_bot_lineup(user_league, target_ovr=target_ovr)

    if not bot_result.overview.is_complete:
        raise RankedError(
            "BOT_CATALOG_INCOMPLETE",
            f"Для Ranked-бота {target_ovr} OVR не хватает реальных карт нужных позиций в каталоге.",
        )

    recent_names: set[str] = set()
    try:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT opponent_name
                FROM ranked_matches
                WHERE user_id = ? AND opponent_type = 'bot'
                ORDER BY id DESC
                LIMIT 8
                """,
                (user_id,),
            ).fetchall()
        recent_names = {str(row["opponent_name"]) for row in rows if row["opponent_name"]}
    except Exception:
        recent_names = set()

    bot_name = ranked_bot_names.pick_nickname(exclude=recent_names)
    return RankedOpponent(user_id=None, name=bot_name, type="bot", bot_overview=bot_result.overview)


def _credit_currency(connection: sqlite3.Connection, user_id: int, currency_code: str, amount: int) -> None:
    if amount <= 0:
        return
    connection.execute(
        """
        INSERT INTO currency_balances (user_id, currency_code, amount) VALUES (?, ?, ?)
        ON CONFLICT(user_id, currency_code) DO UPDATE SET amount = amount + excluded.amount, updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, currency_code, amount),
    )


async def _grant_league_reward(connection: sqlite3.Connection, user_id: int, season_id: int, league: RankedLeagueInfo) -> None:
    """Идемпотентная выдача награды лиги при первом достижении за сезон (раздел RANK
    REWARDS ТЗ) — вставка в claims-таблицу и сама выдача в одной транзакции с
    обновлением рейтинга, поэтому демоушен-затем-повторный-подъём в течение сезона
    не выдаёт награду повторно."""
    try:
        connection.execute(
            "INSERT INTO ranked_league_reward_claims (user_id, season_id, ranked_league_id) VALUES (?, ?, ?)",
            (user_id, season_id, league.id),
        )
    except sqlite3.IntegrityError:
        return  # уже получена в этом сезоне

    reward_rows = connection.execute(
        "SELECT * FROM ranked_league_rewards WHERE ranked_league_id = ? AND active = 1", (league.id,)
    ).fetchall()
    for reward in reward_rows:
        if reward["reward_type"] == "currency" and reward["currency_code"]:
            _credit_currency(connection, user_id, reward["currency_code"], int(reward["amount"]))
        elif reward["reward_type"] == "cosmetic" and reward["cosmetic_item_id"]:
            item = connection.execute(
                "SELECT type, rarity FROM war2_cosmetic_items WHERE id = ?", (reward["cosmetic_item_id"],)
            ).fetchone()
            if item is not None:
                connection.execute(
                    """
                    INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source)
                    VALUES (?, ?, ?, ?, 'ranked_league_reward')
                    """,
                    (user_id, reward["cosmetic_item_id"], item["type"], item["rarity"]),
                )
        elif reward["reward_type"] == "pack" and reward["pack_id"]:
            # ranked_league_rewards.pack_id ссылается на ranked_packs (тематический,
            # по дивизиону), НЕ на общий packs — см. ranked_pass_rewards, где наоборот
            # используется общий packs (та же семантика, что и у hockey_pass_rewards).
            connection.execute(
                """
                INSERT INTO user_ranked_packs (user_id, pack_id, quantity) VALUES (?, ?, 1)
                ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + 1, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, reward["pack_id"]),
            )


async def _award_ranked_xp(connection: sqlite3.Connection, user_id: int, season_id: int, amount: int) -> None:
    if amount <= 0:
        return
    connection.execute(
        """
        UPDATE ranked_player_stats SET ranked_xp = ranked_xp + ? WHERE season_id = ? AND user_id = ?
        """,
        (amount, season_id, user_id),
    )


async def _simulate_ranked_regulation(
    *,
    user_ovr: int,
    opponent_ovr: int,
    lineup_cards: list[LineupCard],
    opponent_name: str,
) -> tuple[int, int, bool, list[MatchPeriodSummary], list[MatchEventInfo]]:
    """Simulate three periods and sometimes deliberately produce a regulation tie.

    Unlike the ordinary-mode ``build_simulation`` this function never resolves a
    tie automatically.  A tie is handed to the interactive Telegram shootout.
    The chance is editable from the admin settings screen.
    """
    from app.services.settings import get_int_setting

    chance_percent = await get_int_setting(
        "ranked_shootout_chance_percent", 20, minimum=0, maximum=100
    )
    force_tie = random.randrange(100) < chance_percent
    attempts = 12 if force_tie else 1

    periods: list[MatchPeriodSummary] = []
    events: list[MatchEventInfo] = []
    user_score = 0
    opponent_score = 0

    for _ in range(attempts):
        periods = []
        events = []
        for number in range(1, 4):
            period, period_events = simulate_period(
                number, user_ovr, opponent_ovr, lineup_cards, opponent_name
            )
            periods.append(period)
            events.extend(period_events)
        user_score = sum(period.user_goals for period in periods)
        opponent_score = sum(period.opponent_goals for period in periods)
        if not force_tie or user_score == opponent_score:
            break

    if force_tie and user_score != opponent_score:
        # Preserve the generated match, but add a late comeback to make the
        # configured shootout chance exact even when repeated simulations did not
        # naturally end level.
        gap = abs(user_score - opponent_score)
        last = periods[-1]
        if user_score < opponent_score:
            user_score += gap
            periods[-1] = replace(last, user_goals=last.user_goals + gap)
            for index in range(gap):
                scorer = choose_scorer(lineup_cards, "Твой игрок")
                events.append(
                    MatchEventInfo(
                        "3-й период",
                        f"19:{40 + min(index * 2, 18):02d}",
                        "GOAL",
                        f"{scorer} сравнивает счёт",
                    )
                )
        else:
            opponent_score += gap
            periods[-1] = replace(last, opponent_goals=last.opponent_goals + gap)
            for index in range(gap):
                events.append(
                    MatchEventInfo(
                        "3-й период",
                        f"19:{40 + min(index * 2, 18):02d}",
                        "GOAL",
                        f"{opponent_name} сравнивает счёт",
                    )
                )

    return user_score, opponent_score, user_score == opponent_score, periods, events


async def _commit_ranked_match(
    *,
    profile_id: int,
    season_id: int | None,
    opponent: RankedOpponent,
    user_ovr: int,
    opponent_ovr: int,
    lineup_cards: tuple[LineupCard, ...],
    user_score: int,
    opponent_score: int,
    regulation_user_score: int,
    regulation_opponent_score: int,
    is_shootout: bool,
    periods: list[MatchPeriodSummary],
    events: list[MatchEventInfo],
    shootout_user_goals: int = 0,
    shootout_opponent_goals: int = 0,
    shootout_log: tuple[dict[str, object], ...] = (),
) -> RankedMatchResult:
    is_win = user_score > opponent_score
    result = "win" if is_win else "loss"
    rank_delta = calculate_rating_delta(user_ovr, opponent_ovr, is_win)
    mvp_title = (
        choose_scorer(list(lineup_cards), "Игрок матча")
        if is_win
        else f"Лидер {opponent.name}"
    )

    new_league: RankedLeagueInfo | None = None
    league_up = False

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        stats_row = (
            connection.execute(
                "SELECT rank_points FROM ranked_player_stats WHERE season_id = ? AND user_id = ?",
                (season_id, profile_id),
            ).fetchone()
            if season_id is not None
            else None
        )
        current_points = int(stats_row["rank_points"]) if stats_row else 0

        old_division_code: str | None = None
        division_before = "—"
        if season_id is not None:
            before_row = connection.execute(
                "SELECT title, division_code FROM ranked_leagues WHERE active = 1 AND min_points <= ? ORDER BY min_points DESC LIMIT 1",
                (current_points,),
            ).fetchone()
            division_before = before_row["title"] if before_row else "—"
            old_division_code = before_row["division_code"] if before_row else None

            new_points = max(0, current_points + rank_delta)
            connection.execute(
                """
                INSERT INTO ranked_player_stats (season_id, user_id, rank_points, wins, losses, matches_played)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(season_id, user_id) DO UPDATE SET
                    rank_points = ?,
                    wins = wins + ?,
                    losses = losses + ?,
                    matches_played = matches_played + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    season_id,
                    profile_id,
                    new_points,
                    1 if is_win else 0,
                    0 if is_win else 1,
                    new_points,
                    1 if is_win else 0,
                    0 if is_win else 1,
                ),
            )

            new_league_row = connection.execute(
                "SELECT * FROM ranked_leagues WHERE active = 1 AND min_points <= ? ORDER BY min_points DESC LIMIT 1",
                (new_points,),
            ).fetchone()
            new_league = _row_to_league(new_league_row) if new_league_row is not None else None
            if new_league is not None:
                connection.execute(
                    "UPDATE ranked_player_stats SET ranked_league_id = ? WHERE season_id = ? AND user_id = ?",
                    (new_league.id, season_id, profile_id),
                )
                await _grant_league_reward(connection, profile_id, season_id, new_league)
                league_up = new_league.division_code != old_division_code

            from app.services.settings import get_int_setting

            xp_per_match = await get_int_setting("ranked_xp_per_match", 20, minimum=0)
            xp_win_bonus = await get_int_setting("ranked_xp_win_bonus", 30, minimum=0)
            xp_division_bonus = await get_int_setting(
                "ranked_xp_division_up_bonus", 150, minimum=0
            )
            xp_total = (
                xp_per_match
                + (xp_win_bonus if is_win else 0)
                + (xp_division_bonus if league_up else 0)
            )
            await _award_ranked_xp(connection, profile_id, season_id, xp_total)

        match_cursor = connection.execute(
            """
            INSERT INTO ranked_matches
                (season_id, user_id, opponent_user_id, opponent_name, opponent_type,
                 user_score, opponent_score, result, rank_delta, division_before, division_after,
                 is_shootout, regulation_user_score, regulation_opponent_score,
                 shootout_user_goals, shootout_opponent_goals, shootout_log_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                season_id,
                profile_id,
                opponent.user_id,
                opponent.name,
                opponent.type,
                user_score,
                opponent_score,
                result,
                rank_delta,
                division_before,
                new_league.title if new_league else "—",
                int(is_shootout),
                regulation_user_score,
                regulation_opponent_score,
                shootout_user_goals,
                shootout_opponent_goals,
                json.dumps(list(shootout_log), ensure_ascii=False),
            ),
        )
        match_id = int(match_cursor.lastrowid)
        connection.commit()

    return RankedMatchResult(
        match_id=match_id,
        user_score=user_score,
        opponent_score=opponent_score,
        result=result,
        rank_delta=rank_delta,
        mvp_title=mvp_title,
        is_overtime=False,
        is_shootout=is_shootout,
        periods=periods,
        events=events,
        new_league=new_league,
        league_up=league_up,
        opponent_name=opponent.name,
        opponent_type=opponent.type,
        opponent_user_id=opponent.user_id,
        opponent_bot_overview=opponent.bot_overview,
        pending_shootout=False,
        shootout_user_goals=shootout_user_goals,
        shootout_opponent_goals=shootout_opponent_goals,
        shootout_log=shootout_log,
        user_id=profile_id,
        season_id=season_id,
        user_ovr=user_ovr,
        opponent_ovr=opponent_ovr,
        lineup_cards=lineup_cards,
    )


async def play_ranked_match(telegram_id: int, *, interactive_shootout: bool = False) -> RankedMatchResult:
    """Prepare and, unless tied, immediately commit a Ranked match.

    A regulation tie remains pending so the handler can run the 4-corner
    interactive shootout before rating, XP and history are committed.
    """
    profile = await get_player_profile_by_telegram_id(telegram_id)
    if profile is None:
        raise RankedError("PROFILE_NOT_FOUND", "Открой игру через /start.")

    if not is_ranked_eligible(profile.league):
        raise RankedError(
            "LEAGUE_TOO_LOW",
            "Ranked Mode доступен только игрокам лиги AHL и выше. Поднимись до AHL в обычном режиме.",
        )

    overview = await get_lineup_overview(profile.id)
    if not overview.is_complete or overview.average_overall is None:
        raise RankedError(
            "LINEUP_INCOMPLETE", "Для Ranked-матча нужно заполнить все 6 слотов состава."
        )

    captain_status = await ranked_captain.get_captain_status(profile.id)
    if overview.salary_total > captain_status.effective_cap:
        bonus_note = (
            f" (база {format_salary(captain_status.base_cap)} + бонус капитана {format_salary(captain_status.bonus_amount)})"
            if captain_status.bonus_amount
            else ""
        )
        raise RankedError(
            "SALARY_CAP_EXCEEDED",
            f"Потолок зарплат Ranked превышен. Лимит: {format_salary(captain_status.effective_cap)}{bonus_note}, "
            f"твой состав: {format_salary(overview.salary_total)}. Превышение: "
            f"{format_salary(overview.salary_total - captain_status.effective_cap)}. "
            "Замени дорогую карту в составе или верни бонус капитана.",
        )

    lock = await match_guard.acquire_player_match_lock(profile.id, "ranked", ttl_seconds=900)
    if not lock.acquired:
        detail = (
            await match_guard.describe_active_match_short(lock.existing)
            if lock.existing
            else ""
        )
        raise RankedError(
            "MATCH_ALREADY_ACTIVE",
            f"У вас уже идёт матч, дождитесь его завершения. {detail}".strip(),
        )

    try:
        season = await get_active_season()
        season_id = season.id if season else None
        lineup_cards = tuple(card for card in overview.slots.values() if card is not None)
        user_ovr = overview.final_overall or overview.average_overall
        opponent = await find_ranked_opponent(profile.id, season_id, user_ovr)
        opponent_ovr = await _resolve_opponent_ovr(opponent, user_ovr)

        user_score, opponent_score, tied, periods, events = await _simulate_ranked_regulation(
            user_ovr=user_ovr,
            opponent_ovr=opponent_ovr,
            lineup_cards=list(lineup_cards),
            opponent_name=opponent.name,
        )

        if tied and interactive_shootout:
            await match_guard.heartbeat_lock(profile.id, extend_seconds=900)
            return RankedMatchResult(
                match_id=0,
                user_score=user_score,
                opponent_score=opponent_score,
                result="pending",
                rank_delta=0,
                mvp_title="",
                is_overtime=False,
                is_shootout=True,
                periods=periods,
                events=events,
                new_league=None,
                league_up=False,
                opponent_name=opponent.name,
                opponent_type=opponent.type,
                opponent_user_id=opponent.user_id,
                opponent_bot_overview=opponent.bot_overview,
                pending_shootout=True,
                user_id=profile.id,
                season_id=season_id,
                user_ovr=user_ovr,
                opponent_ovr=opponent_ovr,
                lineup_cards=lineup_cards,
            )

        auto_shootout = tied
        auto_user_won = weighted_success(user_ovr, opponent_ovr) if auto_shootout else False
        final_user_score = user_score + (1 if auto_shootout and auto_user_won else 0)
        final_opponent_score = opponent_score + (1 if auto_shootout and not auto_user_won else 0)
        auto_log: tuple[dict[str, object], ...] = ()
        if auto_shootout:
            auto_log = ({
                "round": 0,
                "phase": "automatic_fallback",
                "goal": True,
                "winner": "user" if auto_user_won else "opponent",
            },)
            events.append(
                MatchEventInfo(
                    "Буллиты",
                    "SO",
                    "GOAL" if auto_user_won else "SAVE",
                    "Автоматическое завершение серии буллитов",
                )
            )

        committed = await _commit_ranked_match(
            profile_id=profile.id,
            season_id=season_id,
            opponent=opponent,
            user_ovr=user_ovr,
            opponent_ovr=opponent_ovr,
            lineup_cards=lineup_cards,
            user_score=final_user_score,
            opponent_score=final_opponent_score,
            regulation_user_score=user_score,
            regulation_opponent_score=opponent_score,
            is_shootout=auto_shootout,
            periods=periods,
            events=events,
            shootout_user_goals=1 if auto_shootout and auto_user_won else 0,
            shootout_opponent_goals=1 if auto_shootout and not auto_user_won else 0,
            shootout_log=auto_log,
        )
    except Exception:
        await match_guard.cancel_match(profile.id, reason="RANKED_MATCH_ERROR")
        raise

    await match_guard.finalize_match(
        profile.id, match_id=committed.match_id, reason="COMPLETED"
    )
    return committed


async def finalize_ranked_shootout(
    pending: RankedMatchResult,
    *,
    user_won: bool,
    shootout_user_goals: int,
    shootout_opponent_goals: int,
    shootout_log: list[dict[str, object]],
) -> RankedMatchResult:
    """Atomically commit a pending interactive shootout and release MatchGuard."""
    if not pending.pending_shootout or not pending.is_shootout:
        raise RankedError("SHOOTOUT_NOT_PENDING", "Серия буллитов уже завершена.")
    if pending.user_id <= 0 or pending.user_score != pending.opponent_score:
        raise RankedError("SHOOTOUT_BAD_STATE", "Некорректное состояние серии буллитов.")

    opponent = RankedOpponent(
        user_id=pending.opponent_user_id,
        name=pending.opponent_name,
        type=pending.opponent_type,
        bot_overview=pending.opponent_bot_overview,
    )
    final_user_score = pending.user_score + (1 if user_won else 0)
    final_opponent_score = pending.opponent_score + (0 if user_won else 1)
    final_events = list(pending.events)
    final_events.append(
        MatchEventInfo(
            "Буллиты",
            "SO",
            "GOAL" if user_won else "SAVE",
            (
                f"Ты выигрываешь серию буллитов {shootout_user_goals}:{shootout_opponent_goals}"
                if user_won
                else f"{pending.opponent_name} выигрывает серию буллитов {shootout_opponent_goals}:{shootout_user_goals}"
            ),
        )
    )

    try:
        committed = await _commit_ranked_match(
            profile_id=pending.user_id,
            season_id=pending.season_id,
            opponent=opponent,
            user_ovr=pending.user_ovr,
            opponent_ovr=pending.opponent_ovr,
            lineup_cards=pending.lineup_cards,
            user_score=final_user_score,
            opponent_score=final_opponent_score,
            regulation_user_score=pending.user_score,
            regulation_opponent_score=pending.opponent_score,
            is_shootout=True,
            periods=pending.periods,
            events=final_events,
            shootout_user_goals=shootout_user_goals,
            shootout_opponent_goals=shootout_opponent_goals,
            shootout_log=tuple(shootout_log),
        )
    except Exception:
        await match_guard.cancel_match(pending.user_id, reason="RANKED_SHOOTOUT_ERROR")
        raise

    await match_guard.finalize_match(
        pending.user_id, match_id=committed.match_id, reason="RANKED_SHOOTOUT_COMPLETED"
    )
    return committed


async def _resolve_opponent_ovr(opponent: RankedOpponent, user_ovr: int) -> int:
    if opponent.type == "bot":
        # Matchmaking target is the printed/base OVR of the bot cards. Chemistry is
        # still displayed in the lineup render, but must not secretly turn a 95 bot
        # into a 98 opponent after matchmaking selected 95.
        if opponent.bot_overview is not None:
            return opponent.bot_overview.average_overall or user_ovr
        return user_ovr

    from app.services.lineup import get_lineup_overview as _get_overview

    opponent_overview = await _get_overview(opponent.user_id)
    return opponent_overview.final_overall or opponent_overview.average_overall or user_ovr


async def start_ranked_season() -> RankedSeason:
    from datetime import datetime, timedelta, timezone

    from app.services.settings import get_int_setting

    length_days = await get_int_setting("ranked_season_length_days", DEFAULT_SEASON_LENGTH_DAYS, minimum=1)
    with get_connection() as connection:
        existing_active = connection.execute("SELECT id FROM ranked_seasons WHERE status = 'active'").fetchone()
        if existing_active is not None:
            raise RankedError("SEASON_ALREADY_ACTIVE", "Уже есть активный Ranked-сезон.")

        last = connection.execute("SELECT MAX(season_number) AS n FROM ranked_seasons").fetchone()
        next_number = int(last["n"] or 0) + 1
        starts_at = datetime.now(timezone.utc)
        ends_at = starts_at + timedelta(days=length_days)
        cursor = connection.execute(
            "INSERT INTO ranked_seasons (season_number, status, starts_at, ends_at) VALUES (?, 'active', ?, ?)",
            (next_number, starts_at.strftime("%Y-%m-%d %H:%M:%S"), ends_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
        season_id = int(cursor.lastrowid)
        connection.commit()

    return RankedSeason(id=season_id, season_number=next_number, status="active", starts_at=starts_at.strftime("%Y-%m-%d %H:%M:%S"), ends_at=ends_at.strftime("%Y-%m-%d %H:%M:%S"))


async def end_ranked_season() -> None:
    """SEASON ЗАВЕРШЕНИЕ: снимок топ-25 + reset рейтинга (новый сезон стартует с 0 —
    ranked_player_stats архивные строки НЕ удаляются, у нового season_id их просто
    ещё нет, тот же приём, что и в war2_core.end-of-season — см. war2_core.py)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        active = connection.execute("SELECT id FROM ranked_seasons WHERE status = 'active'").fetchone()
        if active is None:
            connection.rollback()
            raise RankedError("NO_ACTIVE_SEASON", "Нет активного Ranked-сезона.")
        season_id = int(active["id"])

        top_rows = connection.execute(
            """
            SELECT users.nickname, ranked_player_stats.rank_points
            FROM ranked_player_stats
            JOIN users ON users.id = ranked_player_stats.user_id
            WHERE ranked_player_stats.season_id = ?
            ORDER BY ranked_player_stats.rank_points DESC
            LIMIT 25
            """,
            (season_id,),
        ).fetchall()
        top_json = json.dumps([{"nickname": row["nickname"], "rank_points": row["rank_points"]} for row in top_rows], ensure_ascii=False)

        connection.execute(
            "UPDATE ranked_seasons SET status = 'ended', top_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (top_json, season_id),
        )
        connection.commit()


@dataclass(frozen=True)
class RankedMatchHistoryItem:
    id: int
    opponent_name: str
    opponent_type: str
    user_score: int
    opponent_score: int
    result: str
    rank_delta: int
    created_at: str


async def get_match_history(user_id: int, limit: int = 10) -> list[RankedMatchHistoryItem]:
    """RANK SYSTEM ТЗ: "история матчей"."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM ranked_matches WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [
        RankedMatchHistoryItem(
            id=int(row["id"]), opponent_name=row["opponent_name"], opponent_type=row["opponent_type"],
            user_score=int(row["user_score"]), opponent_score=int(row["opponent_score"]),
            result=row["result"], rank_delta=int(row["rank_delta"]), created_at=row["created_at"],
        )
        for row in rows
    ]


async def get_ranked_leaderboard(season_id: int, limit: int = 20) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT users.nickname, ranked_player_stats.rank_points, ranked_leagues.title AS league_title
            FROM ranked_player_stats
            JOIN users ON users.id = ranked_player_stats.user_id
            LEFT JOIN ranked_leagues ON ranked_leagues.id = ranked_player_stats.ranked_league_id
            WHERE ranked_player_stats.season_id = ?
            ORDER BY ranked_player_stats.rank_points DESC
            LIMIT ?
            """,
            (season_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
