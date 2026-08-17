from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.admin_panel import (
    build_admin_data_keyboard,
    build_admin_panel_main_keyboard,
    build_admins_keyboard,
    build_admin_role_keyboard,
    build_admin_change_role_keyboard,
    build_cancel_admin_input_keyboard,
)
from app.services.admin_panel import (
    add_admin,
    cleanup_export_file,
    cleanup_old_exports,
    create_database_backup_file,
    create_uploads_archive,
    get_admin_summary,
    is_main_admin,
    list_active_admins,
    remove_admin,
    update_admin_role,
)
from app.states.admin_panel import AdminPanelStates
from app.texts.admin_panel import (
    ADMIN_ADD_NOTIFY_FAILED_TEXT,
    ADMIN_ADD_NOTIFY_SUCCESS_TEXT,
    ADMIN_ADD_PROMPT_TEXT,
    ADMIN_ADD_SUCCESS_TEXT,
    ADMIN_DATA_TEXT,
    ADMIN_DB_NOT_FOUND_TEXT,
    ADMIN_EXPORT_START_TEXT,
    ADMIN_ID_ERROR_TEXT,
    ADMIN_INPUT_CANCELLED_TEXT,
    ADMIN_REMOVE_MAIN_DENIED_TEXT,
    ADMIN_REMOVE_NOT_FOUND_TEXT,
    ADMIN_REMOVE_PROMPT_TEXT,
    ADMIN_REMOVE_SUCCESS_TEXT,
    ADMIN_ROLE_CHANGE_SUCCESS_TEXT,
    ADMIN_ROLE_MAIN_DENIED_TEXT,
    ADMIN_ROLE_PROMPT_TEXT,
    ADMIN_CHANGE_ROLE_PROMPT_TEXT,
    ADMIN_UPLOADS_NOT_FOUND_TEXT,
    NEW_ADMIN_NOTIFICATION_TEXT,
    build_admin_panel_text,
    build_admins_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin
from app.services.admin_permissions import get_admin_role_title


router = Router()


def parse_telegram_id(text: str | None) -> int | None:
    if text is None:
        return None

    normalized = text.strip().replace(" ", "")
    if not normalized.isdigit():
        return None

    return int(normalized)


async def show_admin_panel(message: Message) -> None:
    summary = await get_admin_summary()
    await message.answer(
        build_admin_panel_text(summary),
        reply_markup=build_admin_panel_main_keyboard(),
    )


async def send_database_file(message: Message) -> None:
    backup_path = create_database_backup_file()
    if backup_path is None:
        await message.answer(ADMIN_DB_NOT_FOUND_TEXT)
        return

    try:
        await message.answer_document(
            document=FSInputFile(backup_path),
            caption="🗄 Файл базы данных готов.",
        )
    finally:
        cleanup_export_file(backup_path)
        cleanup_old_exports()


async def send_uploads_archive(message: Message) -> None:
    archive_path = create_uploads_archive()
    if archive_path is None:
        await message.answer(ADMIN_UPLOADS_NOT_FOUND_TEXT)
        return

    try:
        await message.answer_document(
            document=FSInputFile(archive_path),
            caption="🖼 Архив готов. Карты разложены по коллекциям, позициям и OVR.",
        )
    finally:
        cleanup_export_file(archive_path)
        cleanup_old_exports()


@router.message(Command("db_get"))
async def db_get_command(message: Message) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("🚫 Раздел доступен только администрации лиги.")
        return

    await message.answer(ADMIN_EXPORT_START_TEXT)
    await send_database_file(message)
    await send_uploads_archive(message)


@router.message(F.text == "📊 Админ-панель")
async def admin_panel_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("🚫 Раздел доступен только администрации лиги.")
        return

    await state.clear()
    await safe_delete_message(message)
    await show_admin_panel(message)


@router.callback_query(F.data == "admin_panel:main")
async def admin_panel_main_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.clear()
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    summary = await get_admin_summary()
    try:
        await message.edit_text(
            build_admin_panel_text(summary),
            reply_markup=build_admin_panel_main_keyboard(),
        )
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=build_admin_panel_text(summary),
            reply_markup=build_admin_panel_main_keyboard(),
        )

    await callback.answer()


@router.callback_query(F.data == "admin_panel:admins")
async def admin_panel_admins_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.clear()
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    admins = await list_active_admins()
    try:
        await message.edit_text(
            build_admins_text(admins),
            reply_markup=build_admins_keyboard(),
        )
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=build_admins_text(admins),
            reply_markup=build_admins_keyboard(),
        )

    await callback.answer()


@router.callback_query(F.data == "admin_panel:data")
async def admin_panel_data_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.clear()
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    try:
        await message.edit_text(
            ADMIN_DATA_TEXT,
            reply_markup=build_admin_data_keyboard(),
        )
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=ADMIN_DATA_TEXT,
            reply_markup=build_admin_data_keyboard(),
        )

    await callback.answer()


