from __future__ import annotations

import asyncio
import html
import secrets
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.admin_bulk_upload import (
    SECTION_TITLES,
    apply_import,
    build_preview,
    cleanup_job_dir,
    get_target,
    list_targets,
    make_job_dir,
    prepare_source,
    template_csv_bytes,
    template_json_bytes,
)
from app.services.admin_permissions import has_admin_permission
from app.services.audit_log import record_committed
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()
MAX_TELEGRAM_FILE_BYTES = 50 * 1024 * 1024


class AdminBulkUploadStates(StatesGroup):
    waiting_source = State()


def _hub_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for section, title in SECTION_TITLES.items():
        available = [target for target in list_targets(section) if has_admin_permission(user_id, target.permission)]
        if available:
            rows.append([InlineKeyboardButton(text=f"{title} · {len(available)}", callback_data=f"admin_bulk:section:{section}")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-центр", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _section_keyboard(section: str, user_id: int) -> InlineKeyboardMarkup:
    targets = [target for target in list_targets(section) if has_admin_permission(user_id, target.permission)]
    rows = [[InlineKeyboardButton(text=f"📥 {target.title}", callback_data=f"admin_bulk:target:{target.code}")] for target in targets]
    rows.append([InlineKeyboardButton(text="⬅️ К разделам", callback_data="admin_bulk:hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _target_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 CSV-шаблон", callback_data=f"admin_bulk:template_csv:{code}"),
                InlineKeyboardButton(text="🧾 JSON-шаблон", callback_data=f"admin_bulk:template_json:{code}"),
            ],
            [InlineKeyboardButton(text="📤 Загрузить CSV / JSON / ZIP", callback_data=f"admin_bulk:upload:{code}")],
            [InlineKeyboardButton(text="📝 Вставить текстом", callback_data=f"admin_bulk:paste:{code}")],
            [InlineKeyboardButton(text="⬅️ К массовой загрузке", callback_data="admin_bulk:hub")],
        ]
    )


def _waiting_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Скачать CSV-шаблон", callback_data=f"admin_bulk:template_csv:{code}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_bulk:cancel:{code}")],
        ]
    )


