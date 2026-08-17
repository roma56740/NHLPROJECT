"""Админка RANKED MODE: сезон, лиги (21 уровень), награды по лигам, Ranked Packs,
Ranked Pass, косметика (CARD_FRAME/PROFILE_BACKGROUND/TITLE + общий NICK_BADGE) —
создать/изменить/удалить/выдать игроку (раздел ADMIN PANEL ТЗ).

Ranked Season 1 — без отдельного экрана: коллекция управляется полностью
существующим admin_cards.py (обобщён по collection_id), карты добавляются туда же —
тот же выбор, что и у CLAN WAR Legends (см. admin_war2.py)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.services import ranked_bot, ranked_bot_names, ranked_core, ranked_pass, war2_cosmetics
from app.services.admin_permissions import PERMISSION_RANKED, has_admin_permission
from app.services.ranked_common import RankedError
from app.states.admin_ranked import (
    RankedCosmeticCreateStates,
    RankedGrantStates,
    RankedLeagueEditStates,
    RankedPackSlotStates,
    RankedPassCreateStates,
    RankedPassRewardStates,
)
from app.utils.messages import safe_delete_message, safe_edit_message
from app.utils.users import is_admin

router = Router()

CARD_FRAME_IMAGES_DIR = Path("assets/uploads/ranked_frames")
PROFILE_BACKGROUND_IMAGES_DIR = Path("assets/uploads/ranked_backgrounds")

RANKED_COSMETIC_TYPES = ("NICK_BADGE", "CARD_FRAME", "PROFILE_BACKGROUND", "TITLE")
RANKED_COSMETIC_TYPE_TITLES = {
    "NICK_BADGE": "🏷 Приставки",
    "CARD_FRAME": "🖼 Рамки для карт",
    "PROFILE_BACKGROUND": "🏞 Фоны профиля",
    "TITLE": "🎖 Титулы",
}
VALID_RARITIES = {"Common", "Rare", "Epic", "Legendary", "Event", "Icon"}


async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(callback.message, Message):
        await safe_edit_message(callback, text, reply_markup)
    else:
        await callback.answer()


def _back_row(callback_data: str = "admin_ranked:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]


def _require_admin(user_id: int | None) -> bool:
    return is_admin(user_id)


async def _build_admin_ranked_main_screen() -> tuple[str, InlineKeyboardMarkup]:
    season = await ranked_core.get_active_season()
    season_line = f"Активный сезон #{season.season_number}, до {season.ends_at}" if season else "Активного сезона нет."
    text = f"<b>🏆 RANKED MODE — админка</b>\n\n{season_line}"
    keyboard = [
        [InlineKeyboardButton(text="🗓 Сезон", callback_data="admin_ranked:season")],
        [InlineKeyboardButton(text="🎖 Лиги", callback_data="admin_ranked:leagues:1")],
        [InlineKeyboardButton(text="📦 Ranked Packs", callback_data="admin_ranked:packs")],
        [InlineKeyboardButton(text="🎫 Ranked Pass", callback_data="admin_ranked:pass")],
        [InlineKeyboardButton(text="🎨 Общая косметика", callback_data="admin_cosmetics:main")],
        [InlineKeyboardButton(text="🤖 Диагностика ботов", callback_data="admin_ranked:bot_diag")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel:main")],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "🏆 Админка Ranked")
async def admin_ranked_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not (_require_admin(user_id) and has_admin_permission(user_id, PERMISSION_RANKED)):
        await message.answer("Раздел доступен только администрации с правом Ranked.")
        return
    await state.clear()
    await safe_delete_message(message)
    text, keyboard = await _build_admin_ranked_main_screen()
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_ranked:main")
async def admin_ranked_main(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    text, keyboard = await _build_admin_ranked_main_screen()
    await _edit_or_send(callback, text, keyboard)




def _build_global_cosmetics_admin_screen() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "<b>🎨 Общая косметика</b>\n\n"
        "Эти предметы работают во всех режимах, продаются на Чёрном рынке и могут участвовать в обменах. "
        "Каждая выданная рамка, приписка, фон или титул является отдельным экземпляром."
    )
    keyboard = [
        [InlineKeyboardButton(text="🖼 Рамки карт", callback_data="admin_ranked:cos:CARD_FRAME")],
        [InlineKeyboardButton(text="🏞 Фоны профиля и состава", callback_data="admin_ranked:cos:PROFILE_BACKGROUND")],
        [InlineKeyboardButton(text="🏷 Приписки к нику", callback_data="admin_ranked:cos:NICK_BADGE")],
        [InlineKeyboardButton(text="🎖 Титулы", callback_data="admin_ranked:cos:TITLE")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel:main")],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "🎨 Управление косметикой")
async def admin_global_cosmetics_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not (_require_admin(user_id) and has_admin_permission(user_id, PERMISSION_RANKED)):
        await message.answer("Нет доступа к управлению косметикой.")
        return
    await state.clear()
    await safe_delete_message(message)
    text, keyboard = _build_global_cosmetics_admin_screen()
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_cosmetics:main")
async def admin_global_cosmetics_main(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    text, keyboard = _build_global_cosmetics_admin_screen()
    await _edit_or_send(callback, text, keyboard)


# ---------------------------------------------------------------------------
# Диагностика Ranked-ботов: покрытие каталога карт по лигам + список ников
# ---------------------------------------------------------------------------

async def _build_bot_diagnostics_screen() -> tuple[str, InlineKeyboardMarkup]:
    coverage = await ranked_bot.diagnose_catalog_coverage()
    lines = ["<b>🤖 Диагностика Ranked-ботов</b>", "", "<b>Карты каталога по лигам (G/D/F):</b>"]
    for entry in coverage:
        low, high = entry["range"]
        mark = "✅" if entry["sufficient"] else "⚠️"
        counts = entry["counts"]
        lines.append(f"{mark} {entry['league']} ({low}-{high}): G={counts['G']} D={counts['D']} F={counts['F']}")

    names_diag = ranked_bot_names.diagnostics()
    lines.append("")
    lines.append("<b>Ники ботов:</b>")
    lines.append(f"Путь: {names_diag['path']}")
    lines.append(f"Загружено: {names_diag['loaded_count']} (ожидается {names_diag['expected_count']})")
    lines.append(f"Уникальных: {names_diag['unique_count']}")
    lines.append(f"Дубликаты: {'да' if names_diag['has_duplicates'] else 'нет'}")
    if not names_diag["count_matches_expected"]:
        lines.append("⚠️ Количество ников не совпадает с ожидаемым (100).")
    if names_diag["sample"]:
        lines.append("Случайная выборка: " + ", ".join(names_diag["sample"]))

    keyboard = [
        [InlineKeyboardButton(text="🔄 Обновить выборку ников", callback_data="admin_ranked:bot_diag")],
        _back_row(),
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "🤖 Диагностика ботов")
async def admin_ranked_bot_diagnostics_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not (_require_admin(user_id) and has_admin_permission(user_id, PERMISSION_RANKED)):
        await message.answer("Нет доступа к диагностике Ranked.")
        return
    await state.clear()
    await safe_delete_message(message)
    text, keyboard = await _build_bot_diagnostics_screen()
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin_ranked:bot_diag")
async def admin_ranked_bot_diagnostics(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    text, keyboard = await _build_bot_diagnostics_screen()
    await _edit_or_send(callback, text, keyboard)


# ---------------------------------------------------------------------------
# Сезон
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_ranked:season")
async def admin_ranked_season(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return

    season = await ranked_core.get_active_season()
    if season:
        text = f"<b>🗓 Сезон #{season.season_number}</b>\n\nСтатус: {season.status}\nС {season.starts_at} по {season.ends_at}."
        keyboard = [
            [InlineKeyboardButton(text="🏁 Завершить сезон", callback_data="admin_ranked:season_end")],
            _back_row(),
        ]
    else:
        text = "<b>🗓 Сезон</b>\n\nАктивного сезона нет."
        keyboard = [
            [InlineKeyboardButton(text="▶️ Запустить сезон (56 дней)", callback_data="admin_ranked:season_start")],
            _back_row(),
        ]
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data == "admin_ranked:season_start")
async def admin_ranked_season_start(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    try:
        season = await ranked_core.start_ranked_season()
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer(f"Сезон #{season.season_number} запущен.")
    await admin_ranked_season(callback)


@router.callback_query(F.data == "admin_ranked:season_end")
async def admin_ranked_season_end(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    try:
        await ranked_core.end_ranked_season()
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Сезон завершён. Статистика сохранена.")
    await admin_ranked_season(callback)


# ---------------------------------------------------------------------------
# Лиги (21 запись: 7 дивизионов x 3 уровня) — редактирование порога очков
# ---------------------------------------------------------------------------

LEAGUES_PER_PAGE = 7


@router.callback_query(F.data.startswith("admin_ranked:leagues:"))
async def admin_ranked_leagues(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    page = int(callback.data.split(":")[2])

    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM ranked_leagues ORDER BY sort_order").fetchall()

    pages_count = max(1, (len(rows) + LEAGUES_PER_PAGE - 1) // LEAGUES_PER_PAGE)
    page = min(max(page, 1), pages_count)
    page_rows = rows[(page - 1) * LEAGUES_PER_PAGE : page * LEAGUES_PER_PAGE]

    text = f"<b>🎖 Лиги</b> (стр. {page}/{pages_count})\n\nНажми на лигу, чтобы изменить порог очков."
    keyboard = [
        [InlineKeyboardButton(text=f"{row['icon']} {row['title']} — от {row['min_points']}", callback_data=f"admin_ranked:league_edit:{row['id']}")]
        for row in page_rows
    ]
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_ranked:leagues:{page - 1}"))
    if page < pages_count:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_ranked:leagues:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_ranked:league_edit:"))
async def admin_ranked_league_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    league_id = int(callback.data.split(":")[2])
    await state.update_data(league_id=league_id)
    await state.set_state(RankedLeagueEditStates.waiting_for_min_points)
    await _edit_or_send(callback, "Введите новый порог очков (целое число, 0 или больше):")


@router.message(RankedLeagueEditStates.waiting_for_min_points)
async def admin_ranked_league_edit_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    data = await state.get_data()
    with get_connection() as connection:
        connection.execute(
            "UPDATE ranked_leagues SET min_points = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(text), data["league_id"]),
        )
        connection.commit()
    await state.clear()
    await message.answer("Порог очков обновлён.")


# ---------------------------------------------------------------------------
# Ranked Packs
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_ranked:packs")
async def admin_ranked_packs(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM ranked_packs ORDER BY id").fetchall()
    text = "<b>📦 Ranked Packs</b>\n\nВыбери пак, чтобы настроить слоты:"
    keyboard = [
        [InlineKeyboardButton(text=row["name"], callback_data=f"admin_ranked:pack:{row['id']}")]
        for row in rows
    ]
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_ranked:pack:"))
async def admin_ranked_pack_detail(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    pack_id = int(callback.data.split(":")[2])
    with get_connection() as connection:
        pack_row = connection.execute("SELECT * FROM ranked_packs WHERE id = ?", (pack_id,)).fetchone()
        slots = connection.execute("SELECT * FROM ranked_pack_slots WHERE pack_id = ? ORDER BY slot_number", (pack_id,)).fetchall()
        card_pool_count = connection.execute(
            "SELECT COUNT(*) AS n FROM ranked_pack_cards WHERE pack_id = ?", (pack_id,)
        ).fetchone()["n"]
    if pack_row is None:
        await callback.answer("Пак не найден.", show_alert=True)
        return

    lines = [f"<b>📦 {pack_row['name']}</b>", ""]
    for slot in slots:
        lines.append(f"Слот {slot['slot_number']}: {slot['reward_type']} ({slot['amount']})")
    if not slots:
        lines.append("Слотов пока нет.")
    lines.append("")
    lines.append(f"Карт в пуле (card-слоты берут отсюда случайно): {card_pool_count}")

    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить слот: валюта", callback_data=f"admin_ranked:pack_slot_currency:{pack_id}")],
        [InlineKeyboardButton(text="➕ Добавить слот: XP", callback_data=f"admin_ranked:pack_slot_xp:{pack_id}")],
        [InlineKeyboardButton(text="🃏 Добавить карту в пул", callback_data=f"admin_ranked:pack_slot_card:{pack_id}")],
        _back_row("admin_ranked:packs"),
    ]
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_ranked:pack_slot_currency:"))
async def admin_ranked_pack_slot_currency_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    pack_id = int(callback.data.split(":")[2])
    await state.update_data(pack_id=pack_id)
    await state.set_state(RankedPackSlotStates.waiting_for_currency_amount)
    await _edit_or_send(callback, "Введите сумму coins для этого слота (целое число):")


@router.message(RankedPackSlotStates.waiting_for_currency_amount)
async def admin_ranked_pack_slot_currency_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    data = await state.get_data()
    with get_connection() as connection:
        next_slot = connection.execute(
            "SELECT COALESCE(MAX(slot_number), 0) + 1 AS n FROM ranked_pack_slots WHERE pack_id = ?", (data["pack_id"],)
        ).fetchone()["n"]
        connection.execute(
            "INSERT INTO ranked_pack_slots (pack_id, slot_number, reward_type, currency_code, amount, active) VALUES (?, ?, 'currency', 'coins', ?, 1)",
            (data["pack_id"], next_slot, int(text)),
        )
        connection.commit()
    await state.clear()
    await message.answer("Слот добавлен.")


@router.callback_query(F.data.startswith("admin_ranked:pack_slot_xp:"))
async def admin_ranked_pack_slot_xp_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    pack_id = int(callback.data.split(":")[2])
    await state.update_data(pack_id=pack_id)
    await state.set_state(RankedPackSlotStates.waiting_for_xp_amount)
    await _edit_or_send(callback, "Введите количество Ranked XP для этого слота (целое число):")


@router.message(RankedPackSlotStates.waiting_for_xp_amount)
async def admin_ranked_pack_slot_xp_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    data = await state.get_data()
    with get_connection() as connection:
        next_slot = connection.execute(
            "SELECT COALESCE(MAX(slot_number), 0) + 1 AS n FROM ranked_pack_slots WHERE pack_id = ?", (data["pack_id"],)
        ).fetchone()["n"]
        connection.execute(
            "INSERT INTO ranked_pack_slots (pack_id, slot_number, reward_type, amount, active) VALUES (?, ?, 'xp', ?, 1)",
            (data["pack_id"], next_slot, int(text)),
        )
        connection.commit()
    await state.clear()
    await message.answer("Слот добавлен.")


@router.callback_query(F.data.startswith("admin_ranked:pack_slot_card:"))
async def admin_ranked_pack_slot_card_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    pack_id = int(callback.data.split(":")[2])
    await state.update_data(pack_id=pack_id)
    await state.set_state(RankedPackSlotStates.waiting_for_card_id)
    await _edit_or_send(
        callback,
        "Введите ID карты (см. в разделе «Карточки» админ-панели), чтобы добавить её в пул этого пака:",
    )


@router.message(RankedPackSlotStates.waiting_for_card_id)
async def admin_ranked_pack_slot_card_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число (ID карты). Введите ещё раз:")
        return
    card_id = int(text)
    data = await state.get_data()
    pack_id = data["pack_id"]
    with get_connection() as connection:
        card_row = connection.execute("SELECT id, name FROM cards WHERE id = ?", (card_id,)).fetchone()
        if card_row is None:
            await message.answer("Карта с таким ID не найдена. Введите ещё раз:")
            return
        try:
            connection.execute(
                "INSERT INTO ranked_pack_cards (pack_id, card_id) VALUES (?, ?)", (pack_id, card_id)
            )
        except sqlite3.IntegrityError:
            await state.clear()
            await message.answer(f"Карта «{card_row['name']}» уже в пуле этого пака.")
            return
        has_card_slot = connection.execute(
            "SELECT 1 FROM ranked_pack_slots WHERE pack_id = ? AND reward_type = 'card'", (pack_id,)
        ).fetchone()
        if has_card_slot is None:
            next_slot = connection.execute(
                "SELECT COALESCE(MAX(slot_number), 0) + 1 AS n FROM ranked_pack_slots WHERE pack_id = ?", (pack_id,)
            ).fetchone()["n"]
            connection.execute(
                "INSERT INTO ranked_pack_slots (pack_id, slot_number, reward_type, amount, active) VALUES (?, ?, 'card', 1, 1)",
                (pack_id, next_slot),
            )
        connection.commit()
    await state.clear()
    await message.answer(f"Карта «{card_row['name']}» добавлена в пул пака.")


# ---------------------------------------------------------------------------
# Ranked Pass
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_ranked:pass")
async def admin_ranked_pass_main(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    active_pass = await ranked_pass.get_active_pass()
    if active_pass is None:
        text = "<b>🎫 Ranked Pass</b>\n\nПропуск ещё не создан."
        keyboard = [[InlineKeyboardButton(text="➕ Создать пропуск", callback_data="admin_ranked:pass_create")], _back_row()]
    else:
        text = (
            f"<b>🎫 {active_pass.title}</b>\n\n"
            f"Уровней: {active_pass.levels_count}, XP/уровень: {active_pass.points_per_level}\n"
            f"Gold: {active_pass.gold_price_amount} {active_pass.gold_currency_code}\n"
            f"Platinum-апгрейд: {active_pass.upgrade_price_amount} {active_pass.upgrade_currency_code}"
        )
        keyboard = [
            [InlineKeyboardButton(text="➕ Добавить награду", callback_data=f"admin_ranked:pass_reward_add:{active_pass.id}")],
            _back_row(),
        ]
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data == "admin_ranked:pass_create")
async def admin_ranked_pass_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    await state.set_state(RankedPassCreateStates.waiting_for_title)
    await _edit_or_send(callback, "Введите название Ranked Pass:")


@router.message(RankedPassCreateStates.waiting_for_title)
async def admin_ranked_pass_create_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Введите ещё раз:")
        return
    await state.update_data(title=title)
    await state.set_state(RankedPassCreateStates.waiting_for_gold_price)
    await message.answer("Цена Gold Pass в coins (целое число, 0 — недоступен для покупки):")


@router.message(RankedPassCreateStates.waiting_for_gold_price)
async def admin_ranked_pass_create_gold_price(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    await state.update_data(gold_price=int(text))
    await state.set_state(RankedPassCreateStates.waiting_for_platinum_price)
    await message.answer("Цена Platinum Pass в coins (если покупается сразу, без апгрейда; иначе 0):")


@router.message(RankedPassCreateStates.waiting_for_platinum_price)
async def admin_ranked_pass_create_platinum_price(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    await state.update_data(platinum_price=int(text))
    await state.set_state(RankedPassCreateStates.waiting_for_upgrade_price)
    await message.answer("Цена апгрейда Gold -> Platinum в coins:")


@router.message(RankedPassCreateStates.waiting_for_upgrade_price)
async def admin_ranked_pass_create_upgrade_price(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    data = await state.get_data()
    season = await ranked_core.get_active_season()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ranked_passes
                (season_id, title, levels_count, points_per_level, gold_currency_code, gold_price_amount,
                 platinum_currency_code, platinum_price_amount, upgrade_currency_code, upgrade_price_amount, active)
            VALUES (?, ?, 60, 100, 'coins', ?, 'coins', ?, 'coins', ?, 1)
            """,
            (season.id if season else None, data["title"], data["gold_price"], data["platinum_price"], int(text)),
        )
        connection.commit()
    await state.clear()
    await message.answer(f"Ranked Pass «{data['title']}» создан (60 уровней).")


