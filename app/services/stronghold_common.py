"""Общие помощники события THE STRONGHOLD: ошибки, статус жизненного цикла, время.

См. docs/THE_STRONGHOLD_SPEC.md — единый источник правды по механикам события.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.database.db import get_connection

_observability_logger = logging.getLogger("stronghold.observability")

STRONGHOLD_SLUG = "the-stronghold"
FT_CURRENCY_CODE = "fortress_token"
COINS_CURRENCY_CODE = "coins"
GRACE_PERIOD_DAYS = 7


class StrongholdError(Exception):
    """Единая бизнес-ошибка события. `code` — см. раздел 9 THE_STRONGHOLD_SPEC.md."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now_text() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def week_key(dt: datetime | None = None) -> str:
    """Серверная ISO-неделя (UTC), не зависящая от локального времени клиента."""
    moment = dt or utc_now()
    iso = moment.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class StrongholdEventState:
    id: int
    slug: str
    title: str
    description: str
    image_path: str | None
    status: str
    stored_status: str
    starts_at: str | None
    ends_at: str | None
    grace_ends_at: str | None
    store_available_in_grace: bool
    ft_conversion_rate: int
    config_version: int

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    @property
    def is_grace_period(self) -> bool:
        return self.status == "GRACE_PERIOD"

    @property
    def allows_upgrade(self) -> bool:
        return self.status in ("ACTIVE", "GRACE_PERIOD")

    @property
    def allows_store(self) -> bool:
        if self.status == "ACTIVE":
            return True
        if self.status == "GRACE_PERIOD":
            return self.store_available_in_grace
        return False


def compute_effective_status(row: sqlite3.Row, now: datetime | None = None) -> str:
    """Чистая функция: считает актуальный статус по датам, не трогая БД.

    Нужна, чтобы бизнес-логика была верна даже если фоновая задача
    `stronghold_lifecycle_loop` ещё не сделала персистентный переход.
    """
    moment = now or utc_now()
    stored_status = str(row["status"])
    starts_at = parse_db_datetime(row["starts_at"])
    ends_at = parse_db_datetime(row["ends_at"])
    grace_ends_at = parse_db_datetime(row["grace_ends_at"])

    if stored_status == "DRAFT":
        return "DRAFT"

    if stored_status == "SCHEDULED":
        if starts_at and moment >= starts_at:
            return "ACTIVE"
        return "SCHEDULED"

    if stored_status == "ACTIVE":
        if ends_at and moment >= ends_at:
            if grace_ends_at and moment < grace_ends_at:
                return "GRACE_PERIOD"
            return "ARCHIVED"
        return "ACTIVE"

    if stored_status == "GRACE_PERIOD":
        if grace_ends_at and moment >= grace_ends_at:
            return "ARCHIVED"
        return "GRACE_PERIOD"

    return "ARCHIVED"


def row_to_event_state(row: sqlite3.Row, now: datetime | None = None) -> StrongholdEventState:
    return StrongholdEventState(
        id=int(row["id"]),
        slug=row["slug"],
        title=row["title"],
        description=row["description"] or "",
        image_path=row["image_path"],
        status=compute_effective_status(row, now),
        stored_status=str(row["status"]),
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        grace_ends_at=row["grace_ends_at"],
        store_available_in_grace=bool(row["store_available_in_grace"]),
        ft_conversion_rate=int(row["ft_conversion_rate"] or 5000),
        config_version=int(row["config_version"] or 1),
    )


def sync_event_status(connection: sqlite3.Connection, event_id: int, now: datetime | None = None) -> StrongholdEventState | None:
    """Пересчитывает и, если нужно, персистит статус события. Вызывать внутри уже открытой транзакции."""
    row = connection.execute("SELECT * FROM stronghold_events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        return None

    state = row_to_event_state(row, now)
    if state.status != state.stored_status:
        connection.execute(
            "UPDATE stronghold_events SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (state.status, event_id),
        )
    return state


async def get_event_by_slug(slug: str = STRONGHOLD_SLUG) -> StrongholdEventState | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM stronghold_events WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None
        return row_to_event_state(row)


async def get_active_event() -> StrongholdEventState | None:
    """Событие, которое имеет смысл показать игроку (не DRAFT)."""
    event = await get_event_by_slug()
    if event is None or event.status == "DRAFT":
        return None
    return event


def require_event_state(event: StrongholdEventState | None, *, allow_grace: bool = True) -> StrongholdEventState:
    if event is None or event.status in ("DRAFT", "SCHEDULED"):
        raise StrongholdError("EVENT_NOT_ACTIVE", "Событие THE STRONGHOLD сейчас недоступно.")
    if event.status == "ARCHIVED":
        raise StrongholdError("EVENT_ARCHIVED", "Событие THE STRONGHOLD завершено.")
    if event.status == "GRACE_PERIOD" and not allow_grace:
        raise StrongholdError("UPGRADE_GRACE_PERIOD_ENDED", "Действие недоступно в Grace Period.")
    return event


def log_stronghold_operation(
    action: str,
    *,
    user_id: int | None = None,
    event_id: int | None = None,
    result: str = "success",
    duration_ms: float | None = None,
    error_code: str | None = None,
    **extra_fields: object,
) -> None:
    """Единая точка структурированного логирования критичных операций THE STRONGHOLD.

    Пишет в стандартный `logging` (видно в Railway logs) — отдельной внешней системы
    метрик в проекте нет, это совместимый с существующим стеком слой observability
    (см. THE_STRONGHOLD_SPEC.md, раздел 0). Не логирует токены/секреты.
    """
    payload = {
        "stronghold_action": action,
        "user_id": user_id,
        "event_id": event_id,
        "result": result,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "error_code": error_code,
        **extra_fields,
    }
    level = logging.WARNING if result == "error" else logging.INFO
    _observability_logger.log(level, "stronghold_operation", extra={"stronghold": payload})


class OperationTimer:
    """Контекст-менеджер для измерения длительности операции в миллисекундах."""

    def __enter__(self) -> "OperationTimer":
        self._start = time.monotonic()
        self.duration_ms = 0.0
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.duration_ms = (time.monotonic() - self._start) * 1000


def grace_ends_at_text(ends_at_text: str) -> str:
    ends_at = parse_db_datetime(ends_at_text)
    if ends_at is None:
        raise ValueError("ends_at is required to compute grace_ends_at")
    grace = ends_at + timedelta(days=GRACE_PERIOD_DAYS)
    return grace.strftime("%Y-%m-%d %H:%M:%S")
