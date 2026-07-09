from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_divisions import (
    ADMIN_DIVISIONS_PER_PAGE,
    build_admin_division_profile_keyboard,
    build_admin_divisions_list_keyboard,
    build_admin_divisions_main_keyboard,
    build_assets_keyboard,
    build_cancel_keyboard,
    build_missing_keyboard,
    build_team_assignments_keyboard,
)
from app.services.admin_divisions import (
    build_missing_asset_report,
    create_division,
    get_animation_assets_page,
    get_division,
    get_divisions,
    get_team_assignments_page,
    toggle_division_active,
    toggle_team_in_division,
    update_division_image,
    upsert_animation_asset,
)
from app.states.admin_divisions import AdminDivisionsStates
from app.texts.admin_divisions import (
    ADMIN_ASSET_IMAGE_TEXT,
    ADMIN_BAD_IMAGE_TEXT,
    ADMIN_CANCEL_TEXT,
    ADMIN_DIVISION_IMAGE_TEXT,
    ADMIN_DIVISION_NAME_TEXT,
    ADMIN_DIVISIONS_MAIN_TEXT,
    ADMIN_SAVED_TEXT,
    build_assets_text,
    build_division_profile_text,
    build_divisions_text,
    build_missing_report_text,
    build_team_assignments_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()
ADMIN_DIVISIONS_BUTTON_TEXT = "🏒 Дивизионы"
ANIMATION_IMAGES_DIR = Path("assets/uploads/animation")


async def admin_guard_message(message: Message) -> bool:
    if message.from_user and is_admin(message.from_user.id):
        return True
    await message.answer("🚫 Раздел доступен только администрации.")
    return False


async def admin_guard_callback(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


async def save_animation_image(message: Message, prefix: str) -> str | None:
    ANIMATION_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0
    safe_prefix = "".join(ch if ch.isalnum() else "_" for ch in prefix)[:40] or "asset"

    if message.photo:
        photo = message.photo[-1]
        path = ANIMATION_IMAGES_DIR / f"{safe_prefix}_{now}_{user_id}_{photo.file_unique_id}.jpg"
        await message.bot.download(photo, destination=path)
        return path.as_posix()

    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        suffix = Path(message.document.file_name or "asset.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        path = ANIMATION_IMAGES_DIR / f"{safe_prefix}_{now}_{user_id}_{message.document.file_unique_id}{suffix}"
        await message.bot.download(message.document, destination=path)
        return path.as_posix()

    return None


@router.message(F.text == ADMIN_DIVISIONS_BUTTON_TEXT)
async def admin_divisions_button(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    await state.clear()
    await safe_delete_message(message)
    await message.answer(ADMIN_DIVISIONS_MAIN_TEXT, reply_markup=build_admin_divisions_main_keyboard())


@router.callback_query(F.data == "admin_divisions:main")
async def admin_divisions_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    await edit_or_send(callback, ADMIN_DIVISIONS_MAIN_TEXT, reply_markup=build_admin_divisions_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_divisions:create")
async def admin_divisions_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.set_state(AdminDivisionsStates.waiting_for_division_name)
    await edit_or_send(callback, ADMIN_DIVISION_NAME_TEXT, reply_markup=build_cancel_keyboard())
    await callback.answer()


@router.message(AdminDivisionsStates.waiting_for_division_name)
async def admin_division_name_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    await safe_delete_message(message)
    division, error = await create_division(message.text or "")
    await state.clear()
    if division is None:
        await message.answer(f"⚠️ {error}", reply_markup=build_admin_divisions_main_keyboard())
        return
    await message.answer(build_division_profile_text(division), reply_markup=build_admin_division_profile_keyboard(division))


@router.callback_query(F.data == "admin_divisions:list")
async def admin_divisions_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    divisions = await get_divisions()
    await edit_or_send(callback, build_divisions_text(divisions), reply_markup=build_admin_divisions_list_keyboard(divisions))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_divisions:view:"))
async def admin_divisions_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    division_id = int(callback.data.split(":")[-1])
    division = await get_division(division_id)
    if division is None:
        await callback.answer("Дивизион не найден", show_alert=True)
        return
    await edit_or_send(callback, build_division_profile_text(division), reply_markup=build_admin_division_profile_keyboard(division))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_divisions:toggle:"))
async def admin_division_toggle(callback: CallbackQuery) -> None:
    if not await admin_guard_callback(callback):
        return
    division_id = int(callback.data.split(":")[-1])
    division = await toggle_division_active(division_id)
    if division is None:
        await callback.answer("Дивизион не найден", show_alert=True)
        return
    await edit_or_send(callback, build_division_profile_text(division), reply_markup=build_admin_division_profile_keyboard(division))
    await callback.answer("Статус обновлён")


@router.callback_query(F.data.startswith("admin_divisions:image:"))
async def admin_division_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    division_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminDivisionsStates.waiting_for_division_image)
    await state.update_data(division_id=division_id)
    await edit_or_send(callback, ADMIN_DIVISION_IMAGE_TEXT, reply_markup=build_cancel_keyboard())
    await callback.answer()


@router.message(AdminDivisionsStates.waiting_for_division_image)
async def admin_division_image_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    data = await state.get_data()
    division_id = int(data.get("division_id") or 0)
    image_path = await save_animation_image(message, "division")
    await safe_delete_message(message)
    if image_path is None:
        await message.answer(ADMIN_BAD_IMAGE_TEXT, reply_markup=build_cancel_keyboard())
        return
    division = await update_division_image(division_id, image_path)
    await state.clear()
    if division is None:
        await message.answer("⚠️ Дивизион не найден.", reply_markup=build_admin_divisions_main_keyboard())
        return
    await message.answer(f"{ADMIN_SAVED_TEXT}\n\n{build_division_profile_text(division)}", reply_markup=build_admin_division_profile_keyboard(division))


@router.callback_query(F.data.startswith("admin_divisions:teams:"))
async def admin_division_teams(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    parts = callback.data.split(":")
    division_id = int(parts[2])
    page = int(parts[3])
    division = await get_division(division_id)
    if division is None:
        await callback.answer("Дивизион не найден", show_alert=True)
        return
    teams_page = await get_team_assignments_page(division_id, page=page, per_page=ADMIN_DIVISIONS_PER_PAGE)
    await edit_or_send(callback, build_team_assignments_text(division, teams_page), reply_markup=build_team_assignments_keyboard(division_id, teams_page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_divisions:toggle_team:"))
async def admin_division_toggle_team(callback: CallbackQuery) -> None:
    if not await admin_guard_callback(callback):
        return
    parts = callback.data.split(":", 4)
    division_id = int(parts[2])
    page = int(parts[3])
    team_name = parts[4]
    selected = await toggle_team_in_division(division_id, team_name)
    division = await get_division(division_id)
    if division is None:
        await callback.answer("Дивизион не найден", show_alert=True)
        return
    teams_page = await get_team_assignments_page(division_id, page=page, per_page=ADMIN_DIVISIONS_PER_PAGE)
    await edit_or_send(callback, build_team_assignments_text(division, teams_page), reply_markup=build_team_assignments_keyboard(division_id, teams_page))
    await callback.answer("Команда добавлена" if selected else "Команда убрана")


@router.callback_query(F.data.startswith("admin_divisions:assets:"))
async def admin_animation_assets(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    _, _, asset_type, page_raw = callback.data.split(":")
    page = await get_animation_assets_page(asset_type, page=int(page_raw), per_page=ADMIN_DIVISIONS_PER_PAGE)
    await edit_or_send(callback, build_assets_text(page), reply_markup=build_assets_keyboard(page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_divisions:asset_upload:"))
async def admin_animation_asset_upload(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    parts = callback.data.split(":", 4)
    asset_type = parts[2]
    page = int(parts[3])
    asset_key = parts[4]
    await state.set_state(AdminDivisionsStates.waiting_for_asset_image)
    await state.update_data(asset_type=asset_type, page=page, asset_key=asset_key)
    await edit_or_send(callback, f"{ADMIN_ASSET_IMAGE_TEXT}\n\nОбъект: <b>{asset_key}</b>", reply_markup=build_cancel_keyboard())
    await callback.answer()


@router.message(AdminDivisionsStates.waiting_for_asset_image)
async def admin_animation_asset_image_value(message: Message, state: FSMContext) -> None:
    if not await admin_guard_message(message):
        return
    data = await state.get_data()
    asset_type = str(data.get("asset_type") or "team")
    page_number = int(data.get("page") or 1)
    asset_key = str(data.get("asset_key") or "")
    image_path = await save_animation_image(message, asset_type)
    await safe_delete_message(message)
    if image_path is None:
        await message.answer(ADMIN_BAD_IMAGE_TEXT, reply_markup=build_cancel_keyboard())
        return
    await upsert_animation_asset(asset_type, asset_key, asset_key, image_path)
    await state.clear()
    page = await get_animation_assets_page(asset_type, page=page_number, per_page=ADMIN_DIVISIONS_PER_PAGE)
    await message.answer(f"{ADMIN_SAVED_TEXT}\n\n{build_assets_text(page)}", reply_markup=build_assets_keyboard(page))


@router.callback_query(F.data == "admin_divisions:missing")
async def admin_divisions_missing(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard_callback(callback):
        return
    await state.clear()
    report = await build_missing_asset_report()
    await edit_or_send(callback, build_missing_report_text(report), reply_markup=build_missing_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_divisions:noop")
async def admin_divisions_noop(callback: CallbackQuery) -> None:
    await callback.answer()
