"""EventLifecycleService: фоновая синхронизация статуса события + автоконвертация FT.

Регистрируется в main.py как `stronghold_lifecycle_loop`, по аналогии с остальными
`*_loop` фоновыми задачами проекта (creator_weekly_rewards_loop и другими).
"""

from __future__ import annotations

import asyncio
import logging

from app.database.db import get_connection
from app.services.stronghold_common import STRONGHOLD_SLUG, sync_event_status
from app.services.stronghold_conversion import convert_archived_event_balances

logger = logging.getLogger(__name__)

LIFECYCLE_TICK_SECONDS = 300


async def run_lifecycle_tick() -> None:
    with get_connection() as connection:
        row = connection.execute("SELECT id, ft_conversion_rate FROM stronghold_events WHERE slug = ?", (STRONGHOLD_SLUG,)).fetchone()
        if row is None:
            return
        event_id = int(row["id"])
        ft_conversion_rate = int(row["ft_conversion_rate"] or 5000)
        connection.execute("BEGIN IMMEDIATE")
        state = sync_event_status(connection, event_id)
        connection.commit()

    if state is not None and state.status == "ARCHIVED":
        processed = await convert_archived_event_balances(event_id, ft_conversion_rate)
        if processed:
            logger.info("stronghold FT conversion processed %s users for event_id=%s", processed, event_id)


async def stronghold_lifecycle_loop() -> None:
    while True:
        try:
            await run_lifecycle_tick()
        except Exception:
            logger.exception("stronghold lifecycle loop failed")
        await asyncio.sleep(LIFECYCLE_TICK_SECONDS)
