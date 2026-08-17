"""Административные экраны THE STRONGHOLD (LiveOps) внутри Telegram admin-панели.

Доступ контролируется существующей ролевой моделью (`PERMISSION_STRONGHOLD`,
см. app/services/admin_permissions.py). Реализовано: Dashboard, Lifecycle,
публикация/валидация, Healthcheck, редакторы Upgrade Chain/Fortress/Missions/Season
Track/Store (просмотр + правка числовых полей + toggle active, создание для
Missions/Store), аналитика, саппорт пользователей, компенсации (одиночные и массовые),
аудит-лог. Массовые операции и редактирование чисел используют общий FSM-флоу
`StrongholdAdminStates.editing_numeric_field` (см. `_start_numeric_edit`).
"""

from __future__ import annotations

import json
import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.services import stronghold_admin, stronghold_admin_content as content
from app.services.admin_permissions import PERMISSION_STRONGHOLD, has_admin_permission
from app.services.stronghold_common import STRONGHOLD_SLUG, get_event_by_slug
from app.services.stronghold_health import get_health_status
from app.services.stronghold_schedule import (
    get_schedule_status,
    list_manual_unlock_history,
    manual_unlock_next,
    manual_unlock_specific,
    set_schedule_settings,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()

ADMIN_STRONGHOLD_BUTTON_TEXT = "🏰 THE STRONGHOLD"
COMPENSATION_TYPES = ["coins", "fortress_token", "season_xp"]


class StrongholdAdminStates(StatesGroup):
    compensation_user_id = State()
    compensation_type = State()
    compensation_amount = State()
    compensation_reason = State()

    editing_numeric_field = State()

    create_mission_type = State()
    create_mission_condition = State()
    create_mission_title = State()

    create_product_category = State()
    create_product_currency = State()
    create_product_title = State()
    create_product_price_amount = State()
    create_product_purchase_limit = State()
    create_product_item_type = State()
    create_product_item_value = State()
    create_product_item_card_id = State()
    create_product_item_card_amount = State()

    create_fortress_title = State()
    create_fortress_description = State()
    add_match_name = State()
    card_edit_salary = State()

    mass_comp_user_ids = State()
    mass_comp_type = State()
    mass_comp_amount = State()
    mass_comp_reason = State()

    schedule_edit_interval_days = State()
    schedule_edit_timezone = State()
    schedule_edit_start_at = State()
    schedule_unlock_specific = State()


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


def _require_permission(user_id: int | None) -> bool:
    return is_admin(user_id) and has_admin_permission(user_id, PERMISSION_STRONGHOLD)


async def build_dashboard() -> tuple[str, InlineKeyboardMarkup]:
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        return "🏰 <b>THE STRONGHOLD — Dashboard</b>\n\nСобытие не найдено (сид не выполнен?).", InlineKeyboardMarkup(inline_keyboard=[])

    lines = [
        "🏰 <b>THE STRONGHOLD — Dashboard</b>",
        "",
        f"Статус: <b>{event.status}</b> (сохранённый: {event.stored_status})",
        f"Начало: {event.starts_at or '—'}",
        f"Окончание ACTIVE: {event.ends_at or '—'}",
        f"Окончание Grace Period: {event.grace_ends_at or '—'}",
        f"Магазин в Grace Period: {'да' if event.store_available_in_grace else 'нет'}",
        f"Курс конвертации: 1 FT = {event.ft_conversion_rate} Coins",
        f"Версия конфигурации: {event.config_version}",
    ]
    keyboard = [
        [InlineKeyboardButton(text="🚀 Lifecycle", callback_data="admin_stronghold:lifecycle")],
        [InlineKeyboardButton(text="✅ Проверить публикацию", callback_data="admin_stronghold:validate")],
        [InlineKeyboardButton(text="🩺 Healthcheck", callback_data="admin_stronghold:health")],
        [InlineKeyboardButton(text="🃏 Коллекция и Upgrade Chain", callback_data="admin_stronghold:collection")],
        [InlineKeyboardButton(text="🏯 Fortress", callback_data="admin_stronghold:fortress_list:1")],
        [InlineKeyboardButton(text="🕐 Расписание башен", callback_data="admin_stronghold:schedule")],
        [InlineKeyboardButton(text="🎯 Missions", callback_data="admin_stronghold:missions_list")],
        [InlineKeyboardButton(text="📈 Season Track", callback_data="admin_stronghold:season_list")],
        [InlineKeyboardButton(text="🛒 Store", callback_data="admin_stronghold:store_list")],
        [InlineKeyboardButton(text="📊 Аналитика", callback_data="admin_stronghold:analytics")],
        [InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="admin_stronghold:support")],
        [InlineKeyboardButton(text="📜 Аудит-лог", callback_data="admin_stronghold:audit:1")],
        [InlineKeyboardButton(text="🧰 Массовые операции", callback_data="admin_stronghold:mass_ops")],
        [InlineKeyboardButton(text="🏠 В админ-меню", callback_data="menu:main")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


async def show_admin_dashboard_message(message: Message) -> None:
    """Вызывается из app/handlers/stronghold.py — единственной точки входа по кнопке
    "🏰 THE STRONGHOLD" (общей для игроков и админов, см. app/keyboards/reply.py)."""
    if message.from_user is None or not _require_permission(message.from_user.id):
        await message.answer("Раздел доступен только администраторам с доступом к THE STRONGHOLD.")
        return
    text, keyboard = await build_dashboard()
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_stronghold:main")
async def admin_stronghold_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    text, keyboard = await build_dashboard()
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:lifecycle")
async def admin_stronghold_lifecycle(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    lines = [
        "🚀 <b>Lifecycle THE STRONGHOLD</b>",
        "",
        f"Текущий статус: <b>{event.status}</b>",
        "",
        "Доступные переходы (только для тестирования/чрезвычайных ситуаций,",
        "в нормальном режиме статус меняется автоматически по датам):",
    ]
    keyboard = [
        [InlineKeyboardButton(text="▶️ ACTIVE", callback_data="admin_stronghold:transition:ACTIVE")],
        [InlineKeyboardButton(text="⏳ GRACE_PERIOD", callback_data="admin_stronghold:transition:GRACE_PERIOD")],
        [InlineKeyboardButton(text="🗄 ARCHIVED", callback_data="admin_stronghold:transition:ARCHIVED")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")],
    ]
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:transition:"))
async def admin_stronghold_transition(callback: CallbackQuery) -> None:
    admin_id = callback.from_user.id if callback.from_user else None
    if not _require_permission(admin_id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    new_status = (callback.data or "").split(":")[2]
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    stronghold_admin.force_transition(event.id, new_status, admin_id=admin_id, reason="admin_manual_transition")
    await callback.answer(f"Статус изменён на {new_status}.", show_alert=True)
    await admin_stronghold_lifecycle(callback)


def _fmt_dt(dt) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt is not None else "—"


async def _build_schedule_screen(event_id: int) -> tuple[str, InlineKeyboardMarkup]:
    status = await get_schedule_status(event_id)
    if status is None:
        return "🕐 <b>Расписание башен</b>\n\nСобытие не найдено.", InlineKeyboardMarkup(inline_keyboard=[])

    interval_days = status.interval_seconds / 86400
    lines = [
        "🕐 <b>Расписание башен THE STRONGHOLD</b>",
        "",
        f"Начало отсчёта: {_fmt_dt(status.schedule_start_at)} UTC",
        f"Timezone отображения: {status.timezone_name}",
        f"Интервал между башнями: {interval_days:g} дн.",
        "",
        f"Открыто башен: {status.unlocked_count}/{status.total_fortresses}",
        f"Из них вручную: {status.manual_unlock_override_count}",
    ]
    if status.all_unlocked:
        lines.append("Все башни уже открыты.")
    else:
        lines.append(f"Следующая башня: №{status.next_unlock_order_index}")
        lines.append(f"Откроется: {_fmt_dt(status.next_unlock_at)} UTC")

    keyboard = [
        [InlineKeyboardButton(text="🔓 Открыть следующую башню", callback_data="admin_stronghold:schedule_unlock_next_confirm")],
        [InlineKeyboardButton(text="🎯 Открыть конкретную башню", callback_data="admin_stronghold:schedule_unlock_specific")],
        [InlineKeyboardButton(text="🗓 Изменить дату начала отсчёта", callback_data="admin_stronghold:schedule_edit_start")],
        [InlineKeyboardButton(text="✏️ Изменить интервал (дней)", callback_data="admin_stronghold:schedule_edit_interval")],
        [InlineKeyboardButton(text="🌍 Изменить timezone отображения", callback_data="admin_stronghold:schedule_edit_timezone")],
        [InlineKeyboardButton(text="🔄 Пересчитать/обновить статус", callback_data="admin_stronghold:schedule")],
        [InlineKeyboardButton(text="📜 История ручных открытий", callback_data="admin_stronghold:schedule_history")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "🕐 Расписание Stronghold")
async def admin_stronghold_schedule_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _require_permission(user_id):
        await message.answer("Нет доступа к расписанию Stronghold.")
        return
    await state.clear()
    await safe_delete_message(message)
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await message.answer("Событие THE STRONGHOLD не найдено.")
        return
    text, keyboard = await _build_schedule_screen(event.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_stronghold:schedule")
async def admin_stronghold_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    text, keyboard = await _build_schedule_screen(event.id)
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:schedule_unlock_next_confirm")
async def admin_stronghold_schedule_unlock_next_confirm(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    text = "Открыть следующую башню вручную для ВСЕХ игроков сразу?\nЭто действие будет записано в аудит-лог."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_stronghold:schedule_unlock_next")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_stronghold:schedule")],
        ]
    )
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:schedule_unlock_next")
async def admin_stronghold_schedule_unlock_next(callback: CallbackQuery) -> None:
    admin_id = callback.from_user.id if callback.from_user else None
    if not _require_permission(admin_id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    new_count = await manual_unlock_next(event.id, admin_id=admin_id, reason="admin_manual_unlock_next")
    await callback.answer(f"Открыто башен: {new_count}.", show_alert=True)
    text, keyboard = await _build_schedule_screen(event.id)
    await edit_or_send(callback, text, keyboard)


@router.callback_query(F.data == "admin_stronghold:schedule_unlock_specific")
async def admin_stronghold_schedule_unlock_specific_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(StrongholdAdminStates.schedule_unlock_specific)
    await edit_or_send(callback, "Введите номер башни (order_index), которую нужно открыть вручную:")
    await callback.answer()


@router.message(StrongholdAdminStates.schedule_unlock_specific)
async def admin_stronghold_schedule_unlock_specific_apply(message: Message, state: FSMContext) -> None:
    admin_id = message.from_user.id if message.from_user else None
    if not _require_permission(admin_id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("Нужно положительное целое число. Введите ещё раз:")
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()
    if event is None:
        await message.answer("Событие не найдено.")
        return
    new_count = await manual_unlock_specific(event.id, int(text), admin_id=admin_id, reason=f"admin_manual_unlock_specific:{text}")
    await message.answer(f"Готово. Открыто башен: {new_count}.")


@router.callback_query(F.data == "admin_stronghold:schedule_edit_interval")
async def admin_stronghold_schedule_edit_interval_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(StrongholdAdminStates.schedule_edit_interval_days)
    await edit_or_send(callback, "Введите новый интервал между башнями в днях (можно дробное, например 0.5 = 12 часов):")
    await callback.answer()


@router.message(StrongholdAdminStates.schedule_edit_interval_days)
async def admin_stronghold_schedule_edit_interval_apply(message: Message, state: FSMContext) -> None:
    admin_id = message.from_user.id if message.from_user else None
    if not _require_permission(admin_id):
        await state.clear()
        return
    text = (message.text or "").strip().replace(",", ".")
    try:
        days = float(text)
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно положительное число дней. Введите ещё раз:")
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()
    if event is None:
        await message.answer("Событие не найдено.")
        return
    await set_schedule_settings(event.id, admin_id=admin_id, interval_seconds=int(days * 86400))
    await message.answer(f"Интервал обновлён: {days:g} дн. Уже открытые башни не закрываются.")


@router.callback_query(F.data == "admin_stronghold:schedule_edit_timezone")
async def admin_stronghold_schedule_edit_timezone_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(StrongholdAdminStates.schedule_edit_timezone)
    await edit_or_send(callback, "Введите IANA timezone для отображения (например Europe/Moscow, UTC):")
    await callback.answer()


@router.message(StrongholdAdminStates.schedule_edit_timezone)
async def admin_stronghold_schedule_edit_timezone_apply(message: Message, state: FSMContext) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    admin_id = message.from_user.id if message.from_user else None
    if not _require_permission(admin_id):
        await state.clear()
        return
    tz_name = (message.text or "").strip()
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        await message.answer("Неизвестная timezone. Введите ещё раз (например Europe/Moscow):")
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()
    if event is None:
        await message.answer("Событие не найдено.")
        return
    await set_schedule_settings(event.id, admin_id=admin_id, timezone_name=tz_name)
    await message.answer(f"Timezone отображения обновлена: {tz_name}.")


@router.callback_query(F.data == "admin_stronghold:schedule_edit_start")
async def admin_stronghold_schedule_edit_start_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(StrongholdAdminStates.schedule_edit_start_at)
    await edit_or_send(callback, "Введите дату и время начала отсчёта башен в UTC, формат ГГГГ-ММ-ДД ЧЧ:ММ:")
    await callback.answer()


@router.message(StrongholdAdminStates.schedule_edit_start_at)
async def admin_stronghold_schedule_edit_start_apply(message: Message, state: FSMContext) -> None:
    from datetime import timezone as _tz

    from app.services.stronghold_common import parse_db_datetime

    admin_id = message.from_user.id if message.from_user else None
    if not _require_permission(admin_id):
        await state.clear()
        return
    text = (message.text or "").strip()
    parsed = parse_db_datetime(text) or parse_db_datetime(f"{text}:00")
    if parsed is None:
        await message.answer("Не удалось разобрать дату. Формат: ГГГГ-ММ-ДД ЧЧ:ММ. Введите ещё раз:")
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()
    if event is None:
        await message.answer("Событие не найдено.")
        return
    await set_schedule_settings(event.id, admin_id=admin_id, schedule_start_at=parsed.astimezone(_tz.utc))
    await message.answer("Дата начала отсчёта башен обновлена. Уже открытые башни не закрываются.")


@router.callback_query(F.data == "admin_stronghold:schedule_history")
async def admin_stronghold_schedule_history(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    rows = await list_manual_unlock_history(event.id)
    lines = ["📜 <b>История ручных изменений расписания</b>", ""]
    if not rows:
        lines.append("Пока нет ручных действий.")
    for row in rows:
        lines.append(f"{row['created_at']} · admin {row['admin_id']} · {row['action']} · {row['reason'] or '—'}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:schedule")]])
    await edit_or_send(callback, "\n".join(lines), keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:validate")
async def admin_stronghold_validate(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    result = stronghold_admin.validate_event_config(event.id)
    if result.ok:
        text = "✅ <b>Конфигурация корректна</b>\n\nВсе суммы FT/Coins и структура сходятся с спекой."
    else:
        text = "❌ <b>Найдены проблемы конфигурации</b>\n\n" + "\n".join(f"• {error}" for error in result.errors)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")]])
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:audit:"))
async def admin_stronghold_audit(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    try:
        page = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 1

    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    audit_page = stronghold_admin.list_audit_log(event.id, page=page)
    lines = [f"📜 <b>Аудит-лог</b> (стр. {audit_page.page}/{audit_page.pages_count})", ""]
    for entry in audit_page.entries:
        admin_part = f"admin={entry.admin_id}" if entry.admin_id else "system"
        lines.append(f"#{entry.id} [{entry.created_at}] {admin_part} · {entry.action} · {entry.entity}#{entry.entity_id}")
        if entry.reason:
            lines.append(f"   причина: {entry.reason}")

    keyboard = []
    nav_row = []
    if audit_page.page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_stronghold:audit:{audit_page.page - 1}"))
    if audit_page.page < audit_page.pages_count:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_stronghold:audit:{audit_page.page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:support")
async def admin_stronghold_support(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await state.clear()
    await state.set_state(StrongholdAdminStates.compensation_user_id)
    await edit_or_send(
        callback,
        "🔍 <b>Поиск пользователя</b>\n\nОтправьте Telegram ID игрока.",
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_stronghold:main")]]),
    )
    await callback.answer()


@router.message(StrongholdAdminStates.compensation_user_id)
async def admin_stronghold_support_lookup(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return

    from app.database.db import get_connection
    from app.services.stronghold_wallet import get_wallet

    text_value = (message.text or "").strip()
    if not text_value.isdigit():
        await message.answer("Введите числовой Telegram ID.")
        return

    telegram_id = int(text_value)
    with get_connection() as connection:
        user_row = connection.execute("SELECT id, nickname FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()

    if user_row is None:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return

    user_id = int(user_row["id"])
    wallet = await get_wallet(user_id)
    event = await get_event_by_slug(STRONGHOLD_SLUG)

    with get_connection() as connection:
        upgrade_count = connection.execute(
            "SELECT COUNT(*) AS c FROM stronghold_upgrade_transactions WHERE user_id = ? AND status = 'success'", (user_id,)
        ).fetchone()["c"]
        fortress_completed = connection.execute(
            "SELECT COUNT(*) AS c FROM stronghold_user_fortress_progress WHERE user_id = ? AND status = 'COMPLETED'", (user_id,)
        ).fetchone()["c"]

    await state.update_data(support_user_id=user_id, support_event_id=event.id if event else None)
    await state.clear()

    lines = [
        f"👤 <b>{user_row['nickname']}</b> (telegram_id={telegram_id}, user_id={user_id})",
        "",
        f"🛡 Fortress Tokens: {wallet.fortress_tokens}",
        f"🪙 Coins: {wallet.coins}",
        f"⚔️ Успешных апгрейдов: {upgrade_count}",
        f"🏯 Fortress пройдено: {fortress_completed}/15",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Компенсация", callback_data=f"admin_stronghold:compensate:{user_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")],
        ]
    )
    await message.answer("\n".join(lines), reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_stronghold:compensate:"))
async def admin_stronghold_compensate_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        target_user_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    await state.update_data(compensation_target_user_id=target_user_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"admin_stronghold:comp_type:{t}")] for t in COMPENSATION_TYPES]
        + [[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_stronghold:main")]]
    )
    await edit_or_send(callback, "🎁 <b>Компенсация</b>\n\nВыберите тип награды.", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:comp_type:"))
async def admin_stronghold_compensate_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    compensation_type = (callback.data or "").split(":")[2]
    await state.update_data(compensation_type=compensation_type)
    await state.set_state(StrongholdAdminStates.compensation_amount)
    await edit_or_send(callback, "Введите количество (число).", None)
    await callback.answer()


@router.message(StrongholdAdminStates.compensation_amount)
async def admin_stronghold_compensate_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit() or int(text_value) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    await state.update_data(compensation_amount=int(text_value))
    await state.set_state(StrongholdAdminStates.compensation_reason)
    await message.answer("Укажите причину компенсации (для аудит-лога).")


@router.message(StrongholdAdminStates.compensation_reason)
async def admin_stronghold_compensate_reason(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return

    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой.")
        return

    data = await state.get_data()
    target_user_id = data.get("compensation_target_user_id")
    compensation_type = data.get("compensation_type")
    amount = data.get("compensation_amount")
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()

    if not (target_user_id and compensation_type and amount and event):
        await message.answer("Данные компенсации утеряны, начните заново.")
        return

    request_id = str(uuid.uuid4())
    applied = await stronghold_admin.grant_compensation(
        admin_id=message.from_user.id,
        target_user_id=int(target_user_id),
        event_id=event.id,
        compensation_type=str(compensation_type),
        amount=int(amount),
        pack_id=None,
        card_id=None,
        reason=reason,
        request_id=request_id,
    )
    await message.answer("✅ Компенсация выдана." if applied else "⚠️ Компенсация уже была выдана ранее (идемпотентность).")


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:health")
async def admin_stronghold_health(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    result = await get_health_status()
    icon = "✅" if result.ok else "❌"
    lines = [f"🩺 <b>Healthcheck</b> {icon}", ""]
    for check_name, passed in result.checks.items():
        lines.append(f"{'✅' if passed else '❌'} {check_name}")
    if result.details:
        lines.append("")
        for key, value in result.details.items():
            lines.append(f"{key}: {value}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")]])
    await edit_or_send(callback, "\n".join(lines), keyboard)
    await callback.answer()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:analytics")
async def admin_stronghold_analytics(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    summary = await content.get_analytics_summary(event.id)
    lines = [
        "📊 <b>Аналитика THE STRONGHOLD</b>",
        "",
        f"👥 Активных участников: {summary.active_participants}",
        f"⚔️ Успешных апгрейдов: {summary.total_upgrades}",
        f"🛡 FT начислено: {summary.ft_earned}",
        f"🛡 FT потрачено: {summary.ft_spent}",
        f"🪙 Coins потрачено в магазине: {summary.coins_spent_in_store}",
        f"🎯 Забрано наград за миссии: {summary.mission_claims}",
        f"🛒 Покупок в магазине: {summary.store_purchases}",
        "",
        "🏯 Прохождений по крепостям (funnel):",
    ]
    for order_index in range(1, 16):
        count = summary.fortress_completions.get(order_index, 0)
        lines.append(f"  {order_index}. {'█' * min(count, 20)} {count}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")]])
    await edit_or_send(callback, "\n".join(lines), keyboard)
    await callback.answer()


# ---------------------------------------------------------------------------
# Generic numeric-field edit flow (reused by Upgrade/Fortress/Missions/Season/Store)
# ---------------------------------------------------------------------------

NUMERIC_FIELD_LABELS = {
    "ft_cost": "FT",
    "coins_cost": "Coins",
    "first_completion_ft": "FT за первое прохождение",
    "repeat_coins_reward": "Coins за повторное прохождение",
    "opponent_ovr": "OVR соперника (1-99)",
    "target_value": "Цель (число)",
    "reward_ft": "Награда FT",
    "reward_coins": "Награда Coins",
    "reward_xp": "Награда Event XP",
    "xp_threshold": "Порог XP",
    "price_amount": "Цена",
    "purchase_limit": "Лимит покупок (0 = без лимита)",
    "salary": "Зарплата карты",
}


async def _prompt_numeric_field(message_or_callback, fields: list[str], collected: list[int]) -> None:
    field_name = fields[len(collected)]
    label = NUMERIC_FIELD_LABELS.get(field_name, field_name)
    text = f"Введите значение: <b>{label}</b> ({len(collected) + 1}/{len(fields)})"
    if isinstance(message_or_callback, CallbackQuery):
        await edit_or_send(message_or_callback, text)
    else:
        await message_or_callback.answer(text)


async def _start_numeric_edit(callback: CallbackQuery, state: FSMContext, *, entity: str, entity_id: int, fields: list[str], return_callback: str) -> None:
    await state.update_data(numeric_edit={"entity": entity, "entity_id": entity_id, "fields": fields, "collected": [], "return_callback": return_callback})
    await state.set_state(StrongholdAdminStates.editing_numeric_field)
    await _prompt_numeric_field(callback, fields, [])
    await callback.answer()


async def _apply_numeric_edit(entity: str, entity_id: int, values: list[int], admin_id: int, data: dict) -> str:
    """Возвращает текст результата."""
    if entity == "upgrade_step":
        await content.update_upgrade_step_costs(entity_id, ft_cost=values[0], coins_cost=values[1], admin_id=admin_id)
        return "✅ Стоимость шага обновлена."
    if entity == "fortress_reward":
        await content.update_fortress_reward(entity_id, first_completion_ft=values[0], repeat_coins_reward=values[1], admin_id=admin_id)
        return "✅ Награды крепости обновлены."
    if entity == "fortress_match_ovr":
        await content.update_fortress_match_ovr(entity_id, opponent_ovr=values[0], admin_id=admin_id)
        return "✅ OVR соперника обновлён."
    if entity == "mission_rewards":
        await content.update_mission_rewards(entity_id, target_value=values[0], reward_ft=values[1], reward_coins=values[2], reward_xp=values[3], admin_id=admin_id)
        return "✅ Задание обновлено."
    if entity == "season_level":
        await content.update_season_level(entity_id, xp_threshold=values[0], reward_ft=values[1], reward_coins=values[2], admin_id=admin_id)
        return "✅ Уровень Season Track обновлён."
    if entity == "store_product":
        await content.update_store_product_price(entity_id, price_amount=values[0], purchase_limit=values[1], admin_id=admin_id)
        return "✅ Товар обновлён."
    if entity == "new_mission_numeric":
        event = await get_event_by_slug(STRONGHOLD_SLUG)
        mission_id = await content.create_mission(
            event.id,
            type=data["new_mission_type"],
            title=data["new_mission_title"],
            condition_type=data["new_mission_condition"],
            target_value=values[0],
            reward_ft=values[1],
            reward_coins=values[2],
            reward_xp=values[3],
            admin_id=admin_id,
        )
        return f"✅ Задание создано (id={mission_id})."
    if entity == "card_salary":
        await content.update_card_salary(entity_id, salary=values[0], admin_id=admin_id)
        return "✅ Зарплата карты обновлена."
    if entity == "new_fortress_numeric":
        event = await get_event_by_slug(STRONGHOLD_SLUG)
        fortress_id = await content.create_fortress(
            event.id, title=data["new_fortress_title"], description=data.get("new_fortress_description", ""),
            first_completion_ft=values[0], repeat_coins_reward=values[1], admin_id=admin_id,
        )
        return f"✅ Крепость создана (id={fortress_id}, 6 стандартных матчей)."
    if entity == "new_match_numeric":
        match_id = await content.add_fortress_match(entity_id, opponent_name=data["new_match_name"], opponent_ovr=values[0], admin_id=admin_id)
        return f"✅ Матч добавлен (id={match_id})."
    return "⚠️ Неизвестная операция."


@router.message(StrongholdAdminStates.editing_numeric_field)
async def admin_stronghold_numeric_field_value(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return

    text_value = (message.text or "").strip()
    try:
        value = int(text_value)
    except ValueError:
        await message.answer("Введите целое число.")
        return
    if value < 0:
        await message.answer("Значение не может быть отрицательным.")
        return

    data = await state.get_data()
    edit_ctx = data.get("numeric_edit")
    if not edit_ctx:
        await state.clear()
        await message.answer("Сессия редактирования утеряна, начните заново.")
        return

    collected = list(edit_ctx["collected"]) + [value]
    fields = edit_ctx["fields"]

    if len(collected) < len(fields):
        edit_ctx["collected"] = collected
        await state.update_data(numeric_edit=edit_ctx)
        await _prompt_numeric_field(message, fields, collected)
        return

    result_text = await _apply_numeric_edit(edit_ctx["entity"], edit_ctx["entity_id"], collected, message.from_user.id, data)
    await state.clear()
    await message.answer(result_text)


# ---------------------------------------------------------------------------
# Upgrade Chain editor
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:collection")
async def admin_stronghold_collection(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    steps = await content.list_upgrade_steps(event.id)
    lines = ["🃏 <b>Upgrade Chain: Miro Heiskanen</b>", "", "Нажмите на шаг, чтобы изменить стоимость."]
    keyboard = [
        [InlineKeyboardButton(text=f"{s.from_overall}→{s.to_overall}: {s.ft_cost} FT + {s.coins_cost} Coins", callback_data=f"admin_stronghold:step_edit:{s.id}")]
        for s in steps
    ]
    total_ft = sum(s.ft_cost for s in steps)
    total_coins = sum(s.coins_cost for s in steps)
    lines.append(f"\nИтого: {total_ft} FT / {total_coins} Coins (спека: 375 FT / 4 050 000 Coins)")
    keyboard.append([InlineKeyboardButton(text="🃏 Все карты коллекции", callback_data="admin_stronghold:cards_list")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:step_edit:"))
async def admin_stronghold_step_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    step_id = int((callback.data or "").split(":")[2])
    await _start_numeric_edit(callback, state, entity="upgrade_step", entity_id=step_id, fields=["ft_cost", "coins_cost"], return_callback="admin_stronghold:collection")


# ---------------------------------------------------------------------------
# Card Definition editor
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:cards_list")
async def admin_stronghold_cards_list(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    cards = await content.list_collection_cards_admin(event.id)
    lines = ["🃏 <b>Карты коллекции THE STRONGHOLD</b>", ""]
    keyboard = []
    for card in cards:
        chain_icon = "⚔️" if card.is_upgrade_chain_card else ""
        active_icon = "✅" if card.active else "🚫"
        label = f"{active_icon} {chain_icon} {card.name} ({card.overall} OVR, ${card.salary})"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"admin_stronghold:card_view:{card.id}")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:collection")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:card_view:"))
async def admin_stronghold_card_view(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    card_id = int((callback.data or "").split(":")[2])
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    cards = await content.list_collection_cards_admin(event.id)
    card = next((c for c in cards if c.id == card_id), None)
    if card is None:
        await callback.answer("Карта не найдена.", show_alert=True)
        return

    lines = [
        f"🃏 <b>{card.name}</b>",
        f"OVR: {card.overall} · Позиция: {card.position}",
        f"Команда: {card.team} · Страна: {card.country}",
        f"Зарплата: {card.salary}",
        f"Статус: {'активна' if card.active else 'отключена'}",
    ]
    if card.is_upgrade_chain_card:
        lines.append("⚔️ Участвует в Upgrade Chain")
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить зарплату", callback_data=f"admin_stronghold:card_edit_salary:{card_id}")],
        [InlineKeyboardButton(text="🔁 Toggle active", callback_data=f"admin_stronghold:card_toggle:{card_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:cards_list")],
    ]
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:card_edit_salary:"))
async def admin_stronghold_card_edit_salary(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    card_id = int((callback.data or "").split(":")[2])
    await _start_numeric_edit(callback, state, entity="card_salary", entity_id=card_id, fields=["salary"], return_callback=f"admin_stronghold:card_view:{card_id}")


@router.callback_query(F.data.startswith("admin_stronghold:card_toggle:"))
async def admin_stronghold_card_toggle(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    card_id = int((callback.data or "").split(":")[2])
    new_active = await content.toggle_card_active(card_id, callback.from_user.id)
    await callback.answer(f"Карта теперь {'активна' if new_active else 'отключена'}.", show_alert=True)
    await admin_stronghold_card_view(callback)


# ---------------------------------------------------------------------------
# Fortress editor
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin_stronghold:fortress_list:"))
async def admin_stronghold_fortress_list(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    fortresses = await content.list_fortresses_admin(event.id)
    lines = ["🏯 <b>Fortress</b>", ""]
    keyboard = [
        [InlineKeyboardButton(text=f"{'✅' if f.active else '🚫'} {f.order_index}. {f.title} ({f.first_completion_ft} FT)", callback_data=f"admin_stronghold:fortress_view:{f.id}")]
        for f in fortresses
    ]
    total_ft = sum(f.first_completion_ft for f in fortresses)
    lines.append(f"Итого FT за первое прохождение: {total_ft} (спека: 220)")
    keyboard.append([InlineKeyboardButton(text="➕ Новая крепость", callback_data="admin_stronghold:fortress_create")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:fortress_create")
async def admin_stronghold_fortress_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await state.set_state(StrongholdAdminStates.create_fortress_title)
    await edit_or_send(callback, "➕ <b>Новая крепость</b>\n\nВведите название.")
    await callback.answer()


@router.message(StrongholdAdminStates.create_fortress_title)
async def admin_stronghold_fortress_create_title(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(new_fortress_title=title)
    await state.set_state(StrongholdAdminStates.create_fortress_description)
    await message.answer("Введите описание (или «-» чтобы пропустить).")


@router.message(StrongholdAdminStates.create_fortress_description)
async def admin_stronghold_fortress_create_description(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    description = (message.text or "").strip()
    if description == "-":
        description = ""
    await state.update_data(new_fortress_description=description)
    await state.update_data(numeric_edit={"entity": "new_fortress_numeric", "entity_id": 0, "fields": ["first_completion_ft", "repeat_coins_reward"], "collected": [], "return_callback": "admin_stronghold:fortress_list:1"})
    await state.set_state(StrongholdAdminStates.editing_numeric_field)
    await message.answer("Крепость создастся с 6 стандартными матчами (OVR/звёзды можно поправить после). Введите награды.")
    await _prompt_numeric_field(message, ["first_completion_ft", "repeat_coins_reward"], [])


@router.callback_query(F.data.startswith("admin_stronghold:fortress_view:"))
async def admin_stronghold_fortress_view(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    fortress_id = int((callback.data or "").split(":")[2])
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    fortresses = await content.list_fortresses_admin(event.id)
    fortress = next((f for f in fortresses if f.id == fortress_id), None)
    if fortress is None:
        await callback.answer("Крепость не найдена.", show_alert=True)
        return

    lines = [
        f"🏯 <b>{fortress.title}</b>",
        f"Статус: {'активна' if fortress.active else 'отключена'}",
        f"FT за первое прохождение: {fortress.first_completion_ft}",
        f"Coins за повтор: {fortress.repeat_coins_reward}",
    ]
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить награды", callback_data=f"admin_stronghold:fortress_edit:{fortress_id}")],
        [InlineKeyboardButton(text="🎮 Матчи", callback_data=f"admin_stronghold:fortress_matches:{fortress_id}")],
        [InlineKeyboardButton(text="🔁 Toggle active", callback_data=f"admin_stronghold:fortress_toggle:{fortress_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:fortress_list:1")],
    ]
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:fortress_edit:"))
async def admin_stronghold_fortress_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    fortress_id = int((callback.data or "").split(":")[2])
    await _start_numeric_edit(callback, state, entity="fortress_reward", entity_id=fortress_id, fields=["first_completion_ft", "repeat_coins_reward"], return_callback=f"admin_stronghold:fortress_view:{fortress_id}")


@router.callback_query(F.data.startswith("admin_stronghold:fortress_toggle:"))
async def admin_stronghold_fortress_toggle(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    fortress_id = int((callback.data or "").split(":")[2])
    new_active = await content.toggle_fortress_active(fortress_id, callback.from_user.id)
    await callback.answer(f"Крепость теперь {'активна' if new_active else 'отключена'}.", show_alert=True)
    await admin_stronghold_fortress_view(callback)


@router.callback_query(F.data.startswith("admin_stronghold:fortress_matches:"))
async def admin_stronghold_fortress_matches(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    fortress_id = int((callback.data or "").split(":")[2])
    matches = await content.get_fortress_matches_admin(fortress_id)
    lines = ["🎮 <b>Матчи крепости</b>", ""]
    keyboard = [
        [InlineKeyboardButton(text=f"{'✅' if m.active else '🚫'} {m.order_index}. {m.opponent_name} (OVR {m.opponent_ovr})", callback_data=f"admin_stronghold:match_view:{m.id}:{fortress_id}")]
        for m in matches
    ]
    keyboard.append([InlineKeyboardButton(text="➕ Добавить матч", callback_data=f"admin_stronghold:match_add:{fortress_id}")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_stronghold:fortress_view:{fortress_id}")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:match_view:"))
async def admin_stronghold_match_view(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    match_id = int(parts[2])
    fortress_id = int(parts[3])
    matches = await content.get_fortress_matches_admin(fortress_id)
    match = next((m for m in matches if m.id == match_id), None)
    if match is None:
        await callback.answer("Матч не найден.", show_alert=True)
        return

    lines = [
        f"🎮 <b>Матч {match.order_index}: {match.opponent_name}</b>",
        f"OVR соперника: {match.opponent_ovr}",
        f"Статус: {'активен' if match.active else 'отключён'}",
    ]
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить OVR", callback_data=f"admin_stronghold:match_edit:{match_id}:{fortress_id}")],
        [InlineKeyboardButton(text="🔁 Toggle active", callback_data=f"admin_stronghold:match_toggle:{match_id}:{fortress_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_stronghold:fortress_matches:{fortress_id}")],
    ]
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:match_edit:"))
async def admin_stronghold_match_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    match_id = int(parts[2])
    fortress_id = int(parts[3])
    await _start_numeric_edit(callback, state, entity="fortress_match_ovr", entity_id=match_id, fields=["opponent_ovr"], return_callback=f"admin_stronghold:match_view:{match_id}:{fortress_id}")


@router.callback_query(F.data.startswith("admin_stronghold:match_toggle:"))
async def admin_stronghold_match_toggle(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    match_id = int(parts[2])
    new_active = await content.toggle_fortress_match_active(match_id, callback.from_user.id)
    await callback.answer(f"Матч теперь {'активен' if new_active else 'отключён'}.", show_alert=True)
    await admin_stronghold_match_view(callback)


@router.callback_query(F.data.startswith("admin_stronghold:match_add:"))
async def admin_stronghold_match_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    fortress_id = int((callback.data or "").split(":")[2])
    await state.update_data(add_match_fortress_id=fortress_id)
    await state.set_state(StrongholdAdminStates.add_match_name)
    await edit_or_send(callback, "➕ <b>Новый матч</b>\n\nВведите имя соперника.")
    await callback.answer()


@router.message(StrongholdAdminStates.add_match_name)
async def admin_stronghold_match_add_name(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    data = await state.get_data()
    fortress_id = data.get("add_match_fortress_id")
    await state.update_data(new_match_name=name)
    await state.update_data(numeric_edit={"entity": "new_match_numeric", "entity_id": fortress_id, "fields": ["opponent_ovr"], "collected": [], "return_callback": f"admin_stronghold:fortress_matches:{fortress_id}"})
    await state.set_state(StrongholdAdminStates.editing_numeric_field)
    await _prompt_numeric_field(message, ["opponent_ovr"], [])


# ---------------------------------------------------------------------------
# Missions editor
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:missions_list")
async def admin_stronghold_missions_list(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    missions = await content.list_missions_admin(event.id)
    lines = ["🎯 <b>Missions</b>", ""]
    keyboard = [
        [InlineKeyboardButton(text=f"{'✅' if m.active else '🚫'} [{m.type}] {m.title} ({m.reward_ft} FT)", callback_data=f"admin_stronghold:mission_view:{m.id}")]
        for m in missions
    ]
    keyboard.append([InlineKeyboardButton(text="➕ Новое задание", callback_data="admin_stronghold:mission_create")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:mission_view:"))
async def admin_stronghold_mission_view(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    mission_id = int((callback.data or "").split(":")[2])
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    mission = next((m for m in await content.list_missions_admin(event.id) if m.id == mission_id), None)
    if mission is None:
        await callback.answer("Задание не найдено.", show_alert=True)
        return

    lines = [
        f"🎯 <b>{mission.title}</b>",
        f"Тип: {mission.type} · Условие: {mission.condition_type}",
        f"Статус: {'активно' if mission.active else 'отключено'}",
        f"Цель: {mission.target_value} · Награда: {mission.reward_ft} FT, {mission.reward_coins} Coins, {mission.reward_xp} XP",
    ]
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"admin_stronghold:mission_edit:{mission_id}")],
        [InlineKeyboardButton(text="🔁 Toggle active", callback_data=f"admin_stronghold:mission_toggle:{mission_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:missions_list")],
    ]
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:mission_edit:"))
async def admin_stronghold_mission_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    mission_id = int((callback.data or "").split(":")[2])
    await _start_numeric_edit(callback, state, entity="mission_rewards", entity_id=mission_id, fields=["target_value", "reward_ft", "reward_coins", "reward_xp"], return_callback=f"admin_stronghold:mission_view:{mission_id}")


@router.callback_query(F.data.startswith("admin_stronghold:mission_toggle:"))
async def admin_stronghold_mission_toggle(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    mission_id = int((callback.data or "").split(":")[2])
    new_active = await content.toggle_mission_active(mission_id, callback.from_user.id)
    await callback.answer(f"Задание теперь {'активно' if new_active else 'отключено'}.", show_alert=True)
    await admin_stronghold_mission_view(callback)


@router.callback_query(F.data == "admin_stronghold:mission_create")
async def admin_stronghold_mission_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await state.set_state(StrongholdAdminStates.create_mission_type)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"admin_stronghold:mc_type:{t}")] for t in content.MISSION_TYPES])
    await edit_or_send(callback, "➕ <b>Новое задание</b>\n\nВыберите тип.", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:mc_type:"))
async def admin_stronghold_mission_create_type(callback: CallbackQuery, state: FSMContext) -> None:
    mission_type = (callback.data or "").split(":")[2]
    await state.update_data(new_mission_type=mission_type)
    await state.set_state(StrongholdAdminStates.create_mission_condition)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"admin_stronghold:mc_cond:{c}")] for c in content.MISSION_CONDITION_TYPES]
    )
    await edit_or_send(callback, "Выберите условие выполнения.", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:mc_cond:"))
async def admin_stronghold_mission_create_condition(callback: CallbackQuery, state: FSMContext) -> None:
    condition_type = (callback.data or "").split(":")[2]
    await state.update_data(new_mission_condition=condition_type)
    await state.set_state(StrongholdAdminStates.create_mission_title)
    await edit_or_send(callback, "Введите название задания.")
    await callback.answer()


@router.message(StrongholdAdminStates.create_mission_title)
async def admin_stronghold_mission_create_title(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(new_mission_title=title)
    data = await state.get_data()
    await state.update_data(numeric_edit={"entity": "new_mission_numeric", "entity_id": 0, "fields": ["target_value", "reward_ft", "reward_coins", "reward_xp"], "collected": [], "return_callback": "admin_stronghold:missions_list"})
    await state.set_state(StrongholdAdminStates.editing_numeric_field)
    await _prompt_numeric_field(message, ["target_value", "reward_ft", "reward_coins", "reward_xp"], [])


# ---------------------------------------------------------------------------
# Season Track editor
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:season_list")
async def admin_stronghold_season_list(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    levels = await content.list_season_levels_admin(event.id)
    lines = ["📈 <b>Season Track</b>", ""]
    keyboard = [
        [InlineKeyboardButton(text=f"Уровень {l.level} ({l.xp_threshold} XP, {l.reward_ft} FT)", callback_data=f"admin_stronghold:season_edit:{l.id}")]
        for l in levels
    ]
    total_ft = sum(l.reward_ft for l in levels)
    lines.append(f"Итого FT: {total_ft} (спека: 50)")
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:season_edit:"))
async def admin_stronghold_season_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    level_id = int((callback.data or "").split(":")[2])
    await _start_numeric_edit(callback, state, entity="season_level", entity_id=level_id, fields=["xp_threshold", "reward_ft", "reward_coins"], return_callback="admin_stronghold:season_list")


# ---------------------------------------------------------------------------
# Store editor
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:store_list")
async def admin_stronghold_store_list(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    products = await content.list_store_products_admin(event.id)
    lines = ["🛒 <b>Store</b>", ""]
    keyboard = [
        [InlineKeyboardButton(text=f"{'✅' if p.active else '🚫'} [{p.category}] {p.title} — {p.price_amount} {p.price_currency_code}", callback_data=f"admin_stronghold:product_view:{p.id}")]
        for p in products
    ]
    keyboard.append([InlineKeyboardButton(text="➕ Новый товар", callback_data="admin_stronghold:product_create")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")])
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:product_view:"))
async def admin_stronghold_product_view(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    product_id = int((callback.data or "").split(":")[2])
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    product = next((p for p in await content.list_store_products_admin(event.id) if p.id == product_id), None)
    if product is None:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    lines = [
        f"🛒 <b>{product.title}</b>",
        f"Категория: {product.category} · Статус: {'активен' if product.active else 'отключён'}",
        f"Цена: {product.price_amount} {product.price_currency_code} · Лимит: {product.purchase_limit or 'без лимита'}",
    ]
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить цену/лимит", callback_data=f"admin_stronghold:product_edit:{product_id}")],
        [InlineKeyboardButton(text="🔁 Toggle active", callback_data=f"admin_stronghold:product_toggle:{product_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:store_list")],
    ]
    await edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:product_edit:"))
async def admin_stronghold_product_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    product_id = int((callback.data or "").split(":")[2])
    await _start_numeric_edit(callback, state, entity="store_product", entity_id=product_id, fields=["price_amount", "purchase_limit"], return_callback=f"admin_stronghold:product_view:{product_id}")


@router.callback_query(F.data.startswith("admin_stronghold:product_toggle:"))
async def admin_stronghold_product_toggle(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    product_id = int((callback.data or "").split(":")[2])
    new_active = await content.toggle_store_product_active(product_id, callback.from_user.id)
    await callback.answer(f"Товар теперь {'активен' if new_active else 'отключён'}.", show_alert=True)
    await admin_stronghold_product_view(callback)


@router.callback_query(F.data == "admin_stronghold:product_create")
async def admin_stronghold_product_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await state.set_state(StrongholdAdminStates.create_product_category)
    categories = ["Featured", "Packs", "Cards", "Resources", "Bundles"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"admin_stronghold:pc_cat:{c}")] for c in categories])
    await edit_or_send(callback, "➕ <b>Новый товар</b>\n\nВыберите категорию.", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:pc_cat:"))
async def admin_stronghold_product_create_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = (callback.data or "").split(":")[2]
    await state.update_data(new_product_category=category)
    await state.set_state(StrongholdAdminStates.create_product_currency)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Fortress Token", callback_data="admin_stronghold:pc_cur:fortress_token")],
            [InlineKeyboardButton(text="Coins", callback_data="admin_stronghold:pc_cur:coins")],
        ]
    )
    await edit_or_send(callback, "Валюта оплаты?", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stronghold:pc_cur:"))
async def admin_stronghold_product_create_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency_code = (callback.data or "").split(":")[2]
    await state.update_data(new_product_currency=currency_code)
    await state.set_state(StrongholdAdminStates.create_product_title)
    await edit_or_send(callback, "Введите название товара.")
    await callback.answer()


@router.message(StrongholdAdminStates.create_product_title)
async def admin_stronghold_product_create_title(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(new_product_title=title, new_product_contents=[])
    await state.set_state(StrongholdAdminStates.create_product_price_amount)
    await message.answer("Введите цену товара (число).")


@router.message(StrongholdAdminStates.create_product_price_amount)
async def admin_stronghold_product_create_price(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit():
        await message.answer("Введите целое число.")
        return
    await state.update_data(new_product_price_amount=int(text_value))
    await state.set_state(StrongholdAdminStates.create_product_purchase_limit)
    await message.answer("Лимит покупок на игрока (0 = без лимита).")


@router.message(StrongholdAdminStates.create_product_purchase_limit)
async def admin_stronghold_product_create_limit(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit():
        await message.answer("Введите целое число (0 или больше).")
        return
    await state.update_data(new_product_purchase_limit=int(text_value))
    await state.set_state(StrongholdAdminStates.create_product_item_type)
    await _show_bundle_item_menu(message, state)


async def _show_bundle_item_menu(message_or_callback, state: FSMContext) -> None:
    data = await state.get_data()
    contents = data.get("new_product_contents", [])
    lines = [f"🎁 <b>Награды товара</b> (уже добавлено: {len(contents)})", ""]
    for item in contents:
        if item["type"] == "currency":
            lines.append(f"• {item['amount']} {item['currency_code']}")
        elif item["type"] == "card":
            lines.append(f"• card_id={item['card_id']} x{item.get('amount', 1)}")
    lines.append("")
    lines.append("Добавьте награду или завершите создание товара.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="+ Coins", callback_data="admin_stronghold:bi_type:currency_coins")],
            [InlineKeyboardButton(text="+ Fortress Token", callback_data="admin_stronghold:bi_type:currency_fortress_token")],
            [InlineKeyboardButton(text="+ Карта (по card_id)", callback_data="admin_stronghold:bi_type:card")],
            [InlineKeyboardButton(text="✅ Готово", callback_data="admin_stronghold:bi_done")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_stronghold:store_list")],
        ]
    )
    text = "\n".join(lines)
    if isinstance(message_or_callback, CallbackQuery):
        await edit_or_send(message_or_callback, text, keyboard)
    else:
        await message_or_callback.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_stronghold:bi_type:"))
async def admin_stronghold_bundle_item_type(callback: CallbackQuery, state: FSMContext) -> None:
    item_type = (callback.data or "").split(":")[2]
    await state.update_data(bundle_item_type=item_type)
    if item_type.startswith("currency_"):
        currency_code = item_type.split("currency_", 1)[1]
        await state.update_data(bundle_item_currency=currency_code)
        await state.set_state(StrongholdAdminStates.create_product_item_value)
        await edit_or_send(callback, f"Введите количество {currency_code}.")
    else:
        await state.set_state(StrongholdAdminStates.create_product_item_card_id)
        await edit_or_send(callback, "Введите card_id карты (см. раздел «Коллекция»).")
    await callback.answer()


@router.message(StrongholdAdminStates.create_product_item_value)
async def admin_stronghold_bundle_item_currency_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit() or int(text_value) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    data = await state.get_data()
    contents = list(data.get("new_product_contents", []))
    contents.append({"type": "currency", "currency_code": data["bundle_item_currency"], "amount": int(text_value)})
    await state.update_data(new_product_contents=contents)
    await state.set_state(StrongholdAdminStates.create_product_item_type)
    await _show_bundle_item_menu(message, state)


@router.message(StrongholdAdminStates.create_product_item_card_id)
async def admin_stronghold_bundle_item_card_id(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit():
        await message.answer("Введите числовой card_id.")
        return
    with get_connection() as connection:
        exists = connection.execute("SELECT 1 FROM cards WHERE id = ?", (int(text_value),)).fetchone()
    if exists is None:
        await message.answer("Карта с таким card_id не найдена.")
        return
    await state.update_data(bundle_item_card_id=int(text_value))
    await state.set_state(StrongholdAdminStates.create_product_item_card_amount)
    await message.answer("Сколько копий карты выдавать?")


@router.message(StrongholdAdminStates.create_product_item_card_amount)
async def admin_stronghold_bundle_item_card_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit() or int(text_value) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    data = await state.get_data()
    contents = list(data.get("new_product_contents", []))
    contents.append({"type": "card", "card_id": data["bundle_item_card_id"], "amount": int(text_value)})
    await state.update_data(new_product_contents=contents)
    await state.set_state(StrongholdAdminStates.create_product_item_type)
    await _show_bundle_item_menu(message, state)


@router.callback_query(F.data == "admin_stronghold:bi_done")
async def admin_stronghold_bundle_finish(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    data = await state.get_data()
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()

    try:
        product_id = await content.create_store_product(
            event.id,
            category=data["new_product_category"],
            title=data["new_product_title"],
            description="",
            price_currency_code=data["new_product_currency"],
            price_amount=data["new_product_price_amount"],
            purchase_limit=data["new_product_purchase_limit"],
            contents=data.get("new_product_contents", []),
            admin_id=callback.from_user.id,
        )
    except (ValueError, KeyError) as error:
        await callback.answer(f"Ошибка: {error}", show_alert=True)
        return

    await callback.answer(f"✅ Товар создан (id={product_id}).", show_alert=True)
    await admin_stronghold_store_list(callback)
    await _prompt_numeric_field(message, ["price_amount", "purchase_limit", "reward_coins"], [])


# ---------------------------------------------------------------------------
# Mass operations
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stronghold:mass_ops")
async def admin_stronghold_mass_ops(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Отключить весь магазин", callback_data="admin_stronghold:mo_disable_store")],
            [InlineKeyboardButton(text="🎁 Массовая компенсация", callback_data="admin_stronghold:mo_mass_comp")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stronghold:main")],
        ]
    )
    await edit_or_send(callback, "🧰 <b>Массовые операции</b>", keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_stronghold:mo_disable_store")
async def admin_stronghold_mo_disable_store(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    result = await content.mass_disable_store(event.id, callback.from_user.id, reason="admin_mass_disable")
    await callback.answer(f"Отключено товаров: {result.affected}.", show_alert=True)
    await admin_stronghold_mass_ops(callback)


@router.callback_query(F.data == "admin_stronghold:mo_mass_comp")
async def admin_stronghold_mo_mass_comp(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id if callback.from_user else None):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await state.set_state(StrongholdAdminStates.mass_comp_user_ids)
    await edit_or_send(callback, "🎁 <b>Массовая компенсация</b>\n\nВведите user_id через запятую (внутренние ID пользователей, не Telegram ID).")
    await callback.answer()


@router.message(StrongholdAdminStates.mass_comp_user_ids)
async def admin_stronghold_mass_comp_user_ids(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    try:
        user_ids = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError:
        await message.answer("Некорректный список ID. Пример: 1,2,3")
        return
    if not user_ids:
        await message.answer("Список пуст.")
        return
    await state.update_data(mass_comp_user_ids=user_ids)
    await state.set_state(StrongholdAdminStates.mass_comp_type)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"admin_stronghold:mc2_type:{t}")] for t in COMPENSATION_TYPES])
    await message.answer(f"Выбрано {len(user_ids)} пользователей. Тип компенсации?", reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_stronghold:mc2_type:"))
async def admin_stronghold_mass_comp_type(callback: CallbackQuery, state: FSMContext) -> None:
    compensation_type = (callback.data or "").split(":")[2]
    await state.update_data(mass_comp_type=compensation_type)
    await state.set_state(StrongholdAdminStates.mass_comp_amount)
    await edit_or_send(callback, "Введите количество на каждого пользователя.")
    await callback.answer()


@router.message(StrongholdAdminStates.mass_comp_amount)
async def admin_stronghold_mass_comp_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    text_value = (message.text or "").strip()
    if not text_value.isdigit() or int(text_value) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    await state.update_data(mass_comp_amount=int(text_value))
    await state.set_state(StrongholdAdminStates.mass_comp_reason)
    await message.answer("Укажите причину (для аудит-лога).")


@router.message(StrongholdAdminStates.mass_comp_reason)
async def admin_stronghold_mass_comp_reason(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой.")
        return

    data = await state.get_data()
    user_ids = data.get("mass_comp_user_ids", [])
    compensation_type = data.get("mass_comp_type")
    amount = data.get("mass_comp_amount")
    event = await get_event_by_slug(STRONGHOLD_SLUG)
    await state.clear()

    if not (user_ids and compensation_type and amount and event):
        await message.answer("Данные утеряны, начните заново.")
        return

    result = await content.mass_compensate(event.id, message.from_user.id, user_ids, compensation_type=str(compensation_type), amount=int(amount), reason=reason)
    lines = [f"✅ Применено к {result.affected} из {len(user_ids)} пользователей."]
    if result.errors:
        lines.append(f"⚠️ Ошибки: {len(result.errors)}")
        lines.extend(result.errors[:10])
    await message.answer("\n".join(lines))
