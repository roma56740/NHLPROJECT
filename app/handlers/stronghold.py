"""Пользовательские экраны THE STRONGHOLD.

Статичные тексты/иконки вынесены в app/texts/stronghold.py (конвенция проекта, см.
app/texts/quests.py и т.п.). Динамическая сборка экрана (клавиатуры, зависящие от
данных сервисов) остаётся здесь — полное разделение handlers/keyboards на отдельный
файл не делалось (см. docs/THE_STRONGHOLD_IMPLEMENTATION_REPORT.md, "Известные
ограничения": высокая связанность keyboard-builders с построением текста экрана
делает выигрыш от разделения небольшим относительно риска регрессий).
"""

from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.keyboards import stronghold as keyboards
from app.texts import stronghold as texts
from app.services.stronghold_common import StrongholdError, get_active_event
from app.services.stronghold_endless import get_leaderboard, get_status as get_endless_status, play_wave
from app.services.stronghold_fortress import get_fortress, list_fortresses, play_fortress_match
from app.services.stronghold_missions import claim_mission, list_missions
from app.services.stronghold_schedule import get_schedule_status
from app.services.stronghold_season_track import claim_level, get_track
from app.services.stronghold_store import list_products, purchase
from app.services.stronghold_upgrade import confirm_upgrade, ensure_starter_card, preview_upgrade
from app.services.stronghold_wallet import get_currency_history, get_wallet
from app.services.users import get_player_profile_by_telegram_id
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()

STRONGHOLD_BUTTON_TEXT = "🏰 THE STRONGHOLD"
STORE_CATEGORIES = ["Featured", "Packs", "Cards", "Resources", "Bundles"]
MISSION_TYPES = ["DAILY", "WEEKLY", "SEASONAL"]


def error_text(error: StrongholdError) -> str:
    return texts.error_text(error.code, error.message)


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


back_row = keyboards.back_row


def status_title(status: str) -> str:
    return texts.STATUS_TITLES.get(status, status)


async def _profile(callback_or_message) -> object | None:
    user = callback_or_message.from_user
    if user is None:
        return None
    return await get_player_profile_by_telegram_id(user.id)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

