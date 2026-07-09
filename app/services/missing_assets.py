from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import Bot

from app.services.admin_divisions import build_missing_asset_report
from app.services.admin_panel import list_active_admins
from app.services.settings import get_bool_setting, get_int_setting, get_setting, set_setting_value
from app.texts.admin_divisions import build_missing_report_text


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def missing_assets_notification_loop(bot: Bot) -> None:
    """Раз в 2 часа напоминает админам о недостающих картинках/данных."""
    while True:
        try:
            enabled = await get_bool_setting("asset_warning_enabled", True)
            if enabled:
                interval_hours = await get_int_setting("asset_warning_interval_hours", 2, minimum=1, maximum=168)
                last_sent = _parse_datetime(await get_setting("asset_warning_last_sent_at", ""))
                now = datetime.now()
                if last_sent is None or now - last_sent >= timedelta(hours=interval_hours):
                    report = await build_missing_asset_report(limit=25)
                    if report.has_issues:
                        admins = await list_active_admins()
                        text = build_missing_report_text(report)
                        for admin in admins:
                            if not admin.active:
                                continue
                            try:
                                await bot.send_message(chat_id=admin.telegram_id, text=text)
                            except Exception:
                                pass
                            await asyncio.sleep(0.05)
                    await set_setting_value("asset_warning_last_sent_at", now.isoformat(timespec="seconds"))
        except Exception:
            pass

        await asyncio.sleep(300)
