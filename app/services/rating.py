from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.lineup import get_lineup_overview
from app.services.users import get_player_profile_by_telegram_id


LEAGUE_ORDER = ["NCAA", "AHL", "NHL", "OLYMPICS"]
LEAGUE_TITLES = {
    "NCAA": "NCAA",
    "AHL": "AHL",
    "NHL": "NHL",
    "OLYMPICS": "OLYMPICS",
}
LEAGUE_LIMIT = 1500


@dataclass(frozen=True)
class RatingProfile:
    user_id: int
    nickname: str
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    goals_scored: int
    goals_allowed: int
    lineup_ovr: int | None
    lineup_filled_count: int
    lineup_total_slots: int
    league_place: int | None
    global_place: int | None
    next_league: str | None
    points_to_next_league: int | None


@dataclass(frozen=True)
class LeaderboardEntry:
    place: int
    user_id: int
    nickname: str
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    lineup_ovr: int
    rare_cards_count: int


@dataclass(frozen=True)
class LeaderboardPage:
    entries: list[LeaderboardEntry]
    page: int
    pages_count: int
    total_count: int
    title: str
    mode: str


@dataclass(frozen=True)
class LeagueProgressItem:
    code: str
    title: str
    description: str
    reward: str


def get_next_league(league: str) -> str | None:
    if league not in LEAGUE_ORDER:
        return "AHL"

    current_index = LEAGUE_ORDER.index(league)

    if current_index >= len(LEAGUE_ORDER) - 1:
        return None

    return LEAGUE_ORDER[current_index + 1]


def get_league_order_sql() -> str:
    return """
        CASE users.league
            WHEN 'OLYMPICS' THEN 4
            WHEN 'NHL' THEN 3
            WHEN 'AHL' THEN 2
            ELSE 1
        END
    """


async def get_rating_profile(telegram_id: int) -> RatingProfile | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    lineup = await get_lineup_overview(profile.id)
    next_league = get_next_league(profile.league)
    points_to_next_league = None if next_league is None else max(0, LEAGUE_LIMIT - profile.rating_points)

    return RatingProfile(
        user_id=profile.id,
        nickname=profile.nickname,
        league=profile.league,
        rating_points=profile.rating_points,
        wins=profile.wins,
        losses=profile.losses,
        matches_played=profile.matches_played,
        goals_scored=profile.goals_scored,
        goals_allowed=profile.goals_allowed,
        lineup_ovr=lineup.final_overall,
        lineup_filled_count=lineup.filled_count,
        lineup_total_slots=lineup.total_slots,
        league_place=await get_player_league_place(profile.id, profile.league),
        global_place=await get_player_global_place(profile.id),
        next_league=next_league,
        points_to_next_league=points_to_next_league,
    )