@router.callback_query(F.data == "admin_panel:admin_add")
async def admin_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.set_state(AdminPanelStates.add_admin)
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(
            ADMIN_ADD_PROMPT_TEXT,
            reply_markup=build_cancel_admin_input_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_panel:admin_remove")
async def admin_remove_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.set_state(AdminPanelStates.remove_admin)
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(
            ADMIN_REMOVE_PROMPT_TEXT,
            reply_markup=build_cancel_admin_input_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_panel:role_change")
async def admin_role_change_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.set_state(AdminPanelStates.change_admin_role)
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(
            ADMIN_CHANGE_ROLE_PROMPT_TEXT,
            reply_markup=build_cancel_admin_input_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_panel:cancel_input")
async def admin_input_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    await state.clear()
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(
            ADMIN_INPUT_CANCELLED_TEXT,
            reply_markup=build_admin_panel_main_keyboard(),
        )
    await callback.answer()


@router.message(AdminPanelStates.add_admin)
async def add_admin_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return

    telegram_id = parse_telegram_id(message.text)
    await safe_delete_message(message)

    if telegram_id is None:
        await message.answer(
            ADMIN_ID_ERROR_TEXT,
            reply_markup=build_cancel_admin_input_keyboard(),
        )
        return

    if is_main_admin(telegram_id):
        await state.clear()
        admins = await list_active_admins()
        await message.answer(
            f"{ADMIN_ROLE_MAIN_DENIED_TEXT}\n\n{build_admins_text(admins)}",
            reply_markup=build_admins_keyboard(),
        )
        return

    await state.update_data(pending_admin_id=telegram_id)
    await message.answer(
        ADMIN_ROLE_PROMPT_TEXT,
        reply_markup=build_admin_role_keyboard("admin_panel:add_role"),
    )


@router.callback_query(F.data.startswith("admin_panel:add_role:"))
async def add_admin_role_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    role = callback.data.split(":")[-1] if callback.data else "content_admin"
    data = await state.get_data()
    telegram_id = int(data.get("pending_admin_id") or 0)
    if telegram_id <= 0:
        await callback.answer("Telegram ID не найден, начни заново", show_alert=True)
        await state.clear()
        return

    await add_admin(telegram_id, callback.from_user.id, role=role)
    await state.clear()

    notify_text = ADMIN_ADD_NOTIFY_SUCCESS_TEXT
    try:
        await callback.bot.send_message(
            chat_id=telegram_id,
            text=f"{NEW_ADMIN_NOTIFICATION_TEXT}\n\nУровень доступа: <b>{get_admin_role_title(role)}</b>",
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        notify_text = ADMIN_ADD_NOTIFY_FAILED_TEXT

    admins = await list_active_admins()
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(
            f"{ADMIN_ADD_SUCCESS_TEXT}\nУровень: <b>{get_admin_role_title(role)}</b>\n{notify_text}\n\n{build_admins_text(admins)}",
            reply_markup=build_admins_keyboard(),
        )
    await callback.answer("Админ добавлен")


@router.message(AdminPanelStates.change_admin_role)
async def change_admin_role_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return

    telegram_id = parse_telegram_id(message.text)
    await safe_delete_message(message)

    if telegram_id is None:
        await message.answer(
            ADMIN_ID_ERROR_TEXT,
            reply_markup=build_cancel_admin_input_keyboard(),
        )
        return

    if is_main_admin(telegram_id):
        await state.clear()
        admins = await list_active_admins()
        await message.answer(
            f"{ADMIN_ROLE_MAIN_DENIED_TEXT}\n\n{build_admins_text(admins)}",
            reply_markup=build_admins_keyboard(),
        )
        return

    await state.clear()
    await message.answer(
        ADMIN_ROLE_PROMPT_TEXT,
        reply_markup=build_admin_change_role_keyboard(telegram_id),
    )


@router.callback_query(F.data.startswith("admin_panel:role_set:"))
async def set_admin_role_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    parts = callback.data.split(":") if callback.data else []
    telegram_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    role = parts[3] if len(parts) > 3 else "content_admin"

    if telegram_id <= 0 or is_main_admin(telegram_id):
        await callback.answer("Нельзя изменить этого админа", show_alert=True)
        return

    updated = await update_admin_role(telegram_id, role, actor_user_id=callback.from_user.id)
    admins = await list_active_admins()
    message = callback.message
    text = (
        f"{ADMIN_ROLE_CHANGE_SUCCESS_TEXT}\nУровень: <b>{get_admin_role_title(role)}</b>\n\n{build_admins_text(admins)}"
        if updated
        else f"{ADMIN_REMOVE_NOT_FOUND_TEXT}\n\n{build_admins_text(admins)}"
    )
    if isinstance(message, Message):
        await message.edit_text(text, reply_markup=build_admins_keyboard())
    await callback.answer("Уровень обновлён" if updated else "Админ не найден", show_alert=not updated)


@router.message(AdminPanelStates.remove_admin)
async def remove_admin_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return

    telegram_id = parse_telegram_id(message.text)
    await safe_delete_message(message)

    if telegram_id is None:
        await message.answer(
            ADMIN_ID_ERROR_TEXT,
            reply_markup=build_cancel_admin_input_keyboard(),
        )
        return

    await state.clear()

    if is_main_admin(telegram_id):
        result_text = ADMIN_REMOVE_MAIN_DENIED_TEXT
    else:
        removed = await remove_admin(telegram_id, actor_user_id=message.from_user.id)
        result_text = ADMIN_REMOVE_SUCCESS_TEXT if removed else ADMIN_REMOVE_NOT_FOUND_TEXT

    admins = await list_active_admins()
    await message.answer(
        f"{result_text}\n\n{build_admins_text(admins)}",
        reply_markup=build_admins_keyboard(),
    )


@router.callback_query(F.data == "admin_panel:get_db")
async def get_db_callback(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    message = callback.message
    if isinstance(message, Message):
        await callback.answer("Готовлю файл")
        await send_database_file(message)


@router.callback_query(F.data == "admin_panel:get_uploads")
async def get_uploads_callback(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    message = callback.message
    if isinstance(message, Message):
        await callback.answer("Готовлю архив")
        await send_uploads_archive(message)


@router.callback_query(F.data == "admin_panel:get_all")
async def get_all_callback(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return

    message = callback.message
    if isinstance(message, Message):
        await callback.answer("Готовлю файлы")
        await message.answer(ADMIN_EXPORT_START_TEXT)
        await send_database_file(message)
        await send_uploads_archive(message)