async def build_overview(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    event = await get_active_event()
    if event is None:
        return "🏰 <b>THE STRONGHOLD</b>\n\nСобытие сейчас недоступно.", InlineKeyboardMarkup(inline_keyboard=[])

    await ensure_starter_card(user_id)
    wallet = await get_wallet(user_id)
    fortresses = await list_fortresses(user_id)
    completed = sum(1 for f in fortresses if f.status == "COMPLETED")

    lines = [
        "🏰 <b>THE STRONGHOLD</b>",
        "",
        event.description,
        "",
        f"Статус: <b>{status_title(event.status)}</b>",
        f"🛡 Fortress Tokens: <b>{wallet.fortress_tokens}</b>",
        f"🪙 Coins: <b>{wallet.coins}</b>",
        f"🏯 Fortress пройдено: <b>{completed}/15</b>",
    ]
    if event.status == "GRACE_PERIOD":
        lines.append("")
        lines.append("⏳ Grace Period: доступны только Upgrade Chain и получение наград.")

    return "\n".join(lines), keyboards.build_overview_keyboard()


@router.message(F.text == STRONGHOLD_BUTTON_TEXT)
async def stronghold_button(message: Message) -> None:
    await safe_delete_message(message)
    if message.from_user is None:
        return
    if is_admin(message.from_user.id):
        from app.handlers.admin_stronghold import show_admin_dashboard_message
        await show_admin_dashboard_message(message)
        return

    profile = await get_player_profile_by_telegram_id(message.from_user.id)
    if profile is None:
        await message.answer("🏒 Открой игру через /start.")
        return
    text, keyboard = await build_overview(profile.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "stg:main")
async def stronghold_main_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    text, keyboard = await build_overview(profile.id)
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


# ---------------------------------------------------------------------------
# Upgrade Chain
# ---------------------------------------------------------------------------

async def build_upgrade_screen(user_id: int, state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    from app.database.db import get_connection

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT user_cards.id AS user_card_id, cards.name, cards.overall
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ? AND cards.player_key = 'miro-heiskanen'
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return "⚔️ <b>Upgrade Chain</b>\n\nКарта Miro Heiskanen пока не найдена.", InlineKeyboardMarkup(
            inline_keyboard=[back_row()]
        )

    user_card_id = int(row["user_card_id"])
    try:
        preview = await preview_upgrade(user_id, user_card_id)
    except StrongholdError as error:
        return f"⚔️ <b>Upgrade Chain</b>\n\n{error_text(error)}", InlineKeyboardMarkup(inline_keyboard=[back_row()])

    lines = [
        "⚔️ <b>Upgrade Chain: Miro Heiskanen</b>",
        "",
        f"Текущий уровень: <b>{preview.from_overall} OVR</b>",
        f"Следующий уровень: <b>{preview.to_overall} OVR</b>",
        "",
        f"Стоимость: <b>{preview.ft_cost} FT</b> + <b>{preview.coins_cost} Coins</b>",
        f"Ваш баланс: {preview.ft_balance} FT · {preview.coins_balance} Coins",
        f"Новая зарплата карты: {preview.new_salary}",
    ]
    if preview.salary_cap_warning:
        lines.append("⚠️ Апгрейд превысит зарплатный потолок THE STRONGHOLD (45 000 000).")
    if preview.blocking_reason:
        lines.append("")
        lines.append(f"❌ {texts.error_text(preview.blocking_reason, preview.blocking_reason)}")

    can_confirm = not preview.blocking_reason
    if can_confirm:
        request_id = str(uuid.uuid4())
        await state.update_data(stg_upgrade_request_id=request_id, stg_upgrade_user_card_id=user_card_id)
    return "\n".join(lines), keyboards.build_upgrade_keyboard(can_confirm=can_confirm)


@router.callback_query(F.data == "stg:upgrade")
async def stronghold_upgrade_screen(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    text, keyboard = await build_upgrade_screen(profile.id, state)
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "stg:upgrade:confirm")
async def stronghold_upgrade_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    data = await state.get_data()
    request_id = data.get("stg_upgrade_request_id")
    user_card_id = data.get("stg_upgrade_user_card_id")
    if not request_id or not user_card_id:
        await callback.answer("Экран устарел, откройте Upgrade Chain заново.", show_alert=True)
        return

    try:
        result = await confirm_upgrade(profile.id, int(user_card_id), str(request_id))
        await callback.answer(f"Апгрейд выполнен! Новый OVR: {result.to_overall}.", show_alert=True)
    except StrongholdError as error:
        await callback.answer(error_text(error), show_alert=True)

    await state.update_data(stg_upgrade_request_id=None, stg_upgrade_user_card_id=None)
    text, keyboard = await build_upgrade_screen(profile.id, state)
    await edit_or_send(callback, text, keyboard)


# ---------------------------------------------------------------------------
# Fortress
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "stg:fortress")
async def stronghold_fortress_list(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    fortresses = await list_fortresses(profile.id)
    lines = ["🏯 <b>Fortress</b>", "", "Каждая крепость — 6 матчей. Новая крепость открывается по единому расписанию для всех игроков."]

    unlocked_fortresses = [f for f in fortresses if f.status != "LOCKED"]
    all_unlocked_completed = bool(unlocked_fortresses) and all(f.status == "COMPLETED" for f in unlocked_fortresses)
    if all_unlocked_completed and len(unlocked_fortresses) < len(fortresses):
        event = await get_active_event()
        schedule = await get_schedule_status(event.id) if event is not None else None
        if schedule is not None and schedule.next_unlock_at is not None:
            from datetime import timezone as _tz

            from app.services.stronghold_common import utc_now

            remaining = schedule.next_unlock_at - utc_now().astimezone(_tz.utc)
            total_minutes = max(0, int(remaining.total_seconds() // 60))
            hours, minutes = divmod(total_minutes, 60)
            lines.append("")
            lines.append("✅ Все доступные башни пройдены.")
            lines.append("")
            lines.append(f"Следующая башня откроется: {schedule.next_unlock_at.strftime('%d.%m.%Y в %H:%M')} UTC")
            lines.append(f"Осталось: {hours} часов {minutes} минут")

    await edit_or_send(callback, "\n".join(lines), keyboards.build_fortress_list_keyboard(fortresses))
    await callback.answer()


@router.callback_query(F.data == "stg:fortress:locked")
async def stronghold_fortress_locked(callback: CallbackQuery) -> None:
    await callback.answer("Сначала пройдите предыдущий матч крепости.", show_alert=True)


@router.callback_query(F.data.startswith("stg:fortress:locked:"))
async def stronghold_fortress_locked_with_schedule(callback: CallbackQuery) -> None:
    """Закрытая по ГЛОБАЛЬНОМУ РАСПИСАНИЮ башня: не запускаем матч, не списываем
    попытку/валюту, не меняем прогресс — только показываем номер башни, дату/время
    открытия и оставшееся время (ТЗ "Если пользователь нажимает на закрытую башню")."""
    from app.services.stronghold_common import parse_db_datetime, utc_now
    from app.services.stronghold_fortress import list_fortresses

    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    try:
        fortress_id = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        await callback.answer("Крепость не найдена.", show_alert=True)
        return

    fortresses = await list_fortresses(profile.id)
    fortress = next((f for f in fortresses if f.id == fortress_id), None)
    if fortress is None:
        await callback.answer("Крепость не найдена.", show_alert=True)
        return

    if fortress.unlock_at is None:
        await callback.answer(f"Башня {fortress.order_index} ещё не открыта.", show_alert=True)
        return

    unlock_dt = parse_db_datetime(fortress.unlock_at)
    remaining_text = ""
    if unlock_dt is not None:
        remaining = unlock_dt - utc_now()
        total_minutes = max(0, int(remaining.total_seconds() // 60))
        hours, minutes = divmod(total_minutes, 60)
        remaining_text = f"\nОсталось: {hours} ч {minutes} мин"

    await callback.answer(
        f"Башня {fortress.order_index} ещё не открыта.\nОткроется: {fortress.unlock_at} UTC{remaining_text}",
        show_alert=True,
    )


async def _render_fortress_view(callback: CallbackQuery, user_id: int, fortress_id: int) -> None:
    fortress = await get_fortress(user_id, fortress_id)
    if fortress is None:
        await callback.answer("Крепость не найдена.", show_alert=True)
        return

    lines = [
        f"🏯 <b>{fortress.title}</b>",
        fortress.description,
        "",
        f"⭐ Звёзды: {fortress.stars_total}",
        f"🎁 Награда за первое прохождение: {fortress.first_completion_ft} FT",
    ]
    await edit_or_send(callback, "\n".join(lines), keyboards.build_fortress_view_keyboard(fortress))
    await callback.answer()


@router.callback_query(F.data.startswith("stg:fortress:view:"))
async def stronghold_fortress_view(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        fortress_id = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        await callback.answer("Крепость не найдена.", show_alert=True)
        return
    await _render_fortress_view(callback, profile.id, fortress_id)


@router.callback_query(F.data.startswith("stg:fortress:play:"))
async def stronghold_fortress_play(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None or callback.from_user is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        fortress_match_id = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        await callback.answer("Матч не найден.", show_alert=True)
        return

    try:
        result = await play_fortress_match(callback.from_user.id, profile.id, fortress_match_id)
    except StrongholdError as error:
        await callback.answer(error_text(error), show_alert=True)
        return

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    summary = f"{'🏆 Победа' if result.is_win else '💔 Поражение'} {result.user_score}:{result.opponent_score}"
    if result.stars:
        summary += f"\n⭐ Звёзды: {result.stars}"
    if result.ft_awarded:
        summary += f"\n🛡 +{result.ft_awarded} FT (первое прохождение крепости!)"
    if result.coins_awarded:
        summary += f"\n🪙 +{result.coins_awarded} Coins"
    await callback.answer(summary, show_alert=True)

    from app.database.db import get_connection
    with get_connection() as connection:
        row = connection.execute(
            "SELECT fortress_id FROM stronghold_fortress_matches WHERE id = ?", (fortress_match_id,)
        ).fetchone()
    if row is not None:
        await _render_fortress_view(callback, profile.id, int(row["fortress_id"]))


# ---------------------------------------------------------------------------
# Endless Siege
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "stg:endless")
async def stronghold_endless_screen(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    status = await get_endless_status(profile.id)
    lines = ["🌊 <b>Endless Siege</b>", ""]
    if not status.unlocked:
        lines.append("Открывается после прохождения всех 15 Fortress.")
    else:
        lines.append(f"Текущая волна: <b>{status.current_wave}</b>")
        lines.append(f"Лучшая волна: <b>{status.best_wave}</b>")
        lines.append(f"FT на этой неделе: <b>{status.weekly_ft_earned}/{status.weekly_ft_cap}</b>")
    await edit_or_send(callback, "\n".join(lines), keyboards.build_endless_keyboard(unlocked=status.unlocked))
    await callback.answer()


@router.callback_query(F.data == "stg:endless:play")
async def stronghold_endless_play(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None or callback.from_user is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        result = await play_wave(callback.from_user.id, profile.id)
    except StrongholdError as error:
        await callback.answer(error_text(error), show_alert=True)
        return

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    summary = f"{'🏆 Волна пройдена!' if result.is_win else '💔 Поражение'} {result.wave_number} (OVR {result.opponent_ovr})"
    if result.ft_awarded:
        summary += f"\n🛡 +{result.ft_awarded} FT"
    await callback.answer(summary, show_alert=True)
    await stronghold_endless_screen(callback)


@router.callback_query(F.data.startswith("stg:endless:leaderboard:"))
async def stronghold_endless_leaderboard(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    try:
        page = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        page = 1

    board = await get_leaderboard(page=page, user_id=profile.id if profile else None)
    lines = ["🏆 <b>Endless Siege — таблица лидеров</b>", ""]
    for row in board.rows:
        lines.append(f"{row.rank}. {row.nickname} — волна {row.best_wave}")
    if board.my_rank:
        lines.append("")
        lines.append(f"Ваше место: {board.my_rank}")
    await edit_or_send(callback, "\n".join(lines), keyboards.build_leaderboard_keyboard(board))
    await callback.answer()


# ---------------------------------------------------------------------------
# Missions
# ---------------------------------------------------------------------------

async def _render_missions(callback: CallbackQuery, user_id: int, mission_type: str) -> None:
    if mission_type not in MISSION_TYPES:
        mission_type = "DAILY"

    missions = await list_missions(user_id, mission_type)
    lines = [f"🎯 <b>Задания — {mission_type.title()}</b>", ""]
    for mission in missions:
        status_icon = texts.MISSION_STATUS_ICONS.get(mission.status, "")
        lines.append(f"{status_icon} {mission.title}: {mission.progress}/{mission.target_value}")
        reward_bits = []
        if mission.reward_ft:
            reward_bits.append(f"{mission.reward_ft} FT")
        if mission.reward_coins:
            reward_bits.append(f"{mission.reward_coins} Coins")
        lines.append(f"   Награда: {', '.join(reward_bits) if reward_bits else '—'}")

    await edit_or_send(callback, "\n".join(lines), keyboards.build_missions_keyboard(missions, mission_type, MISSION_TYPES))
    await callback.answer()


@router.callback_query(F.data.startswith("stg:missions:claim:"))
async def stronghold_missions_claim(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    try:
        mission_id = int(parts[3])
        mission_type = parts[4]
    except (IndexError, ValueError):
        await callback.answer("Задание не найдено.", show_alert=True)
        return

    try:
        result = await claim_mission(profile.id, mission_id)
        await callback.answer(f"Награда получена: {result.reward_ft} FT, {result.reward_coins} Coins.", show_alert=True)
    except StrongholdError as error:
        await callback.answer(error_text(error), show_alert=True)

    await _render_missions(callback, profile.id, mission_type)


@router.callback_query(F.data.startswith("stg:missions:") & ~F.data.startswith("stg:missions:claim:"))
async def stronghold_missions_screen(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    mission_type = (callback.data or "").split(":")[2]
    await _render_missions(callback, profile.id, mission_type)


# ---------------------------------------------------------------------------
# Season Track
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "stg:season")
async def stronghold_season_screen(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    track = await get_track(profile.id)
    lines = ["📈 <b>Season Track</b>", "", f"Event XP: <b>{track.xp}</b>"]
    for level in track.levels:
        icon = texts.SEASON_LEVEL_STATUS_ICONS.get(level.status, "")
        reward_bits = []
        if level.reward_ft:
            reward_bits.append(f"{level.reward_ft} FT")
        if level.reward_coins:
            reward_bits.append(f"{level.reward_coins} Coins")
        lines.append(f"{icon} Уровень {level.level} ({level.xp_threshold} XP): {', '.join(reward_bits) if reward_bits else '—'}")

    await edit_or_send(callback, "\n".join(lines), keyboards.build_season_track_keyboard(track))
    await callback.answer()


@router.callback_query(F.data.startswith("stg:season:claim:"))
async def stronghold_season_claim(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        level_id = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        await callback.answer("Уровень не найден.", show_alert=True)
        return

    try:
        result = await claim_level(profile.id, level_id)
        await callback.answer(f"Награда получена: {result.reward_ft} FT, {result.reward_coins} Coins.", show_alert=True)
    except StrongholdError as error:
        await callback.answer(error_text(error), show_alert=True)

    await stronghold_season_screen(callback)


# ---------------------------------------------------------------------------
# Event Store
# ---------------------------------------------------------------------------

async def _render_store(callback: CallbackQuery, user_id: int, category: str, state: FSMContext) -> None:
    if category not in STORE_CATEGORIES:
        category = "Featured"

    products = await list_products(user_id, category)
    lines = [f"🛒 <b>Магазин — {category}</b>", ""]
    for product in products:
        available_icon = "🟢" if product.available else "🔴"
        lines.append(f"{available_icon} <b>{product.title}</b> — {product.price_amount} {product.price_currency_code}")
        lines.append(f"   {product.description}")
        if product.available:
            request_id = str(uuid.uuid4())
            await state.update_data(**{f"stg_store_req_{product.id}": request_id})

    await edit_or_send(callback, "\n".join(lines), keyboards.build_store_keyboard(products, category, STORE_CATEGORIES))
    await callback.answer()


@router.callback_query(F.data.startswith("stg:store:buy:"))
async def stronghold_store_buy(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        product_id = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        await callback.answer("Товар не найден.", show_alert=True)
        return

    data = await state.get_data()
    request_id = data.get(f"stg_store_req_{product_id}")
    if not request_id:
        request_id = str(uuid.uuid4())

    category = "Featured"
    try:
        product_row = await list_products(profile.id)
        matching = next((p for p in product_row if p.id == product_id), None)
        if matching is not None:
            category = matching.category
        result = await purchase(profile.id, product_id, str(request_id))
        await callback.answer(f"Покупка успешна! Списано {result.price_amount} {result.price_currency_code}.", show_alert=True)
        await state.update_data(**{f"stg_store_req_{product_id}": None})
    except StrongholdError as error:
        await callback.answer(error_text(error), show_alert=True)
        return

    await _render_store(callback, profile.id, category, state)


@router.callback_query(F.data.startswith("stg:store:") & ~F.data.startswith("stg:store:buy:"))
async def stronghold_store_screen(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    category = (callback.data or "").split(":")[2]
    await _render_store(callback, profile.id, category, state)


# ---------------------------------------------------------------------------
# Wallet History (Currency Ledger)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("stg:wallet_history:"))
async def stronghold_wallet_history(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    event = await get_active_event()
    if event is None:
        await callback.answer("Событие недоступно.", show_alert=True)
        return
    try:
        page = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 1

    history = await get_currency_history(profile.id, event.id, page=page)
    lines = [f"📜 <b>История кошелька</b> (стр. {history.page}/{history.pages_count})", ""]
    if not history.entries:
        lines.append("Пока нет операций.")
    for entry in history.entries:
        icon = texts.CURRENCY_ICONS.get(entry.currency_code, "")
        sign = "+" if entry.delta > 0 else ""
        label = texts.LEDGER_REASON_LABELS.get(entry.reason, entry.reason)
        lines.append(f"{icon} {sign}{entry.delta} — {label} ({entry.created_at})")

    await edit_or_send(callback, "\n".join(lines), keyboards.build_wallet_history_keyboard(history))
    await callback.answer()
