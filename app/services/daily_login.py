from dataclasses import dataclass
from datetime import datetime, timedelta

from app.database.db import get_connection
from app.services.rewards import grant_currency, grant_pack

LADDER_LENGTH = 7


@dataclass(frozen=True)
class DailyRewardDef:
    day: int
    coins: int
    rubles: int
    pack_id: int | None
    pack_name: str | None


@dataclass(frozen=True)
class DailyStatus:
    can_claim: bool
    streak: int
    next_day: int
    seconds_until_next: int
    ladder: list[DailyRewardDef]
    today_reward: DailyRewardDef | None


@dataclass(frozen=True)
class DailyClaimResult:
    day: int
    streak: int
    coins: int
    rubles: int
    pack_name: str | None


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def today_str(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def seconds_to_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0, int((tomorrow - now).total_seconds()))


def load_ladder(connection) -> list[DailyRewardDef]:
    rows = connection.execute(
        """
        SELECT r.day, r.coins, r.rubles, r.pack_id, p.name AS pack_name
        FROM daily_login_rewards r
        LEFT JOIN packs p ON p.id = r.pack_id
        ORDER BY r.day
        """
    ).fetchall()
    return [
        DailyRewardDef(
            day=int(row["day"]),
            coins=int(row["coins"] or 0),
            rubles=int(row["rubles"] or 0),
            pack_id=row["pack_id"],
            pack_name=row["pack_name"],
        )
        for row in rows
    ]


def reward_for_day(ladder: list[DailyRewardDef], day: int) -> DailyRewardDef | None:
    for reward in ladder:
        if reward.day == day:
            return reward
    return None


def next_day_from_streak(streak: int, last_date: str | None, today: str) -> int:
    """Какой день лестницы даст следующий клейм."""
    if last_date is None:
        return 1
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    if last_date == yesterday:
        # серия продолжается — циклически 1..7
        return (streak % LADDER_LENGTH) + 1
    if last_date == today:
        # уже забрано сегодня — показываем следующий за текущим
        return (streak % LADDER_LENGTH) + 1
    # пропуск — серия сбрасывается
    return 1


async def get_daily_status(user_id: int) -> DailyStatus:
    now = utc_now()
    today = today_str(now)

    with get_connection() as connection:
        ladder = load_ladder(connection)
        row = connection.execute(
            "SELECT last_claim_date, streak FROM daily_login_claims WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        last_date = row["last_claim_date"] if row else None
        streak = int(row["streak"]) if row else 0

        can_claim = last_date != today
        next_day = next_day_from_streak(streak, last_date, today)
        today_reward = reward_for_day(ladder, next_day)
        seconds_until = 0 if can_claim else seconds_to_midnight(now)

        return DailyStatus(
            can_claim=can_claim,
            streak=streak,
            next_day=next_day,
            seconds_until_next=seconds_until,
            ladder=ladder,
            today_reward=today_reward,
        )


async def claim_daily(user_id: int) -> tuple[DailyClaimResult | None, str | None]:
    now = utc_now()
    today = today_str(now)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT last_claim_date, streak, total_claims FROM daily_login_claims WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        last_date = row["last_claim_date"] if row else None
        streak = int(row["streak"]) if row else 0
        total = int(row["total_claims"]) if row else 0

        # Защита от повторного получения в тот же день (в т.ч. при спаме кнопки).
        if last_date == today:
            connection.rollback()
            return None, "already"

        if last_date == yesterday:
            new_streak = streak + 1
        else:
            new_streak = 1

        reward_day = ((new_streak - 1) % LADDER_LENGTH) + 1

        reward_row = connection.execute(
            "SELECT coins, rubles, pack_id FROM daily_login_rewards WHERE day = ?",
            (reward_day,),
        ).fetchone()
        if reward_row is None:
            connection.rollback()
            return None, "no_reward"

        coins = int(reward_row["coins"] or 0)
        rubles = int(reward_row["rubles"] or 0)
        pack_id = reward_row["pack_id"]

        grant_currency(connection, user_id, "coins", coins)
        grant_currency(connection, user_id, "energy", rubles)  # energy = Рубли (display)
        pack_name = None
        if pack_id is not None:
            if grant_pack(connection, user_id, int(pack_id), 1):
                name_row = connection.execute("SELECT name FROM packs WHERE id = ?", (int(pack_id),)).fetchone()
                pack_name = name_row["name"] if name_row else None

        connection.execute(
            """
            INSERT INTO daily_login_claims (user_id, last_claim_date, streak, total_claims, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_claim_date = excluded.last_claim_date,
                streak = excluded.streak,
                total_claims = excluded.total_claims,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, today, new_streak, total + 1),
        )
        connection.commit()

    return DailyClaimResult(day=reward_day, streak=new_streak, coins=coins, rubles=rubles, pack_name=pack_name), None


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

async def get_ladder() -> list[DailyRewardDef]:
    with get_connection() as connection:
        return load_ladder(connection)


async def update_reward_field(day: int, field: str, value: object) -> tuple[bool, str]:
    if field not in ("coins", "rubles", "pack_id"):
        return False, "Это поле нельзя изменить."

    if field in ("coins", "rubles"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False, "Нужно целое число."
        if value < 0 or value > 10000000:
            return False, "Сумма должна быть от 0 до 10 000 000."

    with get_connection() as connection:
        exists = connection.execute("SELECT day FROM daily_login_rewards WHERE day = ?", (day,)).fetchone()
        if exists is None:
            return False, "День не найден."
        if field == "pack_id" and value is not None:
            pack = connection.execute("SELECT id FROM packs WHERE id = ?", (value,)).fetchone()
            if pack is None:
                return False, "Пак не найден."
        connection.execute(
            f"UPDATE daily_login_rewards SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE day = ?",
            (value, day),
        )
        connection.commit()
    return True, "Сохранено."


async def list_packs_for_picker(limit: int = 30) -> list[tuple[int, str]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name FROM packs WHERE active = 1 ORDER BY name LIMIT ?",
            (limit,),
        ).fetchall()
    return [(int(row["id"]), row["name"]) for row in rows]
