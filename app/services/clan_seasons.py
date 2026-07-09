import json
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.clan_wars import pay_clan_members
from app.services.rewards import grant_pack


@dataclass(frozen=True)
class ClanTierReward:
    place: int
    coins: int
    rubles: int
    pack_id: int | None
    pack_name: str | None


@dataclass(frozen=True)
class ClanSeasonResetResult:
    season_number: int
    clans_count: int
    rewarded_count: int
    top: list[tuple[int, str, int, int]]  # place, clan, rating, wins


async def get_clan_reward_tiers() -> list[ClanTierReward]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT t.place, t.coins, t.rubles, t.pack_id, p.name AS pack_name
            FROM clan_season_reward_tiers t
            LEFT JOIN packs p ON p.id = t.pack_id
            ORDER BY t.place
            """
        ).fetchall()
    return [
        ClanTierReward(
            place=int(row["place"]),
            coins=int(row["coins"] or 0),
            rubles=int(row["rubles"] or 0),
            pack_id=row["pack_id"],
            pack_name=row["pack_name"],
        )
        for row in rows
    ]


async def clan_rewards_are_configured() -> bool:
    """Сброс кланового сезона разрешён только если награды топ-5 предварительно проставлены."""
    tiers = await get_clan_reward_tiers()
    return any(t.coins > 0 or t.rubles > 0 or t.pack_id is not None for t in tiers)


async def update_clan_reward_field(place: int, field: str, value: object) -> tuple[bool, str]:
    if place < 1 or place > 5:
        return False, "Место должно быть от 1 до 5."
    if field not in ("coins", "rubles", "pack_id"):
        return False, "Это поле нельзя изменить."
    if field in ("coins", "rubles"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False, "Нужно целое число."
        if value < 0 or value > 100000000:
            return False, "Значение вне диапазона."
    if field == "pack_id":
        try:
            value = None if value in (None, "", 0, "0") else int(value)
        except (TypeError, ValueError):
            return False, "Нужно ID пака или 0, чтобы убрать пак."

    with get_connection() as connection:
        exists = connection.execute("SELECT place FROM clan_season_reward_tiers WHERE place = ?", (place,)).fetchone()
        if exists is None:
            connection.execute("INSERT INTO clan_season_reward_tiers (place) VALUES (?)", (place,))
        if field == "pack_id" and value is not None:
            if connection.execute("SELECT id FROM packs WHERE id = ?", (value,)).fetchone() is None:
                return False, "Пак не найден."
        connection.execute(
            f"UPDATE clan_season_reward_tiers SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE place = ?",
            (value, place),
        )
        connection.commit()
    return True, "Сохранено."


async def get_current_clan_top(limit: int = 10) -> list[tuple[int, str, int, int]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT name, rating_points, wins
            FROM clans
            WHERE active = 1
            ORDER BY rating_points DESC, wins DESC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(i + 1, row["name"], int(row["rating_points"] or 0), int(row["wins"] or 0)) for i, row in enumerate(rows)]


async def get_last_clan_seasons(limit: int = 10) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT number, ended_at, clans_count, rewards_summary FROM clan_seasons ORDER BY number DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _grant_pack_to_clan_members(connection, clan_id: int, pack_id: int, quantity: int = 1) -> int:
    rows = connection.execute("SELECT user_id FROM clan_members WHERE clan_id = ?", (clan_id,)).fetchall()
    for row in rows:
        grant_pack(connection, int(row["user_id"]), pack_id, quantity)
    return len(rows)


async def reset_clan_season(reset_by_telegram_id: int | None = None) -> ClanSeasonResetResult:
    """Выдаёт награды топ-5 кланам, сохраняет историю и сбрасывает клановый рейтинг/победы."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rewards = {r.place: r for r in get_clan_reward_tiers_sync(connection)}
        ranked = connection.execute(
            """
            SELECT id, name, rating_points, wins
            FROM clans
            WHERE active = 1
            ORDER BY rating_points DESC, wins DESC, id ASC
            """
        ).fetchall()

        clans_count = len(ranked)
        rewarded = 0
        top_snapshot: list[dict] = []

        for index, clan in enumerate(ranked):
            place = index + 1
            if place <= 5:
                top_snapshot.append({
                    "place": place,
                    "name": clan["name"],
                    "rating_points": int(clan["rating_points"] or 0),
                    "wins": int(clan["wins"] or 0),
                })
            if place > 5:
                continue
            reward = rewards.get(place)
            if reward is None:
                continue
            clan_id = int(clan["id"])
            if reward.coins > 0:
                pay_clan_members(connection, clan_id, "coins", reward.coins)
            if reward.rubles > 0:
                pay_clan_members(connection, clan_id, "energy", reward.rubles)
            if reward.pack_id is not None:
                _grant_pack_to_clan_members(connection, clan_id, int(reward.pack_id), 1)
            rewarded += 1

        last = connection.execute("SELECT MAX(number) AS n FROM clan_seasons").fetchone()
        season_number = (int(last["n"]) + 1) if last and last["n"] is not None else 1
        rewards_summary = ", ".join(
            f"{r.place} место: {r.coins} coins" for r in [rewards[i] for i in sorted(rewards)]
        )
        connection.execute(
            "INSERT INTO clan_seasons (number, top_json, rewards_summary, clans_count, reset_by_telegram_id) VALUES (?, ?, ?, ?, ?)",
            (season_number, json.dumps(top_snapshot, ensure_ascii=False), rewards_summary, clans_count, reset_by_telegram_id),
        )
        connection.execute("UPDATE clans SET rating_points = 0, wins = 0, updated_at = CURRENT_TIMESTAMP")
        connection.execute("UPDATE clan_war_player_stats SET wins_contributed = 0, updated_at = CURRENT_TIMESTAMP")
        connection.execute("UPDATE clan_arena_attacks SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE status = 'active'")
        connection.commit()

    top = [(x["place"], x["name"], x["rating_points"], x["wins"]) for x in top_snapshot]
    return ClanSeasonResetResult(season_number=season_number, clans_count=clans_count, rewarded_count=rewarded, top=top)


def get_clan_reward_tiers_sync(connection) -> list[ClanTierReward]:
    rows = connection.execute(
        """
        SELECT t.place, t.coins, t.rubles, t.pack_id, p.name AS pack_name
        FROM clan_season_reward_tiers t
        LEFT JOIN packs p ON p.id = t.pack_id
        ORDER BY t.place
        """
    ).fetchall()
    return [
        ClanTierReward(
            place=int(row["place"]),
            coins=int(row["coins"] or 0),
            rubles=int(row["rubles"] or 0),
            pack_id=row["pack_id"],
            pack_name=row["pack_name"],
        )
        for row in rows
    ]
