"""Обновляет users.last_active_at на каждом сообщении/callback — единственный источник
данных для таргетинга уведомлений BLACK MARKET "активные за последние N дней"
(app/services/black_market_notifications.py). До этой фичи в проекте не было ни одного
общего поля активности пользователя — только фиче-специфичные таймстампы.

Побочный эффект, не блокирует обработку: любая ошибка молча проглатывается, чтобы
сбой записи активности никогда не мог сломать реальный хендлер (тот же принцип, что и
BannedPlayerMiddleware, но без веток отказа — здесь только side-effect).
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.db import get_connection


class LastActiveMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")
        if telegram_user is not None:
            try:
                with get_connection() as connection:
                    connection.execute(
                        "UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                        (telegram_user.id,),
                    )
                    connection.commit()
            except Exception:
                pass

        return await handler(event, data)
