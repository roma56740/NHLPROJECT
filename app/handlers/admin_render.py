from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.admin_render import build_admin_render_cancel_keyboard, build_admin_render_keyboard
from app.services.render_theme import RENDER_UPLOAD_DIR, get_render_theme_config, relative_asset_path
from app.services.cache_cleanup import remove_render_cache_file
from app.services.renders import render_admin_preview
from app.services.settings import set_setting_value
from app.states.admin_render import AdminRenderStates
from app.utils.users import is_admin

router = Router()

ASSET_KEYS = {
    "render_menu_background_path",
    "render_menu_video_path",
    "render_lineup_background_path",
}
TEXT_KEYS = {
    "render_menu_title",
    "render_menu_subtitle",
    "render_menu_accent",
    "render_lineup_accent",
}
COLOR_KEYS = {"render_menu_accent", "render_lineup_accent"}


def _panel_text() -> str:
    cfg = get_render_theme_config()
    value = lambda text: text if text else "—"
    return (
        "🎨 <b>РЕНДЕРЫ</b>\n\n"
        "<b>Главное меню</b>\n"
        f"• Заголовок: <code>{cfg.menu_title}</code>\n"
        f"• Подзаголовок: <code>{cfg.menu_subtitle}</code>\n"
        f"• Accent: <code>{cfg.menu_accent}</code>\n"
        f"• Сезонный фон: <code>{value(cfg.menu_background_path)}</code>\n"
        f"• Сезонное видео: <code>{value(cfg.menu_video_path)}</code>\n\n"
        "<b>Состав</b>\n"
        f"• Дефолтный фон: <code>{value(cfg.lineup_background_path)}</code>\n"
        f"• Accent: <code>{cfg.lineup_accent}</code>\n"
        f"• Линии химии: <b>{'ВКЛ' if cfg.lineup_chemistry_enabled else 'ВЫКЛ'}</b>\n\n"
        "Рамки карт здесь не задаются: каждая косметическая рамка привязана только к одной конкретной копии карты.\n"
        "Паки настраиваются в существующем разделе «🎬 Видео паков»: при открытии используется чистое видео без дополнительного showcase-рендера."
    )


@router.callback_query(F.data == "admin_render:main")
async def admin_render_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_caption(caption=_panel_text(), reply_markup=build_admin_render_keyboard(get_render_theme_config().lineup_chemistry_enabled))
        except Exception:
            try:
                await callback.message.edit_text(_panel_text(), reply_markup=build_admin_render_keyboard(get_render_theme_config().lineup_chemistry_enabled))
            except Exception:
                await callback.message.answer(_panel_text(), reply_markup=build_admin_render_keyboard(get_render_theme_config().lineup_chemistry_enabled))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_render:asset:"))