def _preview_keyboard(token: str, code: str, can_confirm: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_confirm:
        rows.append([InlineKeyboardButton(text="✅ Импортировать атомарно", callback_data=f"admin_bulk:confirm:{token}")])
    rows.extend(
        [
            [InlineKeyboardButton(text="🔄 Загрузить другой файл", callback_data=f"admin_bulk:upload:{code}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_bulk:cancel:{code}")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await message.answer(text, reply_markup=keyboard)


def _require_admin(user_id: int | None) -> bool:
    return bool(user_id is not None and is_admin(user_id))


def _target_allowed(user_id: int, code: str):
    target = get_target(code)
    if target is None:
        return None
    if not has_admin_permission(user_id, target.permission):
        return None
    return target


def _target_text(code: str) -> str:
    target = get_target(code)
    if target is None:
        return "Цель импорта не найдена."
    required = ", ".join(target.required) or "нет"
    keys = ", ".join(target.key_fields) or "добавление без поиска дублей"
    asset_note = "\n• ZIP может содержать manifest.csv/manifest.json и папку assets/." if target.asset_column else ""
    return (
        f"<b>📥 Массовая загрузка · {html.escape(target.title)}</b>\n\n"
        f"{html.escape(target.description)}\n\n"
        f"• Форматы: <b>CSV, JSON, ZIP</b>\n"
        f"• Обязательные поля: <code>{html.escape(required)}</code>\n"
        f"• Ключ обновления: <code>{html.escape(keys)}</code>\n"
        f"• Лимит: 2 000 строк\n"
        f"• Режим: строгая проверка и одна транзакция{asset_note}\n\n"
        "Сначала скачай шаблон, заполни его и отправь обратно. Если есть хотя бы одна ошибка, база не изменится."
    )


@router.callback_query(F.data == "admin_bulk:hub")
async def bulk_hub(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Только для администрации", show_alert=True)
        return
    await _cleanup_state_job(state)
    await state.clear()
    available = sum(1 for target in list_targets() if has_admin_permission(callback.from_user.id, target.permission))
    text = (
        "<b>📥 Массовая загрузка</b>\n\n"
        f"Доступно направлений: <b>{available}</b>.\n"
        "Можно массово создавать, обновлять и выдавать данные через CSV, JSON или ZIP с ассетами.\n\n"
        "Импорт всегда выполняется атомарно: либо применяются все строки, либо ни одна."
    )
    await _edit_or_send(callback, text, _hub_keyboard(callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bulk:section:"))
async def bulk_section(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Только для администрации", show_alert=True)
        return
    section = (callback.data or "").split(":", 2)[2]
    if section not in SECTION_TITLES:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    targets = [target for target in list_targets(section) if has_admin_permission(callback.from_user.id, target.permission)]
    if not targets:
        await callback.answer("Нет доступа к целям этого раздела", show_alert=True)
        return
    await _edit_or_send(
        callback,
        f"<b>{SECTION_TITLES[section]} · Массовая загрузка</b>\n\nВыбери, что именно нужно загрузить или обновить.",
        _section_keyboard(section, callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bulk:target:"))
async def bulk_target(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":", 2)[2]
    target = _target_allowed(callback.from_user.id, code)
    if target is None:
        await callback.answer("Нет доступа или цель не найдена", show_alert=True)
        return
    await _edit_or_send(callback, _target_text(code), _target_keyboard(code))
    await callback.answer()


async def _send_template(callback: CallbackQuery, code: str, *, json_format: bool) -> None:
    target = _target_allowed(callback.from_user.id, code)
    if target is None:
        await callback.answer("Нет доступа или цель не найдена", show_alert=True)
        return
    suffix = ".json" if json_format else ".csv"
    token = secrets.token_hex(4)
    job_dir = make_job_dir(callback.from_user.id, f"template_{token}")
    path = job_dir / f"bulk_{target.code}_template{suffix}"
    path.write_bytes(template_json_bytes(target) if json_format else template_csv_bytes(target))
    message = callback.message
    if isinstance(message, Message):
        await message.answer_document(
            document=FSInputFile(path),
            caption=f"Шаблон: {target.title}. Заполни строки и загрузи файл через кнопку «📤 Загрузить».",
        )
    cleanup_job_dir(job_dir)
    await callback.answer("Шаблон отправлен")


@router.callback_query(F.data.startswith("admin_bulk:template_csv:"))
async def bulk_template_csv(callback: CallbackQuery) -> None:
    await _send_template(callback, (callback.data or "").split(":", 2)[2], json_format=False)


@router.callback_query(F.data.startswith("admin_bulk:template_json:"))
async def bulk_template_json(callback: CallbackQuery) -> None:
    await _send_template(callback, (callback.data or "").split(":", 2)[2], json_format=True)


@router.callback_query(F.data.startswith("admin_bulk:upload:") | F.data.startswith("admin_bulk:paste:"))
async def bulk_wait_source(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":", 2)[2]
    target = _target_allowed(callback.from_user.id, code)
    if target is None:
        await callback.answer("Нет доступа или цель не найдена", show_alert=True)
        return
    await _cleanup_state_job(state)
    await state.clear()
    await state.set_state(AdminBulkUploadStates.waiting_source)
    await state.update_data(target_code=code)
    text = (
        f"<b>📤 {html.escape(target.title)}</b>\n\n"
        "Отправь одним сообщением:\n"
        "• CSV-файл;\n"
        "• JSON-файл;\n"
        "• ZIP с manifest.csv/manifest.json и ассетами;\n"
        "• либо вставь CSV/JSON обычным текстом.\n\n"
        "После загрузки появится предпросмотр. Никаких изменений до подтверждения не будет."
    )
    await _edit_or_send(callback, text, _waiting_keyboard(code))
    await callback.answer()


async def _cleanup_state_job(state: FSMContext) -> None:
    data = await state.get_data()
    raw_path = data.get("job_dir")
    if raw_path:
        cleanup_job_dir(Path(str(raw_path)))


@router.message(AdminBulkUploadStates.waiting_source)
async def bulk_receive_source(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        return
    data = await state.get_data()
    code = str(data.get("target_code") or "")
    target = _target_allowed(message.from_user.id, code)
    if target is None:
        await state.clear()
        await message.answer("Нет доступа или цель импорта больше недоступна.")
        return

    token = secrets.token_hex(6)
    job_dir = make_job_dir(message.from_user.id, token)
    source_path: Path
    original_name: str

    try:
        if message.document is not None:
            file_size = int(message.document.file_size or 0)
            if file_size > MAX_TELEGRAM_FILE_BYTES:
                raise ValueError("файл больше 50 МБ")
            original_name = message.document.file_name or "bulk.csv"
            suffix = Path(original_name).suffix.lower()
            if suffix not in {".csv", ".json", ".zip"}:
                raise ValueError("нужен файл CSV, JSON или ZIP")
            source_path = job_dir / f"upload{suffix}"
            await message.bot.download(message.document, destination=source_path)
        elif message.text:
            raw = message.text.strip()
            if not raw:
                raise ValueError("пустое сообщение")
            suffix = ".json" if raw.startswith("[") or raw.startswith("{") else ".csv"
            original_name = f"pasted{suffix}"
            source_path = job_dir / original_name
            source_path.write_text(raw, encoding="utf-8")
        else:
            raise ValueError("отправь документ или текст CSV/JSON")

        prepared = await asyncio.to_thread(prepare_source, source_path, job_dir / "prepared", original_name)
        preview = await asyncio.to_thread(build_preview, target, prepared)
        await state.update_data(
            target_code=code,
            token=token,
            job_dir=str(job_dir),
            manifest_path=str(prepared.manifest_path),
            assets_root=str(prepared.assets_root) if prepared.assets_root else "",
            original_name=prepared.original_name,
        )

        lines = [
            f"<b>📥 Предпросмотр · {html.escape(target.title)}</b>",
            "",
            f"Файл: <code>{html.escape(prepared.original_name)}</code>",
            f"Всего строк: <b>{preview.total}</b>",
            f"Готово: <b>{preview.valid}</b>",
            f"С ошибками: <b>{len(preview.errors)}</b>",
            "",
        ]
        for item in preview.previews[:20]:
            marker = "✅" if item.error is None else "❌"
            line = f"{marker} #{item.index} {html.escape(item.display)}"
            if item.error:
                line += f" — <i>{html.escape(item.error)}</i>"
            lines.append(line)
        if preview.total > 20:
            lines.append(f"… ещё {preview.total - 20} строк")
        if preview.errors:
            lines.extend(["", "⚠️ Исправь ошибки и загрузи файл заново. Импорт с частичными строками запрещён."])
        else:
            lines.extend(["", "Все строки валидны. После подтверждения импорт пройдёт одной транзакцией."])

        await safe_delete_message(message)
        await message.answer("\n".join(lines), reply_markup=_preview_keyboard(token, code, not preview.errors))
    except Exception as error:  # noqa: BLE001
        cleanup_job_dir(job_dir)
        await safe_delete_message(message)
        await message.answer(
            f"❌ Не удалось подготовить импорт: <b>{html.escape(str(error))}</b>",
            reply_markup=_waiting_keyboard(code),
        )


@router.callback_query(F.data.startswith("admin_bulk:confirm:"))
async def bulk_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Только для администрации", show_alert=True)
        return
    token = (callback.data or "").split(":", 2)[2]
    data = await state.get_data()
    if token != str(data.get("token") or ""):
        await callback.answer("Этот предпросмотр устарел", show_alert=True)
        return
    code = str(data.get("target_code") or "")
    target = _target_allowed(callback.from_user.id, code)
    if target is None:
        await callback.answer("Нет доступа или цель не найдена", show_alert=True)
        return

    from app.services.admin_bulk_upload import PreparedSource

    prepared = PreparedSource(
        manifest_path=Path(str(data.get("manifest_path"))),
        original_name=str(data.get("original_name") or "bulk"),
        assets_root=Path(str(data.get("assets_root"))) if data.get("assets_root") else None,
    )
    try:
        result = await asyncio.to_thread(apply_import, target, prepared)
        record_committed(
            callback.from_user.id,
            "admin_bulk_import",
            entity_type=target.code,
            details={
                "file": prepared.original_name,
                "total": result.total,
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped": result.skipped,
            },
        )
        text = (
            f"<b>✅ Массовая загрузка завершена</b>\n\n"
            f"Раздел: <b>{html.escape(target.title)}</b>\n"
            f"Строк: <b>{result.total}</b>\n"
            f"Создано: <b>{result.inserted}</b>\n"
            f"Обновлено: <b>{result.updated}</b>\n"
            f"Пропущено: <b>{result.skipped}</b>\n\n"
            "Действие записано в общий аудит-лог."
        )
        await _edit_or_send(callback, text, _target_keyboard(code))
        await callback.answer("Импорт завершён")
    except Exception as error:  # noqa: BLE001
        await _edit_or_send(
            callback,
            f"<b>❌ Импорт отменён</b>\n\n{html.escape(str(error))}\n\nТранзакция откатилась, база не изменена.",
            _preview_keyboard(token, code, True),
        )
        await callback.answer("Импорт не выполнен", show_alert=True)
        return
    cleanup_job_dir(Path(str(data.get("job_dir"))))
    await state.clear()


@router.callback_query(F.data.startswith("admin_bulk:cancel:"))
async def bulk_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":", 2)[2]
    await _cleanup_state_job(state)
    await state.clear()
    target = _target_allowed(callback.from_user.id, code)
    if target is None:
        await bulk_hub(callback, state)
        return
    await _edit_or_send(callback, _target_text(code), _target_keyboard(code))
    await callback.answer("Отменено")
