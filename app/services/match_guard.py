"""Защита матчей: капча перед стартом (#3) и блокировка одновременных матчей (#2)."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.database.db import get_connection

# Матч считается «активным» не дольше этого времени (страховка от зависшей анимации).
ACTIVE_MATCH_TTL_SECONDS = 180

CAPTCHA_TTL_SECONDS = 30

_EMOJI_POOL = ["🏒", "🥅", "🏆", "⚡", "🔥", "⭐", "🎯", "🧤"]


@dataclass(frozen=True)
class Captcha:
    prompt: str
    correct: str
    options: list[str]


def generate_captcha() -> Captcha:
    """Простая проверка: выбрать нужную цифру среди 4 вариантов."""
    numbers = random.sample(range(1, 10), 4)
    correct = random.choice(numbers)
    return Captcha(
        prompt=f"Нажми число <b>{correct}</b>, чтобы начать матч",
        correct=str(correct),
        options=[str(n) for n in numbers],
    )


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


async def try_acquire_match_lock(user_id: int) -> bool:
    """Пытается занять «слот активного матча». False — если матч уже идёт."""
    now = utc_now()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT started_at FROM active_matches WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is not None:
            started = _parse(row["started_at"])
            if started is not None and (now - started) < timedelta(seconds=ACTIVE_MATCH_TTL_SECONDS):
                connection.rollback()
                return False
            # старый/зависший лок — перезаписываем
            connection.execute(
                "UPDATE active_matches SET started_at = ? WHERE user_id = ?",
                (now.strftime("%Y-%m-%d %H:%M:%S"), user_id),
            )
            connection.commit()
            return True

        connection.execute(
            "INSERT INTO active_matches (user_id, started_at) VALUES (?, ?)",
            (user_id, now.strftime("%Y-%m-%d %H:%M:%S")),
        )
        connection.commit()
        return True


async def release_match_lock(user_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM active_matches WHERE user_id = ?", (user_id,))
        connection.commit()


async def has_active_match(user_id: int) -> bool:
    now = utc_now()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT started_at FROM active_matches WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return False
    started = _parse(row["started_at"])
    return started is not None and (now - started) < timedelta(seconds=ACTIVE_MATCH_TTL_SECONDS)
