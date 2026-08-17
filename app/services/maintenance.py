"""Глобальный технический перерыв (ТЗ "ГЛОБАЛЬНЫЙ ТЕХНИЧЕСКИЙ ПЕРЕРЫВ").

Хранение — существующая система глобальных настроек `game_settings`
(app/services/settings.py), тот же `maintenance_mode` флаг, что использовался
раньше в app/middlewares/banned.py, плюс новые ключи для текста/фото/метаданных
(см. DEFAULT_GAME_SETTINGS в app/database/schema.py) — никакой отдельной таблицы
не заводится, это ровно тот "существующий механизм глобальных настроек", который
просит переиспользовать ТЗ.

Кэш — короткий TTL на весь объект статуса, с ЯВНОЙ инвалидацией при любом
изменении (enable/disable/set_text/set_photo/remove_photo), поэтому изменения
всегда применяются немедленно независимо от TTL (ТЗ: "включение должно
немедленно инвалидировать кэш").
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.services.audit_log import record_committed
from app.services.settings import set_setting_value

DEFAULT_MAINTENANCE_TEXT = "Бот временно недоступен из-за технических работ. Пожалуйста, попробуйте позже."
_CACHE_TTL_SECONDS = 2.0


@dataclass(frozen=True)
class MaintenanceStatus:
    enabled: bool
    message_text: str
    photo_file_id: str | None
    photo_file_unique_id: str | None
    enabled_at: str | None
    enabled_by: str | None
    disabled_at: str | None
    disabled_by: str | None
    text_updated_at: str | None
    text_updated_by: str | None
    photo_updated_at: str | None
    photo_updated_by: str | None

    @property
    def effective_text(self) -> str:
        return self.message_text or DEFAULT_MAINTENANCE_TEXT


_cache: tuple[float, MaintenanceStatus] | None = None


def invalidate_cache() -> None:
    global _cache
    _cache = None


async def _load_status() -> MaintenanceStatus:
    from app.database.db import get_connection

    with get_connection() as connection:
        rows = {
            row["key"]: (row["value"], row["updated_at"])
            for row in connection.execute(
                """
                SELECT key, value, updated_at FROM game_settings WHERE key IN (
                    'maintenance_mode', 'maintenance_message_text', 'maintenance_photo_file_id',
                    'maintenance_photo_file_unique_id', 'maintenance_enabled_at', 'maintenance_enabled_by',
                    'maintenance_disabled_at', 'maintenance_disabled_by',
                    'maintenance_text_updated_by', 'maintenance_photo_updated_by'
                )
                """
            ).fetchall()
        }

    def value(key: str) -> str | None:
        raw = rows.get(key, (None, None))[0]
        return raw or None

    def updated_at(key: str) -> str | None:
        return rows.get(key, (None, None))[1]

    enabled_raw = value("maintenance_mode") or "0"
    return MaintenanceStatus(
        enabled=enabled_raw.strip().lower() in {"1", "true", "yes", "on", "да", "вкл"},
        message_text=value("maintenance_message_text") or "",
        photo_file_id=value("maintenance_photo_file_id"),
        photo_file_unique_id=value("maintenance_photo_file_unique_id"),
        enabled_at=value("maintenance_enabled_at"),
        enabled_by=value("maintenance_enabled_by"),
        disabled_at=value("maintenance_disabled_at"),
        disabled_by=value("maintenance_disabled_by"),
        text_updated_at=updated_at("maintenance_message_text"),
        text_updated_by=value("maintenance_text_updated_by"),
        photo_updated_at=updated_at("maintenance_photo_file_id"),
        photo_updated_by=value("maintenance_photo_updated_by"),
    )


async def get_status(*, use_cache: bool = True) -> MaintenanceStatus:
    global _cache
    now = time.monotonic()
    if use_cache and _cache is not None and (now - _cache[0]) < _CACHE_TTL_SECONDS:
        return _cache[1]
    status = await _load_status()
    _cache = (now, status)
    return status


async def is_enabled() -> bool:
    status = await get_status()
    return status.enabled


async def enable(admin_id: int) -> None:
    from app.services.stronghold_common import utc_now_text

    now_text = utc_now_text()
    await set_setting_value("maintenance_mode", "1")
    await set_setting_value("maintenance_enabled_at", now_text)
    await set_setting_value("maintenance_enabled_by", str(admin_id))
    invalidate_cache()
    record_committed(admin_id, "maintenance_enable", entity_type="maintenance", details={"enabled_at": now_text})


async def disable(admin_id: int) -> None:
    from app.services.stronghold_common import utc_now_text

    now_text = utc_now_text()
    await set_setting_value("maintenance_mode", "0")
    await set_setting_value("maintenance_disabled_at", now_text)
    await set_setting_value("maintenance_disabled_by", str(admin_id))
    invalidate_cache()
    record_committed(admin_id, "maintenance_disable", entity_type="maintenance", details={"disabled_at": now_text})


async def set_message_text(text: str, admin_id: int) -> None:
    await set_setting_value("maintenance_message_text", text.strip())
    await set_setting_value("maintenance_text_updated_by", str(admin_id))
    invalidate_cache()
    record_committed(admin_id, "maintenance_text_update", entity_type="maintenance", details={"text": text.strip()[:200]})


async def set_photo(file_id: str, file_unique_id: str, admin_id: int) -> None:
    await set_setting_value("maintenance_photo_file_id", file_id)
    await set_setting_value("maintenance_photo_file_unique_id", file_unique_id)
    await set_setting_value("maintenance_photo_updated_by", str(admin_id))
    invalidate_cache()
    record_committed(admin_id, "maintenance_photo_update", entity_type="maintenance", details={"file_unique_id": file_unique_id})


async def remove_photo(admin_id: int) -> None:
    await set_setting_value("maintenance_photo_file_id", "")
    await set_setting_value("maintenance_photo_file_unique_id", "")
    await set_setting_value("maintenance_photo_updated_by", str(admin_id))
    invalidate_cache()
    record_committed(admin_id, "maintenance_photo_remove", entity_type="maintenance")
