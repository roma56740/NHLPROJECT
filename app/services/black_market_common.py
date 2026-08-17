"""Общие типы и утилиты BLACK MARKET (см. app/services/stronghold_common.py — тот же
паттерн: единый класс ошибки с кодом + текстовое сообщение, UTC-хелперы).

MASTER POOL (black_market_settings/black_market_rarity_weights/black_market_pool_items)
общий для всех пользователей. STOREFRONT (black_market_user_rotations/
black_market_user_rotation_items) генерируется лениво и независимо на каждого
пользователя — см. app/services/black_market_generation.py.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

RARITIES = ["Common", "Rare", "Epic", "Legendary", "Event", "Icon"]
ITEM_TYPES = ("currency", "pack", "card", "cosmetic")


class BlackMarketError(Exception):
    """Единая бизнес-ошибка Чёрного рынка. `code` — см. build_black_market_admin_audit/тексты."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def business_date(now: datetime | None = None) -> str:
    """Текущая business_date — календарный день UTC (сброс в 00:00 UTC, как везде в проекте,
    см. app/services/quests.py:get_daily_period_key). Вынесено в отдельную функцию, чтобы
    при необходимости заменить на настраиваемый часовой пояс без изменения вызывающего кода.
    """
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def get_settings(connection: sqlite3.Connection) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM black_market_settings WHERE id = 1").fetchone()
    if row is None:
        raise BlackMarketError("SETTINGS_NOT_FOUND", "Настройки Чёрного рынка не найдены.")
    return row


def next_business_date_reset_at(now: datetime | None = None) -> datetime:
    """Следующая граница business_date — ближайшая полночь UTC строго после `now`."""
    current = now or datetime.now(timezone.utc)
    tomorrow = current.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)


def format_next_reset_hint(now: datetime | None = None) -> str:
    """Человеко-читаемая подсказка "когда обновится витрина" для экрана магазина
    (раздел 1 ТЗ аудита: "увидеть точное время следующего обновления")."""
    current = now or datetime.now(timezone.utc)
    reset_at = next_business_date_reset_at(current)
    remaining = reset_at - current
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60
    return f"Обновление в 00:00 UTC (через {hours} ч {minutes} мин)"
