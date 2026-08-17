"""Восстановление pack_pending_reveals после перезапуска бота (ТЗ "НАДЁЖНОСТЬ"
раздела 4 — паки). Награда уже зафиксирована в БД до старта видео (см.
`open_user_pack()` в app/services/packs.py) — этот модуль не может выдать
награду повторно, он только ДОСТАВЛЯЕТ уже решённый результат тем, кто его не
увидел из-за рестарта во время 10-секундной анимации.

Вызывается один раз при старте (см. main.py) — до и после рестарта в памяти
ничего не остаётся (asyncio.sleep/задача открытия пака прерывается вместе с
процессом), поэтому вместо попытки "продолжить" редактирование старого
video-сообщения (оно могло не дойти до Telegram или его message_id мог устареть)
для каждой ещё 'pending' записи отправляется НОВОЕ сообщение с картой — тот же
рендер, что и в обычном потоке — и запись помечается 'completed'.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import FSInputFile

from app.database.db import get_connection
from app.services.packs import mark_reveal_completed, mark_reveal_failed, rewards_from_snapshot
from app.services.renders import render_card_profile_image

logger = logging.getLogger(__name__)


async def _resolve_chat_id(user_id: int, stored_chat_id: int | None) -> int | None:
    if stored_chat_id is not None:
        return int(stored_chat_id)
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"]) if row is not None else None


async def resume_pending_pack_reveals(bot: Bot) -> int:
    """Возвращает количество восстановленных раскрытий (для лога запуска)."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM pack_pending_reveals WHERE status = 'pending' ORDER BY id"
        ).fetchall()

    resumed = 0
    for row in rows:
        opening_id = int(row["opening_id"])
        try:
            chat_id = await _resolve_chat_id(int(row["user_id"]), row["chat_id"])
            if chat_id is None:
                await mark_reveal_failed(opening_id, "unresolvable chat_id on restart recovery")
                continue

            rewards = rewards_from_snapshot(row["reward_snapshot"])
            if not rewards:
                await bot.send_message(chat_id, "Пак открыт — награда без карт (см. историю паков).")
            else:
                first = rewards[0]
                try:
                    image_path = render_card_profile_image(first, user_id=chat_id)
                except Exception:
                    image_path = None
                caption = (
                    "🎁 <b>Открытие пака завершилось во время перезапуска бота</b>\n"
                    f"Твоя награда: {first.name} · {first.position} {first.overall}"
                )
                if image_path is not None and image_path.exists():
                    await bot.send_photo(chat_id, photo=FSInputFile(image_path), caption=caption, parse_mode="HTML")
                else:
                    await bot.send_message(chat_id, caption, parse_mode="HTML")

                for extra in rewards[1:]:
                    await bot.send_message(chat_id, f"🎁 Дополнительная награда: {extra.name} · {extra.position} {extra.overall}")

            await mark_reveal_completed(opening_id)
            resumed += 1
        except Exception as error:  # noqa: BLE001 — восстановление не должно ронять запуск бота
            logger.exception("resume_pending_pack_reveals: failed for opening_id=%s: %s", opening_id, error)
            await mark_reveal_failed(opening_id, repr(error))

    if resumed:
        logger.warning("resume_pending_pack_reveals: восстановлено раскрытий паков после рестарта: %d", resumed)
    return resumed
