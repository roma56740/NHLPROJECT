import json
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.rewards import grant_currency, grant_pack

# Ранг -> ключ тира награды.
def tier_for_rank(rank: int) -> str | None:
    if rank == 1:
        return "T1"
    if rank == 2:
        return "T2"
    if rank == 3:
        return "T3"
    if 4 <= rank <= 10:
        return "T4_10"
    if 11 <= rank <= 50:
        return "T11_50"
    return None


TIER_TITLES = {
    "T1": "🥇 1 место",
    "T2": "🥈 2 место",
    "T3": "🥉 3 место",
    "T4_10": "4–10 места",
    "T11_50": "11–50 места",
}


@dataclass(frozen=True)
class TierReward:
    tier_key: str
    coins: int
    rubles: int
    pack_id: int | None
    pack_name: str | None


@dataclass(frozen=True)
class SeasonResetResult:
    season_number: int
    players_count: int
    rewarded_count: int
    top: list[tuple[int, str, int]]  # (rank, nickname, points)


def load_tiers(connection) -> dict[str, TierReward]:
    rows = connection.execute(
        """
        SELECT t.tier_key, t.coins, t.rubles, t.pack_id, p.name AS pack_name
        FROM season_reward_tiers t
        LEFT JOIN packs p ON p.id = t.pack_id
        """
    ).fetchall()
    return {
        row["tier_key"]: TierReward(
            tier_key=row["tier_key"],
            coins=int(row["coins"] or 0),
            rubles=int(row["rubles"] or 0),
            pack_id=row["pack_id"],
            pack_name=row["pack_name"],
        )
        for row in rows
    }


async def get_tiers() -> list[TierReward]:
    with get_connection() as connection:
        tiers = load_tiers(connection)
    order = ["T1", "T2", "T3", "T4_10", "T11_50"]
    return [tiers[k] for k in order if k in tiers]


async def update_tier_field(tier_key: str, field: str, value: object) -> tuple[bool, str]:
    if field not in ("coins", "rubles", "pack_id"):
        return False, "Это поле нельзя изменить."
    if field in ("coins", "rubles"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False, "Нужно целое число."
        if value < 0 or value > 100000000:
            return False, "Значение вне диапазона."
    with get_connection() as connection:
        exists = connection.execute("SELECT tier_key FROM season_reward_tiers WHERE tier_key = ?", (tier_key,)).fetchone()
        if exists is None:
            return False, "Тир не найден."
        if field == "pack_id" and value is not None:
            if connection.execute("SELECT id FROM packs WHERE id = ?", (value,)).fetchone() is None:
                return False, "Пак не найден."
        connection.execute(
            f"UPDATE season_reward_tiers SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE tier_key = ?",
            (value, tier_key),
        )
        connection.commit()
    return True, "Сохранено."


async def get_current_top(limit: int = 10) -> list[tuple[int, str, int]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT nickname, rating_points
            FROM users
            WHERE is_banned = 0
            ORDER BY rating_points DESC, wins DESC, matches_played ASC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(i + 1, row["nickname"], int(row["rating_points"])) for i, row in enumerate(rows)]


async def get_last_seasons(limit: int = 5) -> list:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT number, ended_at, players_count, rewards_summary FROM seasons ORDER BY number DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


async def reset_season() -> SeasonResetResult:
    """Выдаёт награды по местам, сбрасывает MMR/лигу всем, сохраняет историю сезона."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        tiers = load_tiers(connection)

        ranked = connection.execute(
            """
            SELECT id, nickname, rating_points
            FROM users
            WHERE is_banned = 0
            ORDER BY rating_points DESC, wins DESC, matches_played ASC, id ASC
            """
        ).fetchall()

        players_count = len(ranked)
        rewarded = 0
        top_snapshot: list[dict] = []

        for index, player in enumerate(ranked):
            rank = index + 1
            if rank <= 50:
                top_snapshot.append({"rank": rank, "nickname": player["nickname"], "points": int(player["rating_points"])})

            tier_key = tier_for_rank(rank)
            if tier_key is None:
                continue
            tier = tiers.get(tier_key)
            if tier is None:
                continue

            grant_currency(connection, int(player["id"]), "coins", tier.coins)
            grant_currency(connection, int(player["id"]), "energy", tier.rubles)
            if tier.pack_id is not None:
                grant_pack(connection, int(player["id"]), int(tier.pack_id), 1)
            rewarded += 1

        # номер нового сезона
        last = connection.execute("SELECT MAX(number) AS n FROM seasons").fetchone()
        season_number = (int(last["n"]) + 1) if last and last["n"] is not None else 1

        rewards_summary = ", ".join(
            f"{TIER_TITLES.get(t.tier_key, t.tier_key)}: {t.coins} coins"
            for t in [tiers[k] for k in ["T1", "T2", "T3", "T4_10", "T11_50"] if k in tiers]
        )

        connection.execute(
            "INSERT INTO seasons (number, top_json, rewards_summary, players_count) VALUES (?, ?, ?, ?)",
            (season_number, json.dumps(top_snapshot, ensure_ascii=False), rewards_summary, players_count),
        )

        # сброс MMR и лиги всем
        connection.execute("UPDATE users SET rating_points = 0, league = 'NCAA', updated_at = CURRENT_TIMESTAMP")

        connection.commit()

    top = [(row["rank"], row["nickname"], row["points"]) for row in top_snapshot[:10]]
    return SeasonResetResult(season_number=season_number, players_count=players_count, rewarded_count=rewarded, top=top)


async def list_players_telegram_for_broadcast() -> list[int]:
    with get_connection() as connection:
        rows = connection.execute("SELECT telegram_id FROM users WHERE is_banned = 0").fetchall()
    return [int(row["telegram_id"]) for row in rows]


async def list_packs_for_picker(limit: int = 30) -> list[tuple[int, str]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT id, name FROM packs WHERE active = 1 ORDER BY name LIMIT ?", (limit,)).fetchall()
    return [(int(row["id"]), row["name"]) for row in rows]