async def admin_render_asset(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = (callback.data or "").split(":", 2)[-1]
    if key not in ASSET_KEYS or not isinstance(callback.message, Message):
        await callback.answer("Неизвестный параметр", show_alert=True)
        return
    await state.set_state(AdminRenderStates.waiting_for_asset)
    await state.update_data(key=key)
    prompt = (
        "Пришли MP4 для видео меню или PNG/JPG/WEBP для фона.\n\n"
        "Для удаления кастомного ассета отправь <code>reset</code>."
    )
    try:
        await callback.message.edit_caption(caption=prompt, reply_markup=build_admin_render_cancel_keyboard())
    except Exception:
        await callback.message.edit_text(prompt, reply_markup=build_admin_render_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_render:text:"))
async def admin_render_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = (callback.data or "").split(":", 2)[-1]
    if key not in TEXT_KEYS or not isinstance(callback.message, Message):
        await callback.answer("Неизвестный параметр", show_alert=True)
        return
    await state.set_state(AdminRenderStates.waiting_for_text)
    await state.update_data(key=key)
    prompt = "Введи значение."
    if key in COLOR_KEYS:
        prompt = "Введи HEX-цвет, например <code>#4CB8FF</code>."
    try:
        await callback.message.edit_caption(caption=prompt, reply_markup=build_admin_render_cancel_keyboard())
    except Exception:
        await callback.message.edit_text(prompt, reply_markup=build_admin_render_cancel_keyboard())
    await callback.answer()


@router.message(AdminRenderStates.waiting_for_asset)
async def admin_render_save_asset(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = str(data.get("key") or "")
    if key not in ASSET_KEYS:
        await state.clear()
        return

    if (message.text or "").strip().lower() == "reset":
        await set_setting_value(key, "")
        await state.clear()
        await message.answer("✅ Кастомный ассет сброшен.")
        return

    is_video_key = key == "render_menu_video_path"
    file_obj = None
    suffix = ".png"
    if is_video_key and message.video:
        file_obj = message.video
        suffix = ".mp4"
    elif not is_video_key and message.photo:
        file_obj = message.photo[-1]
        suffix = ".jpg"
    elif message.document:
        mime = message.document.mime_type or ""
        if is_video_key and mime.startswith("video/"):
            file_obj = message.document
            suffix = Path(message.document.file_name or "asset.mp4").suffix.lower() or ".mp4"
        elif not is_video_key and mime.startswith("image/"):
            file_obj = message.document
            suffix = Path(message.document.file_name or "asset.png").suffix.lower() or ".png"

    if file_obj is None:
        await message.answer("Нужен MP4 для видео меню или PNG/JPG/WEBP для фона. Можно отправить <code>reset</code>.")
        return

    RENDER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RENDER_UPLOAD_DIR / f"{key}_{stamp}_{file_obj.file_unique_id}{suffix}"
    await message.bot.download(file_obj, destination=path)
    await set_setting_value(key, relative_asset_path(path))
    await state.clear()
    await message.answer("✅ Ассет сохранён. Новые рендеры используют его сразу.")


@router.message(AdminRenderStates.waiting_for_text)
async def admin_render_save_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = str(data.get("key") or "")
    value = (message.text or "").strip()
    if key not in TEXT_KEYS:
        await state.clear()
        return
    if key in COLOR_KEYS:
        if len(value) != 7 or not value.startswith("#"):
            await message.answer("Нужен HEX вида <code>#4CB8FF</code>.")
            return
        try:
            int(value[1:], 16)
        except ValueError:
            await message.answer("Нужен корректный HEX вида <code>#4CB8FF</code>.")
            return
        value = value.upper()
    elif not value:
        await message.answer("Значение не может быть пустым.")
        return
    await set_setting_value(key, value)
    await state.clear()
    await message.answer("✅ Сохранено.")


@router.callback_query(F.data == "admin_render:toggle_chemistry")
async def admin_render_toggle_chemistry(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    cfg = get_render_theme_config()
    await set_setting_value("render_lineup_chemistry_enabled", "0" if cfg.lineup_chemistry_enabled else "1")
    if isinstance(callback.message, Message):
        text = _panel_text()
        keyboard = build_admin_render_keyboard(not cfg.lineup_chemistry_enabled)
        try:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
        except Exception:
            await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer("Химия обновлена")


@router.callback_query(F.data.startswith("admin_render:preview:"))
async def admin_render_preview(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kind = (callback.data or "").split(":")[-1]
    if kind not in {"menu", "lineup"} or not isinstance(callback.message, Message):
        await callback.answer("Нет такого превью", show_alert=True)
        return
    try:
        path = render_admin_preview(kind, callback.from_user.id)
    except Exception as error:
        await callback.answer(f"Ошибка превью: {type(error).__name__}", show_alert=True)
        return
    try:
        await callback.bot.send_photo(chat_id=callback.message.chat.id, photo=FSInputFile(path), caption=f"👁 Превью: {kind}")
    finally:
        remove_render_cache_file(path)
    await callback.answer()
