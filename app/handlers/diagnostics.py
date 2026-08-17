"""Команды /version и /diagnostics (разделы 10-11 ТЗ по надёжности). Доступ — только
администраторам (любая активная роль в bot_admins/ADMIN_IDS, как и остальные
служебные команды вроде /db_get)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services import audit_log, backups, diagnostics
from app.services.cache_cleanup import cleanup_render_cache
from app.utils.messages import safe_edit_message
from app.utils.users import is_admin
from app.version import build_version_text

router = Router()


def _diagnostics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Проверить базу", callback_data="diag:check_db")],
            [InlineKeyboardButton(text="🧹 Очистить render cache", callback_data="diag:clean_cache")],
            [InlineKeyboardButton(text="🗑 Удалить старые бэкапы", callback_data="diag:delete_backups")],
            [InlineKeyboardButton(text="📦 Создать новый бэкап", callback_data="diag:create_backup")],
            [InlineKeyboardButton(text="⚠️ Найти зависшие матчи", callback_data="diag:stuck_matches")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="diag:refresh")],
        ]
    )


@router.message(Command("version"))
async def version_command(message: Message) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("🚫 Команда доступна только администрации лиги.")
        return
    await message.answer(build_version_text())


@router.message(Command("diagnostics"))
async def diagnostics_command(message: Message) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("🚫 Команда доступна только администрации лиги.")
        return
    report = await diagnostics.build_diagnostics_report()
    await message.answer(diagnostics.format_diagnostics_text(report), reply_markup=_diagnostics_keyboard())


@router.callback_query(F.data == "diag:refresh")
async def diag_refresh(callback: CallbackQuery) -> None:
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    report = await diagnostics.build_diagnostics_report()
    await safe_edit_message(callback, diagnostics.format_diagnostics_text(report), _diagnostics_keyboard())
    await callback.answer()


@router.callback_query(F.data == "diag:check_db")
async def diag_check_db(callback: CallbackQuery) -> None:
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from app.database.db import DATABASE_PATH

    ok = backups.quick_check(DATABASE_PATH)
    await callback.answer("✅ PRAGMA quick_check: ok" if ok else "🚨 PRAGMA quick_check вернул ошибку!", show_alert=True)


@router.callback_query(F.data == "diag:clean_cache")
async def diag_clean_cache(callback: CallbackQuery) -> None:
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    removed, freed, current = cleanup_render_cache()
    audit_log.record_committed(callback.from_user.id, 'diagnostics:clean_cache', details={'removed': removed, 'freed_bytes': freed})
    await callback.answer(f"Удалено файлов: {removed}. Освобождено: {diagnostics.format_bytes(freed)}.", show_alert=True)
    await diag_refresh(callback)


@router.callback_query(F.data == "diag:delete_backups")
async def diag_delete_backups(callback: CallbackQuery) -> None:
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    removed = backups.delete_backups_over_limit("manual") + backups.delete_backups_over_limit("daily")
    audit_log.record_committed(callback.from_user.id, 'diagnostics:delete_backups', details={'removed': removed})
    await callback.answer(f"Удалено старых бэкапов: {removed}.", show_alert=True)
    await diag_refresh(callback)


@router.callback_query(F.data == "diag:create_backup")
async def diag_create_backup(callback: CallbackQuery) -> None:
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    result = backups.create_backup("manual")
    audit_log.record_committed(callback.from_user.id, 'diagnostics:create_backup', details={'success': result.success, 'message': result.message})
    await callback.answer(result.message, show_alert=True)
    await diag_refresh(callback)


@router.callback_query(F.data == "diag:stuck_matches")
async def diag_stuck_matches(callback: CallbackQuery) -> None:
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    from app.services.creator_tournaments import find_matches_needing_attention

    stuck = await find_matches_needing_attention()
    if not stuck:
        await callback.answer("Зависших матчей не найдено.", show_alert=True)
        return
    lines = [f"#{m['id']} {m['tournament_title']}: {m['status']}" for m in stuck[:15]]
    await callback.answer("\n".join(lines)[:200], show_alert=True)
