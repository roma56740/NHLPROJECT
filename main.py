import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.database.db import init_database
from app.handlers import setup_routers
from app.services.clan_wars import clan_wars_loop
from app.services.cache_cleanup import cleanup_render_cache, render_cache_cleanup_loop
from app.services.creator_tournaments import expire_tournament_matches
from app.services.creators import creator_weekly_rewards_loop
from app.services.free_card import free_card_notification_loop
from app.services.missing_assets import missing_assets_notification_loop
from config import settings


async def tournament_deadline_loop() -> None:
    while True:
        try:
            await expire_tournament_matches()
        except Exception:
            logging.getLogger(__name__).exception("tournament deadline loop failed")
        await asyncio.sleep(60)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await init_database()
    await asyncio.to_thread(cleanup_render_cache)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    dispatcher.include_router(setup_routers())
    notification_task = asyncio.create_task(free_card_notification_loop(bot))
    clan_wars_task = asyncio.create_task(clan_wars_loop(bot))
    creator_weekly_task = asyncio.create_task(creator_weekly_rewards_loop(bot))
    missing_assets_task = asyncio.create_task(missing_assets_notification_loop(bot))
    render_cache_task = asyncio.create_task(render_cache_cleanup_loop())
    tournament_deadline_task = asyncio.create_task(tournament_deadline_loop())

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dispatcher.start_polling(bot)
    finally:
        for task in (notification_task, clan_wars_task, creator_weekly_task, missing_assets_task, render_cache_task, tournament_deadline_task):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    asyncio.run(main())
