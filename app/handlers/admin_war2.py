"""Админка CLAN WAR 2.0: сезон, режимы (on/off), косметика (FRAME/BACKGROUND/
NICK_BADGE) — создать/изменить/удалить/выдать игроку (раздел ТЗ "ADMIN PANEL").

Паки CLAN_WAR_PACK_LEVEL_1/2/3 и коллекция Clan War Legends отдельных экранов не
получают — они уже полностью управляются существующими разделами admin_cards.py
(коллекция/карты обобщены по collection_id) и Packs-админкой, созданы сидом
(app/services/war2_seed.py). Билеты/зарплатный лимит — существующие game_settings
war2_daily_tickets/war2_salary_cap, редактируются в общем экране настроек
(admin_settings.py), отдельная копия здесь не создаётся."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.services import war2_core, war2_cosmetics
from app.services.admin_permissions import PERMISSION_WAR2, has_admin_permission
from app.services.war2_common import War2Error
from app.services.war2_modes import WAR2_MODE_REGISTRY
from app.states.admin_war2 import War2CosmeticCreateStates, War2GrantStates
from app.utils.messages import safe_delete_message, safe_edit_message
from app.utils.users import is_admin

router = Router()

FRAME_IMAGES_DIR = Path("assets/uploads/war2_frames")
BACKGROUND_IMAGES_DIR = Path("assets/uploads/war2_backgrounds")


async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(callback.message, Message):
        await safe_edit_message(callback, text, reply_markup)
    else:
        await callback.answer()


def _back_row(callback_data: str = "admin_war2:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]


async def _build_admin_war2_main_screen() -> tuple[str, InlineKeyboardMarkup]:
    season = await war2_core.get_active_season()
    season_line = f"Активный сезон #{season.season_number}, до {season.ends_at}" if season else "Активного сезона нет."
    text = f"<b>⚔️ CLAN WAR 2.0 — админка</b>\n\n{season_line}"
    keyboard = [
        [InlineKeyboardButton(text="🗓 Сезон", callback_data="admin_war2:season")],
        [InlineKeyboardButton(text="🎛 Режимы", callback_data="admin_war2:modes")],
        [InlineKeyboardButton(text="🎨 Общая косметика", callback_data="admin_cosmetics:main")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel:main")],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "⚔️ Админка Clan War 2.0")
async def admin_war2_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not (is_admin(user_id) and has_admin_permission(user_id, PERMISSION_WAR2)):
        await message.answer("Нет доступа к админке Clan War 2.0.")
        return
    await state.clear()
    await safe_delete_message(message)
    text, keyboard = await _build_admin_war2_main_screen()
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_war2:main")
async def admin_war2_main(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    text, keyboard = await _build_admin_war2_main_screen()
    await _edit_or_send(callback, text, keyboard)


# ---------------------------------------------------------------------------
# Сезон
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_war2:season")
async def admin_war2_season(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return

    season = await war2_core.get_active_season()
    if season:
        text = f"<b>🗓 Сезон #{season.season_number}</b>\n\nСтатус: {season.status}\nС {season.starts_at} по {season.ends_at}."
        keyboard = [
            [InlineKeyboardButton(text="🏁 Завершить сезон", callback_data="admin_war2:season_end")],
            _back_row(),
        ]
    else:
        text = "<b>🗓 Сезон</b>\n\nАктивного сезона нет."
        keyboard = [
            [InlineKeyboardButton(text="▶️ Запустить сезон (4 недели)", callback_data="admin_war2:season_start")],
            _back_row(),
        ]
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data == "admin_war2:season_start")
async def admin_war2_season_start(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    from app.services.settings import get_int_setting

    length_days = await get_int_setting("war2_season_length_days", 28, minimum=1)
    with get_connection() as connection:
        last = connection.execute("SELECT MAX(season_number) AS n FROM war2_seasons").fetchone()
        next_number = int(last["n"] or 0) + 1
        starts_at = datetime.now(timezone.utc)
        ends_at = starts_at + timedelta(days=length_days)
        connection.execute(
            "INSERT INTO war2_seasons (season_number, status, starts_at, ends_at) VALUES (?, 'active', ?, ?)",
            (next_number, starts_at.strftime("%Y-%m-%d %H:%M:%S"), ends_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
        connection.commit()
    await callback.answer(f"Сезон #{next_number} запущен на {length_days} дней.")
    await admin_war2_season(callback)


@router.callback_query(F.data == "admin_war2:season_end")
async def admin_war2_season_end(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    with get_connection() as connection:
        connection.execute("UPDATE war2_seasons SET status = 'ended', updated_at = CURRENT_TIMESTAMP WHERE status = 'active'")
        connection.commit()
    await callback.answer("Сезон завершён. Статистика сохранена.")
    await admin_war2_season(callback)


# ---------------------------------------------------------------------------
# Режимы (on/off)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_war2:modes")
async def admin_war2_modes(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return

    with get_connection() as connection:
        rows = {row["code"]: bool(row["active"]) for row in connection.execute("SELECT code, active FROM war2_modes").fetchall()}

    text = "<b>🎛 Режимы CLAN WAR 2.0</b>\n\nВключённые режимы участвуют в War Roulette."
    keyboard = []
    for code, definition in WAR2_MODE_REGISTRY.items():
        active = rows.get(code, False)
        mark = "✅" if active else "⬜️"
        keyboard.append([InlineKeyboardButton(text=f"{mark} {definition.title}", callback_data=f"admin_war2:mode_toggle:{code}")])
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_war2:mode_toggle:"))
async def admin_war2_mode_toggle(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    code = callback.data.split(":")[2]
    if code not in WAR2_MODE_REGISTRY:
        await callback.answer("Неизвестный режим.", show_alert=True)
        return
    with get_connection() as connection:
        row = connection.execute("SELECT active FROM war2_modes WHERE code = ?", (code,)).fetchone()
        if row is None:
            await callback.answer("Режим отсутствует в БД.", show_alert=True)
            return
        if bool(row["active"]):
            active_count = int(connection.execute("SELECT COUNT(*) AS n FROM war2_modes WHERE active = 1").fetchone()["n"] or 0)
            if active_count <= 1:
                await callback.answer("Нельзя выключить последний активный режим CLAN WAR 2.0.", show_alert=True)
                return
        connection.execute(
            "UPDATE war2_modes SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END, updated_at = CURRENT_TIMESTAMP WHERE code = ?",
            (code,),
        )
        connection.commit()
    await admin_war2_modes(callback)


# ---------------------------------------------------------------------------
# Косметика: список + создание + удаление + выдача
# ---------------------------------------------------------------------------

COSMETIC_TYPE_TITLES = {"FRAME": "🖼 Рамки", "BACKGROUND": "🏞 Фоны", "NICK_BADGE": "🏷 Приставки"}


@router.callback_query(F.data.startswith("admin_war2:cos:"))
async def admin_war2_cosmetics_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    cosmetic_type = callback.data.split(":")[2]
    items = await war2_cosmetics.list_cosmetic_items(type=cosmetic_type)
    title = COSMETIC_TYPE_TITLES.get(cosmetic_type, cosmetic_type)
    text = f"<b>{title}</b>\n\n" + ("Пока нет предметов." if not items else "Список предметов:")

    keyboard = []
    for item in items:
        mark = "✅" if item.active else "🚫"
        keyboard.append([InlineKeyboardButton(text=f"{mark} {item.title}", callback_data=f"admin_war2:cositem:{item.id}")])
    keyboard.append([InlineKeyboardButton(text="➕ Создать", callback_data=f"admin_war2:coscreate:{cosmetic_type}")])
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_war2:cositem:"))
async def admin_war2_cosmetic_item(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    item_id = int(callback.data.split(":")[2])
    item = await war2_cosmetics.get_cosmetic_item(item_id)
    if item is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return
    text = (
        f"<b>{item.title}</b>\n\n"
        f"Тип: {item.type}\nКод: {item.code}\nРедкость: {item.rarity}\n"
        f"Активен: {'да' if item.active else 'нет'}\n"
        + (f"Приставка: [{item.badge_text}]\n" if item.badge_text else "")
        + (f"Картинка: {item.image_path}\n" if item.image_path else "")
    )
    keyboard = [
        [InlineKeyboardButton(text="🎁 Выдать игроку", callback_data=f"admin_war2:grant:{item.id}")],
        [InlineKeyboardButton(text="🚫 Деактивировать" if item.active else "✅ Активировать", callback_data=f"admin_war2:costoggle:{item.id}")],
        _back_row(f"admin_war2:cos:{item.type}"),
    ]
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_war2:costoggle:"))
async def admin_war2_cosmetic_toggle(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    item_id = int(callback.data.split(":")[2])
    item = await war2_cosmetics.get_cosmetic_item(item_id)
    if item is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return
    if item.active:
        await war2_cosmetics.delete_cosmetic_item(item_id)
    else:
        await war2_cosmetics.update_cosmetic_item(item_id, active=True)
    await admin_war2_cosmetic_item(callback)


@router.callback_query(F.data.startswith("admin_war2:coscreate:"))
async def admin_war2_cosmetic_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    cosmetic_type = callback.data.split(":")[2]
    await state.update_data(cosmetic_type=cosmetic_type)
    await state.set_state(War2CosmeticCreateStates.waiting_for_code)
    await _edit_or_send(callback, "Введите уникальный код предмета (латиницей, например frame-gold):")


@router.message(War2CosmeticCreateStates.waiting_for_code)
async def admin_war2_cosmetic_create_code(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return
    code = (message.text or "").strip()
    if not code:
        await message.answer("Код не может быть пустым. Введите ещё раз:")
        return
    await state.update_data(code=code)
    await state.set_state(War2CosmeticCreateStates.waiting_for_title)
    await message.answer("Введите название предмета (видит игрок):")


@router.message(War2CosmeticCreateStates.waiting_for_title)
async def admin_war2_cosmetic_create_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Введите ещё раз:")
        return
    await state.update_data(title=title)
    await state.set_state(War2CosmeticCreateStates.waiting_for_rarity)
    await message.answer("Редкость: Common / Rare / Epic / Legendary / Event / Icon")


VALID_RARITIES = {"Common", "Rare", "Epic", "Legendary", "Event", "Icon"}


@router.message(War2CosmeticCreateStates.waiting_for_rarity)
async def admin_war2_cosmetic_create_rarity(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return
    rarity = (message.text or "").strip().title()
    if rarity not in VALID_RARITIES:
        await message.answer(f"Недопустимая редкость. Варианты: {', '.join(sorted(VALID_RARITIES))}")
        return
    await state.update_data(rarity=rarity)
    data = await state.get_data()

    if data["cosmetic_type"] == "NICK_BADGE":
        await state.set_state(War2CosmeticCreateStates.waiting_for_badge_text)
        await message.answer("Введите текст приставки (например GOAT):")
    else:
        await state.set_state(War2CosmeticCreateStates.waiting_for_image)
        await message.answer("Пришлите PNG-картинку предмета.")


@router.message(War2CosmeticCreateStates.waiting_for_badge_text)
async def admin_war2_cosmetic_create_badge_text(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return
    badge_text = (message.text or "").strip()
    if not badge_text:
        await message.answer("Текст приставки не может быть пустым. Введите ещё раз:")
        return
    data = await state.get_data()
    try:
        await war2_cosmetics.create_cosmetic_item(
            type=data["cosmetic_type"], code=data["code"], title=data["title"], rarity=data["rarity"], badge_text=badge_text,
        )
    except War2Error as error:
        await message.answer(error.message)
        await state.clear()
        return
    await state.clear()
    await message.answer(f"Приставка «{data['title']}» создана.")


async def _save_cosmetic_image(message: Message, directory: Path) -> str | None:
    directory.mkdir(parents=True, exist_ok=True)
    now_value = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0

    if message.photo:
        photo = message.photo[-1]
        file_name = f"war2_{now_value}_{user_id}_{photo.file_unique_id}.jpg"
        file_path = directory / file_name
        await message.bot.download(photo, destination=file_path)
        return file_path.as_posix()

    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        suffix = Path(message.document.file_name or "cosmetic.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        file_name = f"war2_{now_value}_{user_id}_{message.document.file_unique_id}{suffix}"
        file_path = directory / file_name
        await message.bot.download(message.document, destination=file_path)
        return file_path.as_posix()

    return None


@router.message(War2CosmeticCreateStates.waiting_for_image)
async def admin_war2_cosmetic_create_image(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    directory = FRAME_IMAGES_DIR if data["cosmetic_type"] == "FRAME" else BACKGROUND_IMAGES_DIR
    image_path = await _save_cosmetic_image(message, directory)
    if image_path is None:
        await message.answer("Не удалось распознать картинку. Пришлите PNG/JPG файлом или фото.")
        return
    try:
        await war2_cosmetics.create_cosmetic_item(
            type=data["cosmetic_type"], code=data["code"], title=data["title"], rarity=data["rarity"], image_path=image_path,
        )
    except War2Error as error:
        await message.answer(error.message)
        await state.clear()
        return
    await state.clear()
    await message.answer(f"«{data['title']}» создан.")


# ---------------------------------------------------------------------------
# Выдать игроку
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin_war2:grant:"))
async def admin_war2_grant_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    cosmetic_item_id = int(callback.data.split(":")[2])
    await state.update_data(cosmetic_item_id=cosmetic_item_id)
    await state.set_state(War2GrantStates.waiting_for_telegram_id)
    await _edit_or_send(callback, "Отправьте Telegram ID игрока, которому выдать предмет:")


@router.message(War2GrantStates.waiting_for_telegram_id)
async def admin_war2_grant_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужен числовой Telegram ID. Введите ещё раз:")
        return
    telegram_id = int(text)

    with get_connection() as connection:
        user_row = connection.execute("SELECT id, nickname FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    if user_row is None:
        await message.answer("Игрок с таким Telegram ID не найден.")
        await state.clear()
        return

    data = await state.get_data()
    cosmetic_item_id = data["cosmetic_item_id"]
    try:
        await war2_cosmetics.grant_cosmetic_to_user(int(user_row["id"]), cosmetic_item_id, source="admin_grant")
    except War2Error as error:
        await message.answer(error.message)
        await state.clear()
        return

    await state.clear()
    await message.answer(f"Предмет выдан игроку {user_row['nickname']} (ID {telegram_id}).")
