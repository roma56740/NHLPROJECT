import asyncio
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.database.db import get_connection


@dataclass(frozen=True)
class BroadcastTarget:
    user_id: int
    telegram_id: int
    nickname: str


@dataclass(frozen=True)
class BroadcastResult:
    total: int
    success: int
    failed: int


async def get_broadcast_targets() -> list[BroadcastTarget]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, telegram_id, nickname
            FROM users
            WHERE is_banned = 0
            ORDER BY id ASC
            """
        ).fetchall()

    return [
        BroadcastTarget(
            user_id=int(row["id"]),
            telegram_id=int(row["telegram_id"]),
            nickname=row["nickname"],
        )
        for row in rows
    ]


async def send_broadcast(bot: Bot, text: str, photo_file_id: str | None = None) -> BroadcastResult:
    targets = await get_broadcast_targets()
    success = 0
    failed = 0

    async def send_to_target(target: BroadcastTarget) -> None:
        if photo_file_id:
            if len(text) <= 1024:
                await bot.send_photo(chat_id=target.telegram_id, photo=photo_file_id, caption=text)
            else:
                await bot.send_photo(chat_id=target.telegram_id, photo=photo_file_id)
                await bot.send_message(chat_id=target.telegram_id, text=text)
        else:
            await bot.send_message(chat_id=target.telegram_id, text=text)

    for target in targets:
        try:
            await send_to_target(target)
            success += 1
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 1)
            try:
                await send_to_target(target)
                success += 1
            except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
                failed += 1
        except (TelegramBadRequest, TelegramForbiddenError):
            failed += 1

        # Лимит Telegram — около 30 сообщений в секунду на бота.
        await asyncio.sleep(0.05)

    return BroadcastResult(total=len(targets), success=success, failed=failed)
