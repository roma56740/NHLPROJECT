from dataclasses import dataclass

from aiogram.types import User as TelegramUser

from app.database.db import get_connection
from app.services.currencies import CurrencyBalance, ensure_user_balances, get_user_balances
from app.services.hockey_pass import get_active_pass_row
from app.services.starter_kit import give_starter_kit_to_new_user


@dataclass(frozen=True)
class PlayerProfile:
    id: int
    telegram_id: int
    nickname: str
    username: str | None
    league: str
    rating_points: int
    wins: int
    losses: int
    matches_played: int
    goals_scored: int
    goals_allowed: int
    bp_points: int
    hockey_pass_level: int
    premium_pass: bool
    hockey_pass_title: str | None
    hockey_pass_premium_active: bool
    team_name: str | None
    team_country: str | None
    team_logo_path: str | None
    privacy_public_cards: bool
    is_banned: bool
    is_new: bool
    balances: list[CurrencyBalance]
    is_creator: bool = False


TEAM_PROFILE_LEAGUE = "OLYMPICS"


def build_nickname(telegram_user: TelegramUser) -> str:
    if telegram_user.username:
        return telegram_user.username

    full_name = telegram_user.full_name.strip()

    if full_name:
        return full_name

    return f"Player {telegram_user.id}"


def can_edit_team_profile(profile: PlayerProfile) -> bool:
    return profile.league == TEAM_PROFILE_LEAGUE


async def register_or_update_player(telegram_user: TelegramUser) -> PlayerProfile:
    with get_connection() as connection:
        cursor = connection.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_user.id,),
        )
        existing_user = cursor.fetchone()

        nickname = build_nickname(telegram_user)
        username = telegram_user.username
        first_name = telegram_user.first_name
        last_name = telegram_user.last_name
        is_new = existing_user is None

        if is_new:
            connection.execute(
                """
                INSERT INTO users (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    nickname
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    telegram_user.id,
                    username,
                    first_name,
                    last_name,
                    nickname,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE users
                SET
                    username = ?,
                    first_name = ?,
                    last_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (
                    username,
                    first_name,
                    last_name,
                    telegram_user.id,
                ),
            )

        connection.commit()

    user_row = await get_player_row_by_telegram_id(telegram_user.id)

    if user_row is None:
        raise RuntimeError("Не удалось создать профиль игрока")

    await ensure_user_balances(user_row["id"], is_new_player=is_new)

    if is_new:
        await give_starter_kit_to_new_user(user_row["id"])

    balances = await get_user_balances(user_row["id"])
    hockey_pass_title, hockey_pass_premium_active = await get_active_player_hockey_pass_state(user_row["id"])

    return build_player_profile(
        user_row,
        balances,
        is_new=is_new,
        hockey_pass_title=hockey_pass_title,
        hockey_pass_premium_active=hockey_pass_premium_active,
    )


async def get_player_profile_by_telegram_id(telegram_id: int) -> PlayerProfile | None:
    user_row = await get_player_row_by_telegram_id(telegram_id)

    if user_row is None:
        return None

    balances = await get_user_balances(user_row["id"])
    hockey_pass_title, hockey_pass_premium_active = await get_active_player_hockey_pass_state(user_row["id"])

    return build_player_profile(
        user_row,
        balances,
        is_new=False,
        hockey_pass_title=hockey_pass_title,
        hockey_pass_premium_active=hockey_pass_premium_active,
    )


async def toggle_player_cards_privacy(telegram_id: int) -> PlayerProfile | None:
    user_row = await get_player_row_by_telegram_id(telegram_id)

    if user_row is None:
        return None

    new_value = 0 if int(user_row["privacy_public_cards"]) == 1 else 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                privacy_public_cards = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            """,
            (new_value, telegram_id),
        )
        connection.commit()

    return await get_player_profile_by_telegram_id(telegram_id)


async def update_player_nickname(telegram_id: int, nickname: str) -> PlayerProfile | None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                nickname = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            """,
            (nickname, telegram_id),
        )
        connection.commit()

    return await get_player_profile_by_telegram_id(telegram_id)


async def update_player_team_name(telegram_id: int, team_name: str) -> PlayerProfile | None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                team_name = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            """,
            (team_name, telegram_id),
        )
        connection.commit()

    return await get_player_profile_by_telegram_id(telegram_id)


async def update_player_team_country(telegram_id: int, team_country: str) -> PlayerProfile | None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                team_country = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            """,
            (team_country, telegram_id),
        )
        connection.commit()

    return await get_player_profile_by_telegram_id(telegram_id)


async def update_player_team_logo_path(telegram_id: int, team_logo_path: str) -> PlayerProfile | None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET
                team_logo_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
            """,
            (team_logo_path, telegram_id),
        )
        connection.commit()

    return await get_player_profile_by_telegram_id(telegram_id)


async def get_active_player_hockey_pass_state(user_id: int) -> tuple[str | None, bool]:
    with get_connection() as connection:
        pass_row = await get_active_pass_row(connection)

        if pass_row is None:
            return None, False

        connection.execute(
            """
            INSERT INTO user_hockey_passes (user_id, pass_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, pass_id) DO NOTHING
            """,
            (user_id, pass_row["id"]),
        )
        user_pass_row = connection.execute(
            """
            SELECT premium_unlocked
            FROM user_hockey_passes
            WHERE user_id = ? AND pass_id = ?
            """,
            (user_id, pass_row["id"]),
        ).fetchone()
        connection.commit()

    return pass_row["title"], bool(user_pass_row and user_pass_row["premium_unlocked"])


def build_player_profile(
    row,
    balances: list[CurrencyBalance],
    is_new: bool,
    hockey_pass_title: str | None = None,
    hockey_pass_premium_active: bool = False,
) -> PlayerProfile:
    return PlayerProfile(
        id=row["id"],
        telegram_id=row["telegram_id"],
        nickname=row["nickname"],
        username=row["username"],
        league=row["league"],
        rating_points=row["rating_points"],
        wins=row["wins"],
        losses=row["losses"],
        matches_played=row["matches_played"],
        goals_scored=row["goals_scored"],
        goals_allowed=row["goals_allowed"],
        bp_points=row["bp_points"],
        hockey_pass_level=row["hockey_pass_level"],
        premium_pass=bool(row["premium_pass"]),
        hockey_pass_title=hockey_pass_title,
        hockey_pass_premium_active=hockey_pass_premium_active,
        team_name=row["team_name"],
        team_country=row["team_country"],
        team_logo_path=row["team_logo_path"],
        privacy_public_cards=bool(row["privacy_public_cards"]),
        is_banned=bool(row["is_banned"]),
        is_new=is_new,
        balances=balances,
        is_creator=bool(row["is_creator"]) if "is_creator" in row.keys() else False,
    )


async def get_player_row_by_telegram_id(telegram_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                id,
                telegram_id,
                username,
                nickname,
                league,
                rating_points,
                wins,
                losses,
                matches_played,
                goals_scored,
                goals_allowed,
                bp_points,
                hockey_pass_level,
                premium_pass,
                team_name,
                team_country,
                team_logo_path,
                privacy_public_cards,
                is_banned,
                is_creator
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        return cursor.fetchone()


async def is_player_banned(telegram_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT is_banned
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return False

    return bool(row["is_banned"])
