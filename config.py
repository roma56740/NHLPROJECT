import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_path: Path
    start_coins: int
    start_energy: int
    start_rank_points: int


def parse_admin_ids(raw_value: str) -> frozenset[int]:
    admin_ids: set[int] = set()

    for item in raw_value.split(","):
        value = item.strip()

        if not value:
            continue

        if not value.isdigit():
            raise ValueError("ADMIN_IDS должен содержать Telegram ID через запятую")

        admin_ids.add(int(value))

    return frozenset(admin_ids)


def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()

    if not raw_value:
        return default

    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} должен быть числом") from error


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    database_path_raw = os.getenv("DATABASE_PATH", "data/nhl_bot.sqlite3").strip()

    if not bot_token:
        raise RuntimeError("Не указан BOT_TOKEN в переменных окружения")

    return Settings(
        bot_token=bot_token,
        admin_ids=parse_admin_ids(admin_ids_raw),
        database_path=Path(database_path_raw),
        start_coins=parse_int_env("START_COINS", 0),
        start_energy=parse_int_env("START_ENERGY", 0),
        start_rank_points=parse_int_env("START_RANK_POINTS", 0),
    )


settings = get_settings()
