from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.clan_seasons import (
    clan_rewards_are_configured,
    get_clan_reward_tiers,
    get_current_clan_top,
    get_last_clan_seasons,
    reset_clan_season,
    update_clan_reward_field,
)
from app.services.settings import get_setting
from app.utils.users import is_admin

router = Router()


class ClanSeasonStates(StatesGroup):
    waiting_for_value = State()
    waiting_for_reset_password = State()


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Награды топ-5 кланов", callback_data="clan_season:tiers")],
        [InlineKeyboardButton(text="📜 История", callback_data="clan_season:history")],
        [InlineKeyboardButton(text="⚠️ Сбросить клановый сезон", callback_data="clan_season:reset_confirm")],
        [InlineKeyboardButton(text="⬅️ К наградам", callback_data="admin_rewards:main")],
    ])


def tiers_kb(tiers) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{t.place} место", callback_data=f"clan_season:tier:{t.place}")] for t in tiers]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="clan_season:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tier_edit_kb(place: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 Coins", callback_data=f"clan_season:edit:{place}:coins")],
        [InlineKeyboardButton(text="💵 Рубли", callback_data=f"clan_season:edit:{place}:rubles")],
        [InlineKeyboardButton(text="🎁 ID пака", callback_data=f"clan_season:edit:{place}:pack_id")],
        [InlineKeyboardButton(text="⬅️ К топ-5", callback_data="clan_season:tiers")],
    ])


def reset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Сначала проверить/проставить награды", callback_data="clan_season:tiers")],
        [InlineKeyboardButton(text="🔐 Ввести пароль и сбросить", callback_data="clan_season:reset_do")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="clan_season:main")],
    ])


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    msg = callback.message
    if not isinstance(msg, Message):
        await callback.answer()
        return
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await msg.answer(text, reply_markup=reply_markup)


