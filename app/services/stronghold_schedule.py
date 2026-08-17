"""Глобальное расписание открытия башен (крепостей) THE STRONGHOLD (ТЗ "ГЛОБАЛЬНОЕ
ОТКРЫТИЕ БАШЕН THE STRONGHOLD").

Терминология проекта — "Fortress" (`stronghold_fortresses.order_index` 1..15), это
и есть "башни" из ТЗ. Расписание ЕДИНОЕ для всех пользователей и НЕ зависит от
личного прогресса/даты регистрации/OVR — формула:

    tower_unlock_at(N) = schedule_start_at + (N - 1) * unlock_interval

где `schedule_start_at` = `stronghold_events.fortress_unlock_started_at`, а если
оно не задано явно администратором — используется уже существующее
`stronghold_events.starts_at` (старт события), без отдельной миграции backfill:
COALESCE на каждый расчёт сам восстанавливает "сколько башен уже должно быть
открыто", если сезон уже идёт на момент установки обновления (ТЗ, раздел
"Если сезон уже идёт на момент установки обновления").

`fortress_unlock_timezone` используется ТОЛЬКО для отображения даты/времени
администратору/игроку (конвертация из хранимого UTC) — все расчёты и хранение
остаются в UTC, как и весь остальной проект (`stronghold_common.utc_now()`).

Ручное открытие (админ) хранится как один nullable int
`stronghold_events.manual_unlock_override_count` — монотонный "не меньше N башен
открыто вручную", комбинируется с расчётом по времени через max(), поэтому:
— уже открытая башня никогда не закрывается (и время, и ручное открытие только
  увеличивают итоговое число открытых башен);
— ручное открытие одной башни не занижает и не закрывает другие.
Второй таблицы под это не заводится — история ручных открытий читается из уже
существующего `stronghold_audit_log` (action='manual_fortress_unlock').
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database.db import get_connection
from app.services.stronghold_common import parse_db_datetime, utc_now

DEFAULT_UNLOCK_INTERVAL_SECONDS = 86400
DEFAULT_TIMEZONE = "UTC"


@dataclass(frozen=True)
class ScheduleConfig:
    event_id: int
    schedule_start_at: datetime | None
    interval_seconds: int
    timezone_name: str
    manual_unlock_override_count: int


def _row_to_config(row: sqlite3.Row) -> ScheduleConfig:
    start_raw = row["fortress_unlock_started_at"] or row["starts_at"]
    return ScheduleConfig(
        event_id=int(row["id"]),
        schedule_start_at=parse_db_datetime(start_raw),
        interval_seconds=int(row["fortress_unlock_interval_seconds"] or DEFAULT_UNLOCK_INTERVAL_SECONDS),
        timezone_name=row["fortress_unlock_timezone"] or DEFAULT_TIMEZONE,
        manual_unlock_override_count=int(row["manual_unlock_override_count"] or 0),
    )


def get_schedule_config(connection: sqlite3.Connection, event_id: int) -> ScheduleConfig | None:
    row = connection.execute("SELECT * FROM stronghold_events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        return None
    return _row_to_config(row)


def get_total_fortress_count(connection: sqlite3.Connection, event_id: int) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM stronghold_fortresses WHERE event_id = ? AND active = 1", (event_id,)
    ).fetchone()
    return int(row["n"])


def compute_time_unlocked_count(config: ScheduleConfig, total_fortresses: int, now: datetime | None = None) -> int:
    """Сколько башен должно быть открыто по формуле unlock_at(N) = start + (N-1)*interval,
    БЕЗ учёта ручных открытий — чистая функция даты/времени."""
    if config.schedule_start_at is None or total_fortresses <= 0:
        return 0
    moment = now or utc_now()
    if moment < config.schedule_start_at:
        return 0
    interval = max(1, config.interval_seconds)
    elapsed_seconds = (moment - config.schedule_start_at).total_seconds()
    count = int(elapsed_seconds // interval) + 1
    return max(0, min(count, total_fortresses))


def compute_unlocked_count(config: ScheduleConfig, total_fortresses: int, now: datetime | None = None) -> int:
    """Итоговое число открытых башен = max(по расписанию, вручную открыто админом)."""
    time_based = compute_time_unlocked_count(config, total_fortresses, now)
    return max(time_based, min(config.manual_unlock_override_count, total_fortresses))


def get_fortress_unlock_at(config: ScheduleConfig, order_index: int) -> datetime | None:
    if config.schedule_start_at is None:
        return None
    interval = max(1, config.interval_seconds)
    return config.schedule_start_at + timedelta(seconds=interval * (order_index - 1))


def is_fortress_unlocked(config: ScheduleConfig, order_index: int, total_fortresses: int, now: datetime | None = None) -> bool:
    return order_index <= compute_unlocked_count(config, total_fortresses, now)


def to_display_timezone(moment: datetime, config: ScheduleConfig) -> datetime:
    try:
        return moment.astimezone(ZoneInfo(config.timezone_name))
    except Exception:
        return moment.astimezone(timezone.utc)


@dataclass(frozen=True)
class ScheduleStatus:
    event_id: int
    schedule_start_at: datetime | None
    interval_seconds: int
    timezone_name: str
    total_fortresses: int
    unlocked_count: int
    manual_unlock_override_count: int
    last_unlocked_order_index: int
    next_unlock_order_index: int | None
    next_unlock_at: datetime | None
    all_unlocked: bool


async def get_schedule_status(event_id: int) -> ScheduleStatus | None:
    with get_connection() as connection:
        config = get_schedule_config(connection, event_id)
        if config is None:
            return None
        total = get_total_fortress_count(connection, event_id)

    unlocked_count = compute_unlocked_count(config, total)
    next_index = unlocked_count + 1 if unlocked_count < total else None
    next_unlock_at = get_fortress_unlock_at(config, next_index) if next_index is not None else None

    return ScheduleStatus(
        event_id=event_id,
        schedule_start_at=config.schedule_start_at,
        interval_seconds=config.interval_seconds,
        timezone_name=config.timezone_name,
        total_fortresses=total,
        unlocked_count=unlocked_count,
        manual_unlock_override_count=config.manual_unlock_override_count,
        last_unlocked_order_index=unlocked_count,
        next_unlock_order_index=next_index,
        next_unlock_at=next_unlock_at,
        all_unlocked=unlocked_count >= total,
    )


async def set_schedule_settings(
    event_id: int,
    *,
    admin_id: int | None,
    schedule_start_at: datetime | None = None,
    interval_seconds: int | None = None,
    timezone_name: str | None = None,
) -> None:
    fields = []
    values: list[object] = []
    if schedule_start_at is not None:
        fields.append("fortress_unlock_started_at = ?")
        values.append(schedule_start_at.strftime("%Y-%m-%d %H:%M:%S"))
    if interval_seconds is not None:
        fields.append("fortress_unlock_interval_seconds = ?")
        values.append(max(1, interval_seconds))
    if timezone_name is not None:
        fields.append("fortress_unlock_timezone = ?")
        values.append(timezone_name)
    if not fields:
        return

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before = get_schedule_config(connection, event_id)
        fields.append("updated_at = CURRENT_TIMESTAMP")
        connection.execute(
            f"UPDATE stronghold_events SET {', '.join(fields)} WHERE id = ?", (*values, event_id)
        )
        after = get_schedule_config(connection, event_id)
        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, before, after, reason)
            VALUES (?, ?, 'fortress_schedule_update', 'stronghold_events', ?, ?, ?, NULL)
            """,
            (
                event_id, admin_id, event_id,
                str(before.__dict__) if before else None,
                str(after.__dict__) if after else None,
            ),
        )
        connection.commit()


