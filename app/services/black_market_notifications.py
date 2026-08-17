"""Уведомления об обновлении персональной витрины BLACK MARKET.

Таргетинг читается из black_market_settings.notification_target — не требует
предварительной генерации товаров для получателя: витрина создастся лениво при
следующем открытии магазина (см. app/services/black_market_generation.py).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.database.db import get_connection
from app.services.black_market_common import business_date

logger = logging.getLogger(__name__)

NOTIFICATION_TEXT = "🕶 Твой ассортимент Чёрного рынка обновлён."

BUSINESS_DATE_POLL_SECONDS = 1800


async def resolve_target_telegram_ids(target_mode: str, active_days: int) -> list[int]:
    with get_connection() as connection:
        if target_mode == "NONE":
            return []
        if target_mode == "ALL":
            rows = connection.execute("SELECT telegram_id FROM users WHERE is_banned = 0").fetchall()
        elif target_mode in ("ACTIVE_N_DAYS", "IN_BOT_ONLY"):
            rows = connection.execute(
                """
                SELECT telegram_id FROM users
                WHERE is_banned = 0
                  AND last_active_at IS NOT NULL
                  AND last_active_at >= datetime('now', ?)
                """,
                (f"-{max(0, int(active_days))} days",),
            ).fetchall()
        else:
            return []
    return [int(row["telegram_id"]) for row in rows]


async def notify_rotation_refreshed(bot: Bot, telegram_ids: list[int]) -> int:
    """Best-effort рассылка — ошибка по одному получателю не должна прервать остальных
    (тот же принцип resilience, что и mission-progress хук в stronghold_store.py)."""
    sent = 0
    for telegram_id in telegram_ids:
        try:
            await bot.send_message(telegram_id, NOTIFICATION_TEXT)
            sent += 1
        except TelegramRetryAfter:
            continue
        except TelegramForbiddenError:
            continue
        except Exception:
            logger.exception("black market notification failed for telegram_id=%s", telegram_id)
    return sent


async def notify_settings_driven(bot: Bot) -> int:
    with get_connection() as connection:
        settings_row = connection.execute(
            "SELECT notification_target, notification_active_days FROM black_market_settings WHERE id = 1"
        ).fetchone()
    if settings_row is None:
        return 0
    target_mode = settings_row["notification_target"]
    if target_mode in ("IN_BOT_ONLY", "NONE"):
        # IN_BOT_ONLY: только внутриигровое уведомление, никакой рассылки от бота наружу.
        return 0
    active_days = int(settings_row["notification_active_days"])
    telegram_ids = await resolve_target_telegram_ids(target_mode, active_days)
    return await notify_rotation_refreshed(bot, telegram_ids)


async def notify_single_user(bot: Bot, telegram_id: int) -> None:
    """Точечное уведомление одного игрока (после admin refresh_one_user) — не завязано
    на notification_target, т.к. это прямое админ-действие для конкретного человека,
    а не массовая рассылка."""
    try:
        await bot.send_message(telegram_id, NOTIFICATION_TEXT)
    except (TelegramForbiddenError, TelegramRetryAfter):
        pass
    except Exception:
        logger.exception("black market single-user notification failed for telegram_id=%s", telegram_id)


async def check_and_notify_business_date_change(bot: Bot) -> bool:
    """Раздел 6/9 ТЗ аудита: витрины генерируются лениво, поэтому нет естественной
    "полуночной" точки, где можно было бы разослать уведомление о новом дне — этот
    фоновый тик закрывает именно этот пробел, ничего не генерируя заранее.

    Возвращает True, если business_date сменился и уведомление было отправлено
    (или пропущено по настройке NONE/IN_BOT_ONLY, но сам факт смены дня учтён)."""
    today = business_date()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT last_notified_business_date FROM black_market_settings WHERE id = 1"
        ).fetchone()
        last_notified = row["last_notified_business_date"] if row else None
        if last_notified == today:
            return False
        connection.execute(
            "UPDATE black_market_settings SET last_notified_business_date = ? WHERE id = 1",
            (today,),
        )
        connection.commit()

    await notify_settings_driven(bot)
    return True


async def black_market_notification_loop(bot: Bot, poll_seconds: int = BUSINESS_DATE_POLL_SECONDS) -> None:
    """Фоновый цикл (регистрируется в main.py рядом с free_card_notification_loop и
    остальными periodic loops) — не блокирует бота: рассылка идёт последовательно, но
    каждый await bot.send_message отдаёт управление event loop'у между получателями,
    а сам цикл проверки — раз в poll_seconds, а не при каждом апдейте."""
    while True:
        try:
            await check_and_notify_business_date_change(bot)
        except Exception:
            logger.exception("black market notification loop failed")
        await asyncio.sleep(poll_seconds)
