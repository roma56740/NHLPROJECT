import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from app.database.db import init_database
from app.handlers import setup_routers
from app.services.cache_cleanup import cleanup_render_cache, render_cache_cleanup_loop
from app.services import backups, error_log
from app.services.creator_tournaments import expire_tournament_matches
from app.services.clan_wars import clan_wars_loop
from app.services.creators import creator_weekly_rewards_loop
from app.services.black_market_notifications import black_market_notification_loop
from app.services.free_card import free_card_notification_loop
from app.services.health_monitor import health_check_loop
from app.services import match_guard, war2_core
from app.services.missing_assets import missing_assets_notification_loop
from app.services.pack_reveal_recovery import resume_pending_pack_reveals
from app.services.stronghold_lifecycle import stronghold_lifecycle_loop
from config import settings

DAILY_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60


async def handle_dispatcher_error(event: ErrorEvent) -> bool:
    """Раздел 19 ТЗ: необработанные исключения хендлеров раньше уходили только в
    stdout-логи Railway, которые никто не смотрит без ручного открытия деплоя. Пишем в
    application_errors — последняя ошибка и их частота видны прямо в /diagnostics."""
    update_summary = event.update.event_type if event.update else "unknown"
    error_log.record_error("dispatcher", event.exception, context=f"update={update_summary}")
    logging.getLogger(__name__).error("unhandled error in update handler (update=%s)", update_summary, exc_info=event.exception)
    return True


MATCH_LOCK_RECOVERY_INTERVAL_SECONDS = 120


async def match_lock_recovery_loop() -> None:
    """ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: периодическая проверка зависших lock'ов —
    boot recovery (вызов ниже, до старта polling) покрывает состояние сразу после
    рестарта, этот цикл продолжает подчищать TTL-истёкшие lock'и, пока процесс
    уже работает (например, если реальный матч упал с исключением где-то в
    середине пути и cancel/release почему-то не сработал)."""
    while True:
        try:
            # War 2.0 имеет многошаговый draft и собственный inactivity timeout.
            # Сначала закрываем реально брошенные drafting-матчи, затем общий
            # recovery обрабатывает остальные lock'и. Иначе старый War 2.0 со
            # status='drafting' мог продлевать lock бесконечно.
            await war2_core.cleanup_abandoned_war2_matches()
            report = await match_guard.recover_stale_matches()
            if report.actions:
                logging.getLogger(__name__).warning(
                    "match_lock_recovery_loop: processed %d stale lock(s)", len(report.actions)
                )
        except Exception:
            logging.getLogger(__name__).exception("match_lock_recovery_loop failed")
        await asyncio.sleep(MATCH_LOCK_RECOVERY_INTERVAL_SECONDS)


async def tournament_deadline_loop() -> None:
    while True:
        try:
            await expire_tournament_matches()
        except Exception:
            logging.getLogger(__name__).exception("tournament deadline loop failed")
        await asyncio.sleep(60)


async def daily_backup_loop() -> None:
    """Раздел 13 ТЗ: ежедневный backup по расписанию (не на каждый restart)."""
    while True:
        await asyncio.sleep(DAILY_BACKUP_INTERVAL_SECONDS)
        try:
            result = await asyncio.to_thread(backups.create_backup, "daily")
            if not result.success:
                logging.getLogger(__name__).warning("daily backup failed: %s", result.message)
        except Exception:
            logging.getLogger(__name__).exception("daily backup loop failed")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await init_database()
    await asyncio.to_thread(cleanup_render_cache)

    # ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: boot recovery ДО старта polling — если процесс
    # упал во время матча, пользователь не должен оставаться заблокированным
    # навсегда после рестарта. Проверяет реальное состояние матча перед тем, как
    # снять lock (см. app/services/match_guard.py::recover_stale_matches).
    try:
        await war2_core.cleanup_abandoned_war2_matches()
        boot_recovery_report = await match_guard.recover_stale_matches()
        if boot_recovery_report.actions:
            logging.getLogger(__name__).warning(
                "boot recovery: processed %d stale match lock(s) (scanned=%d)",
                len(boot_recovery_report.actions), boot_recovery_report.scanned,
            )
    except Exception:
        logging.getLogger(__name__).exception("match_guard.recover_stale_matches failed at boot")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.error.register(handle_dispatcher_error)

    dispatcher.include_router(setup_routers())
    notification_task = asyncio.create_task(free_card_notification_loop(bot))
    clan_wars_task = asyncio.create_task(clan_wars_loop(bot))
    creator_weekly_task = asyncio.create_task(creator_weekly_rewards_loop(bot))
    missing_assets_task = asyncio.create_task(missing_assets_notification_loop(bot))
    render_cache_task = asyncio.create_task(render_cache_cleanup_loop())
    tournament_deadline_task = asyncio.create_task(tournament_deadline_loop())
    stronghold_lifecycle_task = asyncio.create_task(stronghold_lifecycle_loop())
    health_check_task = asyncio.create_task(health_check_loop(bot))
    daily_backup_task = asyncio.create_task(daily_backup_loop())
    black_market_task = asyncio.create_task(black_market_notification_loop(bot))
    match_lock_recovery_task = asyncio.create_task(match_lock_recovery_loop())

    try:
        await resume_pending_pack_reveals(bot)
    except Exception:
        logging.getLogger(__name__).exception("resume_pending_pack_reveals failed at startup")

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dispatcher.start_polling(bot)
    finally:
        for task in (
            notification_task,
            clan_wars_task,
            creator_weekly_task,
            missing_assets_task,
            render_cache_task,
            tournament_deadline_task,
            stronghold_lifecycle_task,
            health_check_task,
            daily_backup_task,
            black_market_task,
            match_lock_recovery_task,
        ):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    asyncio.run(main())
