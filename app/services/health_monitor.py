"""Периодический health-check (раздел 15 ТЗ по надёжности).

Каждые CHECK_INTERVAL_SECONDS проверяет БД/Volume/зависшие матчи, уведомляет
администраторов при проблеме, с cooldown на повтор одинаковой проблемы (раздел 15:
"добавить cooldown, чтобы одинаковая ошибка не спамила каждую минуту").

Автоматическое высвобождение места (раздел 13 ТЗ, пороги 20%/15%) выполняется здесь же
реактивно на каждой проверке — отдельного гейта на старте миграций нет (см.
docs/TOURNAMENT_RELIABILITY_SPEC.md, раздел про Этап 2, "Известные ограничения": полная
блокировка миграций при <10% потребовала бы более глубокой переделки последовательности
запуска и оставлена как явное ограничение этого этапа).
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot

from app.services import backups, diagnostics
from app.services.cache_cleanup import cleanup_render_cache
from config import settings

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 5 * 60
ALERT_COOLDOWN_SECONDS = 30 * 60

_last_alert_at: dict[str, float] = {}


def _should_alert(key: str) -> bool:
    now = time.monotonic()
    last = _last_alert_at.get(key)
    if last is not None and (now - last) < ALERT_COOLDOWN_SECONDS:
        return False
    _last_alert_at[key] = now
    return True


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("health_monitor: failed to notify admin_id=%s", admin_id)


async def run_health_check(bot: Bot) -> None:
    db = diagnostics.get_db_health()
    if not db.ok and _should_alert("db_quick_check"):
        await _notify_admins(
            bot,
            "🚨 NHL BOT ALERT\n\nPRAGMA quick_check базы вернул ошибку.\nТребуется немедленная проверка (см. /diagnostics).",
        )

    volume = diagnostics.get_volume_health()
    if volume.free_percent < backups.FREE_SPACE_STOP_PCT:
        if _should_alert("volume_critical"):
            await _notify_admins(
                bot,
                f"🚨 NHL BOT ALERT\n\nVolume заполнен на {volume.used_percent}%.\n"
                f"Свободно: {diagnostics.format_bytes(volume.free_bytes)}.\n"
                "Новые миграции/backup рискованны — требуется ручное вмешательство.",
            )
    elif volume.free_percent < backups.FREE_SPACE_DELETE_BACKUPS_PCT:
        removed = backups.delete_backups_over_limit("manual") + backups.delete_backups_over_limit("daily")
        if _should_alert("volume_low_backups_trimmed"):
            await _notify_admins(
                bot,
                f"⚠️ NHL BOT ALERT\n\nVolume заполнен на {volume.used_percent}%.\n"
                f"Свободно: {diagnostics.format_bytes(volume.free_bytes)}.\n"
                f"Старые backup удалены сверх лимита ({removed} шт.).",
            )
    elif volume.free_percent < backups.FREE_SPACE_CLEAN_CACHE_PCT:
        await asyncio.to_thread(cleanup_render_cache)
        if _should_alert("volume_low_cache_cleaned"):
            await _notify_admins(
                bot,
                f"⚠️ NHL BOT ALERT\n\nVolume заполнен на {volume.used_percent}%.\n"
                f"Свободно: {diagnostics.format_bytes(volume.free_bytes)}.\nRender cache очищен.",
            )
    elif volume.free_percent < backups.FREE_SPACE_WARN_PCT and _should_alert("volume_warning"):
        await _notify_admins(
            bot,
            f"⚠️ NHL BOT ALERT\n\nVolume заполнен на {volume.used_percent}%.\n"
            f"Свободно: {diagnostics.format_bytes(volume.free_bytes)}.",
        )

    tournaments = await diagnostics.get_tournament_health()
    if tournaments.stuck_matches > 0 and _should_alert("stuck_matches"):
        await _notify_admins(
            bot,
            f"🚨 NHL BOT ALERT\n\nЗависших/ошибочных матчей: {tournaments.stuck_matches}.\n"
            "Креаторам доступно восстановление в разделе «⚠️ Требуют внимания» их турнира.",
        )


async def health_check_loop(bot: Bot) -> None:
    while True:
        try:
            await run_health_check(bot)
        except Exception:
            logger.exception("health_monitor: check failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