async def manual_unlock_next(event_id: int, *, admin_id: int | None, reason: str | None = None) -> int:
    """Открывает следующую по порядку башню вручную (не закрывает остальные, не
    сбрасывает расписание). Возвращает итоговое число открытых башен."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        config = get_schedule_config(connection, event_id)
        if config is None:
            connection.rollback()
            raise ValueError("Событие не найдено")
        total = get_total_fortress_count(connection, event_id)
        current_unlocked = compute_unlocked_count(config, total)
        new_count = min(total, current_unlocked + 1)
        connection.execute(
            "UPDATE stronghold_events SET manual_unlock_override_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_count, event_id),
        )
        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, before, after, reason)
            VALUES (?, ?, 'manual_fortress_unlock', 'stronghold_fortresses', ?, ?, ?, ?)
            """,
            (event_id, admin_id, new_count, str(current_unlocked), str(new_count), reason),
        )
        connection.commit()
    return new_count


async def manual_unlock_specific(event_id: int, order_index: int, *, admin_id: int | None, reason: str | None = None) -> int:
    """Открывает конкретную башню (и всё до неё) вручную — монотонно, никогда не уменьшает."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        config = get_schedule_config(connection, event_id)
        if config is None:
            connection.rollback()
            raise ValueError("Событие не найдено")
        total = get_total_fortress_count(connection, event_id)
        current_unlocked = compute_unlocked_count(config, total)
        new_count = min(total, max(current_unlocked, order_index, config.manual_unlock_override_count))
        connection.execute(
            "UPDATE stronghold_events SET manual_unlock_override_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_count, event_id),
        )
        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, before, after, reason)
            VALUES (?, ?, 'manual_fortress_unlock', 'stronghold_fortresses', ?, ?, ?, ?)
            """,
            (event_id, admin_id, order_index, str(current_unlocked), str(new_count), reason),
        )
        connection.commit()
    return new_count


async def list_manual_unlock_history(event_id: int, limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(
            connection.execute(
                """
                SELECT * FROM stronghold_audit_log
                WHERE event_id = ? AND action IN ('manual_fortress_unlock', 'fortress_schedule_update')
                ORDER BY id DESC LIMIT ?
                """,
                (event_id, limit),
            ).fetchall()
        )