async def get_player_league_place(user_id: int, league: str) -> int | None:
    with get_connection() as connection:
        player_cursor = connection.execute(
            """
            SELECT rating_points, wins, matches_played
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        player = player_cursor.fetchone()

        if player is None:
            return None

        cursor = connection.execute(
            """
            SELECT COUNT(*) AS better_count
            FROM users
            WHERE league = ?
              AND is_banned = 0
              AND (
                    rating_points > ?
                    OR (rating_points = ? AND wins > ?)
                    OR (rating_points = ? AND wins = ? AND matches_played < ?)
                    OR (rating_points = ? AND wins = ? AND matches_played = ? AND id < ?)
              )
            """,
            (
                league,
                player["rating_points"],
                player["rating_points"],
                player["wins"],
                player["rating_points"],
                player["wins"],
                player["matches_played"],
                player["rating_points"],
                player["wins"],
                player["matches_played"],
                user_id,
            ),
        )
        row = cursor.fetchone()

    return int(row["better_count"]) + 1 if row is not None else None


async def get_player_global_place(user_id: int) -> int | None:
    league_order_sql = get_league_order_sql()

    with get_connection() as connection:
        player_cursor = connection.execute(
            f"""
            SELECT
                id,
                league,
                rating_points,
                wins,
                matches_played,
                {league_order_sql} AS league_order
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        player = player_cursor.fetchone()

        if player is None:
            return None

        cursor = connection.execute(
            f"""
            SELECT COUNT(*) AS better_count
            FROM users
            WHERE is_banned = 0
              AND (
                    {league_order_sql} > ?
                    OR ({league_order_sql} = ? AND rating_points > ?)
                    OR ({league_order_sql} = ? AND rating_points = ? AND wins > ?)
                    OR ({league_order_sql} = ? AND rating_points = ? AND wins = ? AND matches_played < ?)
                    OR ({league_order_sql} = ? AND rating_points = ? AND wins = ? AND matches_played = ? AND id < ?)
              )
            """,
            (
                player["league_order"],
                player["league_order"],
                player["rating_points"],
                player["league_order"],
                player["rating_points"],
                player["wins"],
                player["league_order"],
                player["rating_points"],
                player["wins"],
                player["matches_played"],
                player["league_order"],
                player["rating_points"],
                player["wins"],
                player["matches_played"],
                user_id,
            ),
        )
        row = cursor.fetchone()

    return int(row["better_count"]) + 1 if row is not None else None


async def get_global_leaderboard_page(page: int = 1, per_page: int = 5) -> LeaderboardPage:
    return await get_leaderboard_page(
        page=page,
        per_page=per_page,
        mode="global",
        title="📊 Таблица лидеров",
        league=None,
    )


async def get_olympics_leaderboard_page(page: int = 1, per_page: int = 5) -> LeaderboardPage:
    return await get_leaderboard_page(
        page=page,
        per_page=per_page,
        mode="olympics",
        title="🎖 Топ OLYMPICS",
        league="OLYMPICS",
    )


async def get_current_league_leaderboard_page(
    telegram_id: int,
    page: int = 1,
    per_page: int = 5,
) -> LeaderboardPage | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        return None

    return await get_leaderboard_page(
        page=page,
        per_page=per_page,
        mode="league",
        title=f"🏆 Топ лиги {profile.league}",
        league=profile.league,
    )


async def get_leaderboard_page(
    *,
    page: int,
    per_page: int,
    mode: str,
    title: str,
    league: str | None,
) -> LeaderboardPage:
    where_sql = "WHERE users.is_banned = 0"
    params: list[object] = []

    if league is not None:
        where_sql += " AND users.league = ?"
        params.append(league)

    league_order_sql = get_league_order_sql()

    with get_connection() as connection:
        count_cursor = connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM users
            {where_sql}
            """,
            params,
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                users.id,
                users.nickname,
                users.league,
                users.rating_points,
                users.wins,
                users.losses,
                users.matches_played,
                COALESCE(lineup.lineup_ovr, 0) AS lineup_ovr,
                COALESCE(rare_cards.rare_cards_count, 0) AS rare_cards_count
            FROM users
            LEFT JOIN (
                SELECT
                    user_cards.user_id,
                    ROUND(AVG(cards.overall)) AS lineup_ovr
                FROM user_cards
                JOIN cards ON cards.id = user_cards.card_id
                WHERE user_cards.is_in_lineup = 1
                GROUP BY user_cards.user_id
            ) AS lineup ON lineup.user_id = users.id
            LEFT JOIN (
                SELECT
                    user_cards.user_id,
                    COUNT(*) AS rare_cards_count
                FROM user_cards
                JOIN cards ON cards.id = user_cards.card_id
                WHERE cards.rarity IN ('Epic', 'Legendary', 'Event', 'Icon')
                GROUP BY user_cards.user_id
            ) AS rare_cards ON rare_cards.user_id = users.id
            {where_sql}
            ORDER BY
                {league_order_sql} DESC,
                users.rating_points DESC,
                users.wins DESC,
                users.matches_played ASC,
                users.id ASC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    entries: list[LeaderboardEntry] = []

    for index, row in enumerate(rows):
        lineup = await get_lineup_overview(int(row["id"]))
        entries.append(
            LeaderboardEntry(
                place=offset + index + 1,
                user_id=row["id"],
                nickname=row["nickname"],
                league=row["league"],
                rating_points=row["rating_points"],
                wins=row["wins"],
                losses=row["losses"],
                matches_played=row["matches_played"],
                lineup_ovr=int(lineup.final_overall or lineup.average_overall or 0),
                rare_cards_count=int(row["rare_cards_count"] or 0),
            )
        )

    return LeaderboardPage(
        entries=entries,
        page=safe_page,
        pages_count=pages_count,
        total_count=total_count,
        title=title,
        mode=mode,
    )


def get_league_progress_items() -> list[LeagueProgressItem]:
    return [
        LeagueProgressItem(
            code="NCAA",
            title="NCAA",
            description="Стартовая лига. Здесь начинается путь клуба.",
            reward="Переход в AHL: 1 Rank-point",
        ),
        LeagueProgressItem(
            code="AHL",
            title="AHL",
            description="Вторая ступень. Соперники становятся сильнее.",
            reward="Переход в NHL: 1 Rank-point",
        ),
        LeagueProgressItem(
            code="NHL",
            title="NHL",
            description="Главная лига перед олимпийским уровнем.",
            reward="Переход в OLYMPICS: 2 Rank-point",
        ),
        LeagueProgressItem(
            code="OLYMPICS",
            title="OLYMPICS",
            description="Высшая лига. Здесь формируется главный топ игроков.",
            reward="Вылет отключён. Открывается настройка команды.",
        ),
    ]
