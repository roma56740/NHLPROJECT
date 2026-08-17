"""Админ-панель "🛠 Технический перерыв" (ТЗ раздел 5). Управляет тем же
`game_settings.maintenance_mode`, что и MaintenanceModeMiddleware
(app/middlewares/maintenance.py) и быстрый тумблер в "⚙️ Настройки"
(app/handlers/admin_settings.py) — единая точка правды app.services.maintenance,
никакой отдельной системы состояния не заводится.

Доступ — существующая ролевая модель, PERMISSION_SETTINGS (тот же permission,
что и у "⚙️ Настройки"), проверяется и middleware (AdminPermissionMiddleware по
префиксу "admin_maintenance:"), и здесь на всякий случай явно.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services import maintenance
from app.services.admin_permissions import PERMISSION_SETTINGS, has_admin_permission
from app.services.audit_log import recent
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()


class AdminMaintenanceStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_photo = State()


def _require_permission(user_id: int | None) -> bool:
    return is_admin(user_id) and has_admin_permission(user_id, PERMISSION_SETTINGS)


async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await message.delete()
        except Exception:
            pass
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


def _back_row(callback_data: str = "admin_maintenance:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]


async def _build_status_screen(status: maintenance.MaintenanceStatus) -> tuple[str, InlineKeyboardMarkup]:
    mode_text = "🔴 ВКЛЮЧЁН" if status.enabled else "🟢 выключен"
    lines = [
        "<b>🛠 Технический перерыв</b>",
        "",
        f"Статус: <b>{mode_text}</b>",
    ]
    if status.enabled:
        lines.append(f"Включил: {status.enabled_by or '—'}")
        lines.append(f"Когда: {status.enabled_at or '—'}")
    else:
        lines.append(f"Последний раз выключил: {status.disabled_by or '—'}")
        lines.append(f"Когда: {status.disabled_at or '—'}")
    lines.append("")
    lines.append(f"Текст: {status.effective_text}")
    lines.append(f"Фото: {'установлено' if status.photo_file_id else 'не установлено'}")
    lines.append(f"Текст последним менял: {status.text_updated_by or '—'} ({status.text_updated_at or '—'})")
    lines.append(f"Фото последним менял: {status.photo_updated_by or '—'} ({status.photo_updated_at or '—'})")

    keyboard = [
        [InlineKeyboardButton(
            text="🔴 Завершить перерыв" if status.enabled else "🟢 Начать технический перерыв",
            callback_data="admin_maintenance:disable_confirm" if status.enabled else "admin_maintenance:enable_confirm",
        )],
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="admin_maintenance:edit_text")],
        [InlineKeyboardButton(text="🖼 Загрузить/заменить фото", callback_data="admin_maintenance:upload_photo")],
    ]
    if status.photo_file_id:
        keyboard.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data="admin_maintenance:remove_photo")])
    keyboard.append([InlineKeyboardButton(text="👁 Предпросмотр", callback_data="admin_maintenance:preview")])
    keyboard.append([InlineKeyboardButton(text="📜 История изменений", callback_data="admin_maintenance:history")])
    keyboard.append([InlineKeyboardButton(text="⬅️ В настройки", callback_data="admin_settings:main")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "🛠 Технический перерыв")
async def admin_maintenance_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _require_permission(user_id):
        await message.answer("Нет доступа к управлению техническим перерывом.")
        return
    await state.clear()
    await safe_delete_message(message)
    status = await maintenance.get_status(use_cache=False)
    text, keyboard = await _build_status_screen(status)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_maintenance:main")
async def admin_maintenance_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    status = await maintenance.get_status(use_cache=False)
    text, keyboard = await _build_status_screen(status)
    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_maintenance:enable_confirm")
async def admin_maintenance_enable_confirm(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    text = "После включения бот станет недоступен всем пользователям, кроме администраторов."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_maintenance:enable")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_maintenance:main")],
        ]
    )
    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_maintenance:enable")
async def admin_maintenance_enable(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await maintenance.enable(callback.from_user.id)
    await callback.answer("Технический перерыв включён.", show_alert=True)
    status = await maintenance.get_status(use_cache=False)
    text, keyboard = await _build_status_screen(status)
    await _edit_or_send(callback, text, keyboard)


@router.callback_query(F.data == "admin_maintenance:disable_confirm")
async def admin_maintenance_disable_confirm(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    text = "Завершить технический перерыв и вернуть доступ обычным пользователям?"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_maintenance:disable")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_maintenance:main")],
        ]
    )
    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_maintenance:disable")
async def admin_maintenance_disable(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await maintenance.disable(callback.from_user.id)
    await callback.answer("Технический перерыв выключен. Бот снова доступен всем.", show_alert=True)
    status = await maintenance.get_status(use_cache=False)
    text, keyboard = await _build_status_screen(status)
    await _edit_or_send(callback, text, keyboard)


@router.callback_query(F.data == "admin_maintenance:edit_text")
async def admin_maintenance_edit_text_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminMaintenanceStates.waiting_for_text)
    await _edit_or_send(
        callback,
        "Введите новый текст технического перерыва (или отправьте /cancel):",
        InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
    )
    await callback.answer()


@router.message(AdminMaintenanceStates.waiting_for_text)
async def admin_maintenance_edit_text_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    await state.clear()
    if not text or text == "/cancel":
        await message.answer("Отменено.")
        return
    await maintenance.set_message_text(text, message.from_user.id)
    await message.answer("Текст технического перерыва обновлён. Применяется немедленно.")


@router.callback_query(F.data == "admin_maintenance:upload_photo")
async def admin_maintenance_upload_photo_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminMaintenanceStates.waiting_for_photo)
    await _edit_or_send(
        callback,
        "Пришлите фотографию для экрана технического перерыва:",
        InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
    )
    await callback.answer()


@router.message(AdminMaintenanceStates.waiting_for_photo)
async def admin_maintenance_upload_photo_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    if not message.photo:
        await message.answer("Нужна именно фотография. Попробуй ещё раз через меню.")
        return
    photo = message.photo[-1]
    await maintenance.set_photo(photo.file_id, photo.file_unique_id, message.from_user.id)
    await message.answer("Фото технического перерыва обновлено. Применяется немедленно.")


@router.callback_query(F.data == "admin_maintenance:remove_photo")
async def admin_maintenance_remove_photo(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await maintenance.remove_photo(callback.from_user.id)
    await callback.answer("Фото удалено.")
    status = await maintenance.get_status(use_cache=False)
    text, keyboard = await _build_status_screen(status)
    await _edit_or_send(callback, text, keyboard)


@router.callback_query(F.data == "admin_maintenance:preview")
async def admin_maintenance_preview(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    status = await maintenance.get_status(use_cache=False)
    if callback.message is None:
        await callback.answer()
        return
    if status.photo_file_id:
        await callback.bot.send_photo(callback.message.chat.id, photo=status.photo_file_id, caption=status.effective_text)
    else:
        await callback.bot.send_message(callback.message.chat.id, status.effective_text)
    await callback.answer("Так это увидит обычный пользователь.")


@router.callback_query(F.data == "admin_maintenance:history")
async def admin_maintenance_history(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rows = recent(limit=50)
    maintenance_rows = [row for row in rows if str(row["action"]).startswith("maintenance_")][:20]
    lines = ["<b>📜 История изменений технического перерыва</b>", ""]
    if not maintenance_rows:
        lines.append("Пока нет записей.")
    for row in maintenance_rows:
        lines.append(f"{row['created_at']} · admin {row['actor_user_id']} · {row['action']}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[_back_row()])
    await _edit_or_send(callback, "\n".join(lines), keyboard)
    await callback.answer()