@router.callback_query(F.data.startswith("admin_ranked:pass_reward_add:"))
async def admin_ranked_pass_reward_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    pass_id = int(callback.data.split(":")[2])
    await state.update_data(pass_id=pass_id)
    await state.set_state(RankedPassRewardStates.waiting_for_level)
    await _edit_or_send(
        callback,
        "Введите в формате: уровень,линия (free/gold/platinum)\nНапример: 5,gold",
    )


@router.message(RankedPassRewardStates.waiting_for_level)
async def admin_ranked_pass_reward_level(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    parts = text.split(",")
    if len(parts) != 2 or not parts[0].strip().isdigit() or parts[1].strip() not in ("free", "gold", "platinum"):
        await message.answer("Формат: уровень,линия (free/gold/platinum). Например: 5,gold. Введите ещё раз:")
        return
    level = int(parts[0].strip())
    if not (1 <= level <= 60):
        await message.answer("Уровень должен быть от 1 до 60. Введите ещё раз:")
        return
    await state.update_data(level=level, track=parts[1].strip())
    await state.set_state(RankedPassRewardStates.waiting_for_amount)
    await message.answer("Сколько coins выдать за эту награду (целое число):")


@router.message(RankedPassRewardStates.waiting_for_amount)
async def admin_ranked_pass_reward_amount(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужно целое число. Введите ещё раз:")
        return
    await state.update_data(amount=int(text))
    await state.set_state(RankedPassRewardStates.waiting_for_title)
    await message.answer("Название награды (для отображения игроку):")


@router.message(RankedPassRewardStates.waiting_for_title)
async def admin_ranked_pass_reward_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or "").strip()
    data = await state.get_data()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ranked_pass_rewards (pass_id, level, track, reward_type, currency_code, amount, title, active)
            VALUES (?, ?, ?, 'currency', 'coins', ?, ?, 1)
            """,
            (data["pass_id"], data["level"], data["track"], data["amount"], title or f"Уровень {data['level']}"),
        )
        connection.commit()
    await state.clear()
    await message.answer("Награда добавлена.")


# ---------------------------------------------------------------------------
# Косметика (общий каталог с CLAN WAR 2.0 — app.services.war2_cosmetics)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin_ranked:cos:"))
async def admin_ranked_cosmetics_list(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    cosmetic_type = callback.data.split(":")[2]
    items = await war2_cosmetics.list_cosmetic_items(type=cosmetic_type)
    title = RANKED_COSMETIC_TYPE_TITLES.get(cosmetic_type, cosmetic_type)
    text = f"<b>{title}</b>\n\n" + ("Пока нет предметов." if not items else "Список предметов:")

    keyboard = []
    for item in items:
        mark = "✅" if item.active else "🚫"
        keyboard.append([InlineKeyboardButton(text=f"{mark} {item.title}", callback_data=f"admin_ranked:cositem:{item.id}")])
    keyboard.append([InlineKeyboardButton(text="➕ Создать", callback_data=f"admin_ranked:coscreate:{cosmetic_type}")])
    keyboard.append(_back_row("admin_cosmetics:main"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_ranked:cositem:"))
async def admin_ranked_cosmetic_item(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
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
        [InlineKeyboardButton(text="🎁 Выдать игроку", callback_data=f"admin_ranked:grant:{item.id}")],
        [InlineKeyboardButton(text="🚫 Деактивировать" if item.active else "✅ Активировать", callback_data=f"admin_ranked:costoggle:{item.id}")],
        _back_row(f"admin_ranked:cos:{item.type}"),
    ]
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin_ranked:costoggle:"))
async def admin_ranked_cosmetic_toggle(callback: CallbackQuery) -> None:
    if not _require_admin(callback.from_user.id):
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
    await admin_ranked_cosmetic_item(callback)


@router.callback_query(F.data.startswith("admin_ranked:coscreate:"))
async def admin_ranked_cosmetic_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    cosmetic_type = callback.data.split(":")[2]
    await state.update_data(cosmetic_type=cosmetic_type)
    await state.set_state(RankedCosmeticCreateStates.waiting_for_code)
    await _edit_or_send(callback, "Введите уникальный код предмета (латиницей, например ranked-card-frame-gold):")


@router.message(RankedCosmeticCreateStates.waiting_for_code)
async def admin_ranked_cosmetic_create_code(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    code = (message.text or "").strip()
    if not code:
        await message.answer("Код не может быть пустым. Введите ещё раз:")
        return
    await state.update_data(code=code)
    await state.set_state(RankedCosmeticCreateStates.waiting_for_title)
    await message.answer("Введите название предмета (видит игрок):")


@router.message(RankedCosmeticCreateStates.waiting_for_title)
async def admin_ranked_cosmetic_create_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Введите ещё раз:")
        return
    await state.update_data(title=title)
    await state.set_state(RankedCosmeticCreateStates.waiting_for_rarity)
    await message.answer("Редкость: Common / Rare / Epic / Legendary / Event / Icon")


@router.message(RankedCosmeticCreateStates.waiting_for_rarity)
async def admin_ranked_cosmetic_create_rarity(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    rarity = (message.text or "").strip().title()
    if rarity not in VALID_RARITIES:
        await message.answer(f"Недопустимая редкость. Варианты: {', '.join(sorted(VALID_RARITIES))}")
        return
    await state.update_data(rarity=rarity)
    data = await state.get_data()

    if data["cosmetic_type"] == "NICK_BADGE":
        await state.set_state(RankedCosmeticCreateStates.waiting_for_badge_text)
        await message.answer("Введите текст приставки (например LEGEND):")
    elif data["cosmetic_type"] == "TITLE":
        await state.set_state(RankedCosmeticCreateStates.waiting_for_badge_text)
        await message.answer("Введите текст титула:")
    else:
        await state.set_state(RankedCosmeticCreateStates.waiting_for_image)
        await message.answer("Пришлите PNG-картинку предмета.")


@router.message(RankedCosmeticCreateStates.waiting_for_badge_text)
async def admin_ranked_cosmetic_create_badge_text(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    badge_text = (message.text or "").strip()
    if not badge_text:
        await message.answer("Текст не может быть пустым. Введите ещё раз:")
        return
    data = await state.get_data()
    try:
        await war2_cosmetics.create_cosmetic_item(
            type=data["cosmetic_type"], code=data["code"], title=data["title"], rarity=data["rarity"], badge_text=badge_text,
        )
    except Exception as error:  # War2Error — общий каталог
        await message.answer(getattr(error, "message", str(error)))
        await state.clear()
        return
    await state.clear()
    await message.answer(f"«{data['title']}» создан.")


async def _save_cosmetic_image(message: Message, directory: Path) -> str | None:
    directory.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    now_value = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0

    if message.photo:
        photo = message.photo[-1]
        file_name = f"ranked_{now_value}_{user_id}_{photo.file_unique_id}.jpg"
        file_path = directory / file_name
        await message.bot.download(photo, destination=file_path)
        return file_path.as_posix()

    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        suffix = Path(message.document.file_name or "cosmetic.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        file_name = f"ranked_{now_value}_{user_id}_{message.document.file_unique_id}{suffix}"
        file_path = directory / file_name
        await message.bot.download(message.document, destination=file_path)
        return file_path.as_posix()

    return None


@router.message(RankedCosmeticCreateStates.waiting_for_image)
async def admin_ranked_cosmetic_create_image(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    directory = CARD_FRAME_IMAGES_DIR if data["cosmetic_type"] == "CARD_FRAME" else PROFILE_BACKGROUND_IMAGES_DIR
    image_path = await _save_cosmetic_image(message, directory)
    if image_path is None:
        await message.answer("Не удалось распознать картинку. Пришлите PNG/JPG файлом или фото.")
        return
    try:
        await war2_cosmetics.create_cosmetic_item(
            type=data["cosmetic_type"], code=data["code"], title=data["title"], rarity=data["rarity"], image_path=image_path,
        )
    except Exception as error:
        await message.answer(getattr(error, "message", str(error)))
        await state.clear()
        return
    await state.clear()
    await message.answer(f"«{data['title']}» создан.")


# ---------------------------------------------------------------------------
# Выдать игроку
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin_ranked:grant:"))
async def admin_ranked_grant_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации.", show_alert=True)
        return
    cosmetic_item_id = int(callback.data.split(":")[2])
    await state.update_data(cosmetic_item_id=cosmetic_item_id)
    await state.set_state(RankedGrantStates.waiting_for_telegram_id)
    await _edit_or_send(callback, "Отправьте Telegram ID игрока, которому выдать предмет:")


@router.message(RankedGrantStates.waiting_for_telegram_id)
async def admin_ranked_grant_apply(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_admin(message.from_user.id):
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
    try:
        await war2_cosmetics.grant_cosmetic_to_user(int(user_row["id"]), data["cosmetic_item_id"], source="admin_grant")
    except Exception as error:
        await message.answer(getattr(error, "message", str(error)))
        await state.clear()
        return

    await state.clear()
    await message.answer(f"Предмет выдан игроку {user_row['nickname']} (ID {telegram_id}).")