async def guard(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def main_text() -> str:
    top = await get_current_clan_top(10)
    block = "Кланов пока нет." if not top else "\n".join(f"{p}. {name} — {fmt(rating)} рейтинга · {wins} побед" for p, name, rating, wins in top)
    return f"<b>🏆 Клановый сезон</b>\n\n<b>Текущий топ-10 кланов:</b>\n{block}\n\nЗдесь настраиваются награды для топ-5 кланов и сброс кланового сезона."


@router.callback_query(F.data == "clan_season:main")
async def clan_season_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    await state.clear()
    await edit_or_send(callback, await main_text(), reply_markup=main_kb())
    await callback.answer()


@router.callback_query(F.data == "clan_season:tiers")
async def clan_season_tiers(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    await state.clear()
    tiers = await get_clan_reward_tiers()
    lines = ["<b>🎁 Награды топ-5 кланов</b>", "", "Каждое место редактируется отдельно. Награда выдаётся каждому участнику клана.", ""]
    for t in tiers:
        pack = f" + 🎁 пак ID {t.pack_id}" if t.pack_id else ""
        rubles = f" + 💵 {fmt(t.rubles)}" if t.rubles else ""
        lines.append(f"{t.place} место: 🪙 {fmt(t.coins)}{rubles}{pack}")
    await edit_or_send(callback, "\n".join(lines), reply_markup=tiers_kb(tiers))
    await callback.answer()


@router.callback_query(F.data.startswith("clan_season:tier:"))
async def clan_season_tier(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    await state.clear()
    place = int(callback.data.split(":")[-1])
    tiers = {t.place: t for t in await get_clan_reward_tiers()}
    t = tiers.get(place)
    if t is None:
        await clan_season_tiers(callback, state)
        return
    pack = f"{t.pack_id} — {t.pack_name}" if t.pack_id else "нет"
    text = f"<b>🎁 {place} место среди кланов</b>\n\n🪙 Coins: <b>{fmt(t.coins)}</b>\n💵 Рубли: <b>{fmt(t.rubles)}</b>\n🎁 Пак: <b>{pack}</b>\n\nЧто изменить?"
    await edit_or_send(callback, text, reply_markup=tier_edit_kb(place))
    await callback.answer()


@router.callback_query(F.data.startswith("clan_season:edit:"))
async def clan_season_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    _, _, raw_place, field = callback.data.split(":")
    place = int(raw_place)
    await state.set_state(ClanSeasonStates.waiting_for_value)
    await state.update_data(place=place, field=field)
    label = {"coins": "количество coins", "rubles": "количество рублей", "pack_id": "ID пака, 0 — убрать пак"}.get(field, field)
    await edit_or_send(callback, f"Введи {label} для {place} места.", reply_markup=tier_edit_kb(place))
    await callback.answer()


@router.message(ClanSeasonStates.waiting_for_value)
async def clan_season_edit_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи целое число.")
        return
    ok, msg = await update_clan_reward_field(int(data.get("place", 0)), str(data.get("field", "")), int(raw))
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    tiers = await get_clan_reward_tiers()
    await message.answer("Открываю награды топ-5 кланов.", reply_markup=tiers_kb(tiers))


@router.callback_query(F.data == "clan_season:history")
async def clan_season_history(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    await state.clear()
    seasons = await get_last_clan_seasons(10)
    if not seasons:
        text = "<b>📜 История клановых сезонов</b>\n\nКлановые сезоны ещё не завершались."
    else:
        lines = ["<b>📜 История клановых сезонов</b>", ""]
        for s in seasons:
            lines.append(f"Клановый сезон {s['number']}: {s['clans_count']} кланов · {s['ended_at'][:10]}")
        text = "\n".join(lines)
    await edit_or_send(callback, text, reply_markup=main_kb())
    await callback.answer()


@router.callback_query(F.data == "clan_season:reset_confirm")
async def clan_season_reset_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    await state.clear()
    tiers = await get_clan_reward_tiers()
    lines = [
        "<b>⚠️ Сброс кланового сезона</b>",
        "",
        "Перед сбросом обязательно проверь и проставь награды топ-5 кланов. Каждое место редактируется отдельно, награда выдаётся каждому участнику клана.",
        "",
        "<b>Текущие награды:</b>",
    ]
    for t in tiers:
        pack = f" + пак ID {t.pack_id}" if t.pack_id else ""
        lines.append(f"{t.place} место: 🪙 {fmt(t.coins)} · 💵 {fmt(t.rubles)}{pack}")
    lines.extend([
        "",
        "После подтверждения рейтинг, победы, активные атаки и вклад игроков будут сброшены.",
        "Для сброса нужен отдельный пароль главного админа."
    ])
    await edit_or_send(callback, "\n".join(lines), reply_markup=reset_kb())
    await callback.answer()


@router.callback_query(F.data == "clan_season:reset_do")
async def clan_season_reset_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await guard(callback):
        return
    if not await clan_rewards_are_configured():
        await callback.answer("Сначала проставь награды топ-5 кланов", show_alert=True)
        await clan_season_tiers(callback, state)
        return
    await state.set_state(ClanSeasonStates.waiting_for_reset_password)
    await edit_or_send(
        callback,
        "<b>🔐 Пароль сброса</b>\n\nВведи отдельный пароль главного админа для сброса кланового сезона.",
        reply_markup=reset_kb(),
    )
    await callback.answer()


@router.message(ClanSeasonStates.waiting_for_reset_password)
async def clan_season_reset_password(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    password = (message.text or "").strip()
    expected = await get_setting("clan_season_reset_password", "Ihbsn_3141592")
    if password != expected:
        await message.answer("❌ Неверный пароль сброса. Сезон не сброшен.")
        return
    await state.clear()
    result = await reset_clan_season(reset_by_telegram_id=message.from_user.id)
    top = "\n".join(f"{p}. {name} — {fmt(rating)} рейтинга · {wins} побед" for p, name, rating, wins in result.top) or "—"
    text = (
        f"<b>✅ Клановый сезон {result.season_number - 1} завершён</b>\n\n"
        f"Кланов: <b>{result.clans_count}</b>\n"
        f"Награждено мест: <b>{result.rewarded_count}</b>\n\n"
        f"<b>Топ-5:</b>\n{top}\n\n"
        f"Начался клановый сезон {result.season_number}."
    )
    await message.answer(text, reply_markup=main_kb())
