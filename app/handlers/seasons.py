from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.seasons import (
    TIER_TITLES,
    get_current_top,
    get_last_seasons,
    get_tiers,
    list_players_telegram_for_broadcast,
    reset_season,
    update_tier_field,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()

SEASON_BUTTON_TEXT = "🔄 Сброс сезона"


class SeasonTierStates(StatesGroup):
    waiting_for_value = State()


def build_season_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Награды по местам", callback_data="season:tiers")],
            [InlineKeyboardButton(text="📜 История сезонов", callback_data="season:history")],
            [InlineKeyboardButton(text="⚠️ Сбросить сезон", callback_data="season:reset_confirm")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="season:main")],
        ]
    )


def build_season_tiers_keyboard(tiers) -> InlineKeyboardMarkup:
    rows = []
    for t in tiers:
        rows.append([InlineKeyboardButton(text=f"{TIER_TITLES.get(t.tier_key, t.tier_key)}", callback_data=f"season:tier:{t.tier_key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="season:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_season_tier_edit_keyboard(tier_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Coins", callback_data=f"season:edit:{tier_key}:coins")],
            [InlineKeyboardButton(text="💵 Рубли", callback_data=f"season:edit:{tier_key}:rubles")],
            [InlineKeyboardButton(text="⬅️ К наградам", callback_data="season:tiers")],
        ]
    )


def build_season_reset_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, сбросить сезон", callback_data="season:reset_do")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="season:main")],
        ]
    )


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


def format_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


async def build_main_text() -> str:
    top = await get_current_top(10)
    if not top:
        top_block = "Игроков пока нет."
    else:
        top_block = "\n".join(f"{rank}. {nick} — {format_num(pts)}" for rank, nick, pts in top)
    return f"<b>🔄 Сезон</b>\n\n<b>Текущий топ-10:</b>\n{top_block}\n\nВыбери действие."


async def admin_guard(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


@router.message(F.text == SEASON_BUTTON_TEXT)
async def season_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await state.clear()
    await safe_delete_message(message)
    await message.answer(await build_main_text(), reply_markup=build_season_main_keyboard())


@router.callback_query(F.data == "season:main")
async def season_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    await edit_or_send(callback, await build_main_text(), reply_markup=build_season_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "season:tiers")
async def season_tiers(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    tiers = await get_tiers()
    lines = ["<b>🎁 Награды по местам</b>", ""]
    for t in tiers:
        extra = f" + 💵 {t.rubles}" if t.rubles else ""
        lines.append(f"{TIER_TITLES.get(t.tier_key, t.tier_key)}: 🪙 {format_num(t.coins)}{extra}")
    await edit_or_send(callback, "\n".join(lines), reply_markup=build_season_tiers_keyboard(tiers))
    await callback.answer()


@router.callback_query(F.data.startswith("season:tier:"))
async def season_tier(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    tier_key = callback.data.split(":")[-1] if callback.data else ""
    tiers = {t.tier_key: t for t in await get_tiers()}
    t = tiers.get(tier_key)
    if t is None:
        await season_tiers(callback, state)
        return
    text = f"<b>{TIER_TITLES.get(tier_key, tier_key)}</b>\n\n🪙 Coins: <b>{format_num(t.coins)}</b>\n💵 Рубли: <b>{t.rubles}</b>\n\nЧто изменить?"
    await edit_or_send(callback, text, reply_markup=build_season_tier_edit_keyboard(tier_key))
    await callback.answer()


@router.callback_query(F.data.startswith("season:edit:"))
async def season_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 4:
        await callback.answer()
        return
    tier_key, field = parts[2], parts[3]
    await state.set_state(SeasonTierStates.waiting_for_value)
    await state.update_data(tier_key=tier_key, field=field)
    label = "Coins" if field == "coins" else "Рубли"
    await edit_or_send(callback, f"Введи количество {label} для {TIER_TITLES.get(tier_key, tier_key)}.", reply_markup=build_season_tier_edit_keyboard(tier_key))
    await callback.answer()


@router.message(SeasonTierStates.waiting_for_value)
async def season_edit_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()
    tier_key = data.get("tier_key", "")
    field = data.get("field", "")
    if not raw.isdigit():
        await message.answer("Введи целое число.")
        return
    ok, msg = await update_tier_field(tier_key, field, int(raw))
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    tiers = await get_tiers()
    lines = ["<b>🎁 Награды по местам</b>", ""]
    for t in tiers:
        extra = f" + 💵 {t.rubles}" if t.rubles else ""
        lines.append(f"{TIER_TITLES.get(t.tier_key, t.tier_key)}: 🪙 {format_num(t.coins)}{extra}")
    await message.answer("\n".join(lines), reply_markup=build_season_tiers_keyboard(tiers))


@router.callback_query(F.data == "season:history")
async def season_history(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    seasons = await get_last_seasons(10)
    if not seasons:
        text = "<b>📜 История сезонов</b>\n\nСезоны ещё не завершались."
    else:
        lines = ["<b>📜 История сезонов</b>", ""]
        for s in seasons:
            lines.append(f"Сезон {s['number']}: {s['players_count']} игроков · {s['ended_at'][:10]}")
        text = "\n".join(lines)
    await edit_or_send(callback, text, reply_markup=build_season_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "season:reset_confirm")
async def season_reset_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    text = (
        "<b>⚠️ Сброс сезона</b>\n\n"
        "Будут выданы награды по итоговым местам, после чего <b>MMR всех игроков обнулится</b>, "
        "а лиги сбросятся до NCAA. Итоги сезона сохранятся в истории.\n\n"
        "Действие необратимо. Продолжить?"
    )
    await edit_or_send(callback, text, reply_markup=build_season_reset_confirm_keyboard())
    await callback.answer()


@router.callback_query(F.data == "season:reset_do")
async def season_reset_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    result = await reset_season()

    top_block = "\n".join(f"{r}. {n} — {format_num(p)}" for r, n, p in result.top) or "—"
    report = (
        f"<b>✅ Сезон {result.season_number - 1} завершён</b>\n\n"
        f"Игроков: <b>{result.players_count}</b>\n"
        f"Награждено: <b>{result.rewarded_count}</b>\n\n"
        f"<b>Топ по итогам:</b>\n{top_block}\n\n"
        f"MMR сброшен. Начался сезон {result.season_number}."
    )
    await edit_or_send(callback, report, reply_markup=build_season_main_keyboard())
    await callback.answer("Сезон сброшен")

    # уведомляем игроков о новом сезоне
    import asyncio
    for tg in await list_players_telegram_for_broadcast():
        try:
            await callback.bot.send_message(chat_id=tg, text=f"🏒 Начался новый сезон {result.season_number}! MMR обнулён — вперёд за новыми наградами.")
        except Exception:
            pass
        await asyncio.sleep(0.05)
