from __future__ import annotations

from dataclasses import dataclass

from app.database.db import get_connection
from app.database.schema import DEFAULT_GAME_SETTINGS


@dataclass(frozen=True)
class GameSetting:
    key: str
    value: str
    title: str
    description: str
    updated_at: str


DEFAULT_VALUES = {item["key"]: item["value"] for item in DEFAULT_GAME_SETTINGS}
DEFAULT_TITLES = {item["key"]: item["title"] for item in DEFAULT_GAME_SETTINGS}
DEFAULT_DESCRIPTIONS = {item["key"]: item["description"] for item in DEFAULT_GAME_SETTINGS}


async def ensure_default_settings() -> None:
    with get_connection() as connection:
        for item in DEFAULT_GAME_SETTINGS:
            connection.execute(
                """
                INSERT INTO game_settings (key, value, title, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description
                """,
                (item["key"], item["value"], item["title"], item["description"]),
            )
        connection.commit()


async def get_all_settings() -> list[GameSetting]:
    await ensure_default_settings()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT key, value, title, description, updated_at
            FROM game_settings
            ORDER BY
                CASE key
                    WHEN 'maintenance_mode' THEN 1
                    WHEN 'season_key' THEN 2
                    WHEN 'win_coins_reward' THEN 3
                    WHEN 'matchmaking_min_wait_seconds' THEN 4
                    WHEN 'matchmaking_max_wait_seconds' THEN 5
                    WHEN 'start_coins' THEN 6
                    WHEN 'start_energy' THEN 7
                    WHEN 'start_rank_points' THEN 8
                    ELSE 99
                END,
                key
            """
        )
        rows = cursor.fetchall()

    return [
        GameSetting(
            key=row["key"],
            value=row["value"],
            title=row["title"],
            description=row["description"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


async def get_setting(key: str, default: str | None = None) -> str:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM game_settings WHERE key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return DEFAULT_VALUES.get(key, default or "")

    return str(row["value"])


async def get_int_setting(key: str, default: int = 0, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = await get_setting(key, str(default))

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default

    if minimum is not None and value < minimum:
        value = minimum

    if maximum is not None and value > maximum:
        value = maximum

    return value


async def get_bool_setting(key: str, default: bool = False) -> bool:
    value = await get_setting(key, "1" if default else "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да", "вкл"}


async def set_setting_value(key: str, value: str) -> None:
    title = DEFAULT_TITLES.get(key, key)
    description = DEFAULT_DESCRIPTIONS.get(key, "")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO game_settings (key, value, title, description, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                title = excluded.title,
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value, title, description),
        )
        connection.commit()


async def toggle_maintenance_mode() -> bool:
    is_enabled = await get_bool_setting("maintenance_mode")
    new_value = "0" if is_enabled else "1"
    await set_setting_value("maintenance_mode", new_value)
    return new_value == "1"


async def is_maintenance_mode_enabled() -> bool:
    return await get_bool_setting("maintenance_mode")
