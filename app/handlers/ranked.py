"""RANKED MODE (v1) — игровой флоу: доступ (AHL+) -> мгновенный подбор соперника ->
матч (потолок зарплат 54M) -> рейтинг/лига/XP. Плюс косметика (включая привязку
CARD_FRAME к конкретной карте), Ranked Pack, Ranked Pass (Gold/Platinum, апгрейд).

Стиль — как app/handlers/war2.py (тексты/клавиатуры инлайн, один файл на весь флоу) —
тот же осознанный выбор ради единого обзора при таком количестве экранов."""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
from dataclasses import dataclass, replace

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services import match_guard, ranked_captain, ranked_core, ranked_cosmetics, ranked_packs, ranked_pass, ranked_shootout, war2_cosmetics
from app.services.audit_log import record_committed
from app.services.lineup import get_lineup_overview
from app.services.ranked_common import RankedError
from app.services.renders import render_lineup_image
from app.services.salary import RANKED_SALARY_CAP, format_salary_full
from app.services.war2_common import War2Error
from app.services.user_cards import get_player_cards_page
from app.services.users import get_player_profile_by_telegram_id
from app.texts.matches import build_match_goal_live_text, build_match_no_goal_live_text, build_match_playing_text
from app.utils.inline_navigation import suppress_auto_back_button
from app.utils.messages import safe_delete_message, safe_edit_message
from app.utils.users import is_admin

router = Router()
logger = logging.getLogger(__name__)

RANKED_MATCH_PLAYING_SECONDS = 60

RANKED_COSMETIC_TYPE_TITLES = {
    "NICK_BADGE": "🏷 Приставки",
    "PROFILE_BACKGROUND": "🏞 Фон профиля",
    "TITLE": "🎖 Титулы",
}

SHOOTOUT_CHOICE_SECONDS = 10
SHOOTOUT_RESULT_PAUSE_SECONDS = 1.2


@dataclass
class _ShootoutWaiter:
    telegram_id: int
    future: asyncio.Future[str]


_RANKED_SHOOTOUT_WAITERS: dict[str, _ShootoutWaiter] = {}


async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(callback.message, Message):
        await safe_edit_message(callback, text, reply_markup)
    else:
        await callback.answer()


def _back_row(callback_data: str = "ranked:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]


# ---------------------------------------------------------------------------
# Главный экран + матч
# ---------------------------------------------------------------------------

RANKED_BUTTON_TEXT = "🏆 Ranked Mode"


async def build_ranked_main_screen(telegram_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    """None — профиля нет (игрок не жал /start), вызывающий код сам решает, что показать."""
    profile = await get_player_profile_by_telegram_id(telegram_id)
    if profile is None:
        return None

    eligible = ranked_core.is_ranked_eligible(profile.league)
    season = await ranked_core.get_active_season()

    lines = ["<b>🏆 RANKED MODE</b>", ""]
    if not eligible:
        lines.append("Доступно с лиги AHL и выше. Твоя лига: " + profile.league)
    elif season is None:
        lines.append("Сезон сейчас не активен.")
    else:
        stats = await ranked_core.get_ranked_stats(profile.id, season.id)
        division = None
        if stats.ranked_league_id is not None:
            division = await ranked_core.compute_ranked_division(stats.rank_points)
        lines.append(f"Сезон #{season.season_number}, до {season.ends_at}")
        lines.append(f"Рейтинг: {stats.rank_points}" + (f" ({division.title})" if division else ""))
        lines.append(f"Победы/поражения: {stats.wins}/{stats.losses}")

    if eligible:
        lines.append("")
        lines.append(await _build_captain_block(profile.id))

    keyboard = []
    if eligible and season is not None:
        keyboard.append([InlineKeyboardButton(text="🏒 Играть Ranked", callback_data="ranked:play")])
    if eligible:
        keyboard.append([InlineKeyboardButton(text="🎖 Капитан состава", callback_data="ranked:captain")])
    keyboard.append([InlineKeyboardButton(text="📜 История матчей", callback_data="ranked:history")])
    keyboard.append([InlineKeyboardButton(text="🏆 Таблица лидеров", callback_data="ranked:leaderboard")])
    keyboard.append([InlineKeyboardButton(text="🎨 Косметика", callback_data="cosmetics:main")])
    keyboard.append([InlineKeyboardButton(text="📦 Ranked Packs", callback_data="ranked:packs")])
    keyboard.append([InlineKeyboardButton(text="🎫 Ranked Pass", callback_data="ranked:pass")])
    if is_admin(telegram_id):
        keyboard.append([InlineKeyboardButton(text="🛠 Админка Ranked", callback_data="admin_ranked:main")])
    keyboard.append(_back_row("community:main"))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


async def _build_captain_block(user_id: int) -> str:
    """Формат блока из ТЗ (раздел "ИНТЕРФЕЙС" системы капитанов)."""
    status = await ranked_captain.get_captain_status(user_id)
    if status.user_card_id is None:
        return "Капитан: не назначен\nБонус потолка: не активен"

    bonus_line = f"+{format_salary_full(status.bonus_amount)}" if status.bonus_active else "не активен"
    return "\n".join(
        [
            f"Капитан: {status.card_name}",
            f"Дивизион: {status.division_name or '—'}",
            f"Прогресс дивизиона: {status.division_count}/{status.required_count}",
            f"Бонус потолка: {bonus_line}",
            f"Текущий потолок: {format_salary_full(status.effective_cap)}",
        ]
    )


@router.callback_query(F.data == "ranked:captain")
async def ranked_captain_screen(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    status = await ranked_captain.get_captain_status(profile.id)
    text = "<b>🎖 Капитан Ranked-состава</b>\n\n" + await _build_captain_block(profile.id)
    if status.is_over_cap:
        text += (
            "\n\n⚠️ Состав превышает потолок зарплат: "
            f"{format_salary_full(status.salary_total)} из {format_salary_full(status.effective_cap)} "
            f"(превышение {format_salary_full(status.overage)}). "
            "Ranked-матч запустить нельзя, пока состав не приведён в порядок."
        )

    keyboard = []
    if status.user_card_id is not None:
        keyboard.append([InlineKeyboardButton(text="🔄 Сменить капитана", callback_data="ranked:captain_pick")])
        keyboard.append([InlineKeyboardButton(text="❌ Снять капитана", callback_data="ranked:captain_remove")])
    else:
        keyboard.append([InlineKeyboardButton(text="🎖 Назначить капитана", callback_data="ranked:captain_pick")])
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data == "ranked:captain_pick")
async def ranked_captain_pick(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    overview = await get_lineup_overview(profile.id)
    cards = [card for card in overview.slots.values() if card is not None]
    if not cards:
        await callback.answer("Сначала собери Ranked-состав (лайнап пуст).", show_alert=True)
        return

    text = "<b>🎖 Выбери карту-капитана</b>\n\nКапитаном можно назначить только карту из твоего текущего состава."
    keyboard = [
        [InlineKeyboardButton(text=f"{card.name} · {card.position} {card.overall}", callback_data=f"ranked:captain_set:{card.user_card_id}")]
        for card in cards
    ]
    keyboard.append(_back_row("ranked:captain"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("ranked:captain_set:"))
async def ranked_captain_set(callback: CallbackQuery) -> None:
    user_card_id_text = callback.data.split(":")[2]
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        user_card_id = int(user_card_id_text)
    except ValueError:
        await callback.answer("Некорректная карта.", show_alert=True)
        return

    try:
        status = await ranked_captain.assign_captain(profile.id, user_card_id)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return

    record_committed(
        profile.id,
        "ranked_captain_assign",
        entity_type="user_card",
        entity_id=user_card_id,
        details={"division_code": status.division_code, "division_count": status.division_count},
    )
    await callback.answer("Капитан назначен.")
    await ranked_captain_screen(callback)


@router.callback_query(F.data == "ranked:captain_remove")
async def ranked_captain_remove(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    status = await ranked_captain.get_captain_status(profile.id)
    if status.user_card_id is not None:
        await ranked_captain.remove_captain(profile.id)
        record_committed(
            profile.id,
            "ranked_captain_remove",
            entity_type="user_card",
            entity_id=status.user_card_id,
        )
    await callback.answer("Капитан снят.")
    await ranked_captain_screen(callback)


@router.callback_query(F.data == "ranked:main")
async def ranked_main(callback: CallbackQuery) -> None:
    screen = await build_ranked_main_screen(callback.from_user.id)
    if screen is None:
        await callback.answer("Открой игру через /start.", show_alert=True)
        return
    text, keyboard = screen
    await _edit_or_send(callback, text, keyboard)


@router.message(F.text == RANKED_BUTTON_TEXT)
async def ranked_button(message: Message) -> None:
    if message.from_user is None:
        return
    screen = await build_ranked_main_screen(message.from_user.id)
    if screen is None:
        await message.answer("🏆 Открой игру через /start.")
        return
    text, keyboard = screen
    await message.answer(text, reply_markup=keyboard)


async def _send_ranked_lineup_previews(callback: CallbackQuery, result, user_id: int) -> None:
    """Показывает состав игрока и состав соперника перед 60-секундной анимацией."""
    if callback.message is None or callback.bot is None:
        return
    chat_id = callback.message.chat.id
    try:
        own_overview = await get_lineup_overview(user_id)
        own_name = "Ты"
        own_background = None
        try:
            profile = await get_player_profile_by_telegram_id(callback.from_user.id)
            if profile is not None:
                own_name = await war2_cosmetics.get_display_nickname(profile.id, profile.nickname)
                own_background = await war2_cosmetics.get_equipped_background_path(profile.id)
        except Exception:
            pass
        own_cap = RANKED_SALARY_CAP
        try:
            own_cap = (await ranked_captain.get_captain_status(user_id)).effective_cap
        except Exception:
            pass
        own_render_overview = replace(own_overview, salary_cap=own_cap)
        own_image = render_lineup_image(
            own_render_overview, user_id, title=f"ТВОЙ СОСТАВ: {own_name}",
            background_override_path=own_background, show_salary_cap=True,
        )
        await callback.bot.send_photo(
            chat_id=chat_id, photo=FSInputFile(own_image),
            caption=f"<b>Твой состав</b>\n{own_name}\nOVR: <b>{own_overview.average_overall or '—'}</b> (+{own_overview.chemistry_bonus})",
        )
        await asyncio.sleep(0.7)

        if result.opponent_bot_overview is not None:
            overview = result.opponent_bot_overview
        elif result.opponent_user_id is not None:
            overview = await get_lineup_overview(result.opponent_user_id)
        else:
            return
        opponent_name = result.opponent_name
        background_path = None
        if result.opponent_user_id is not None:
            try:
                opponent_name = await war2_cosmetics.get_display_nickname(result.opponent_user_id, result.opponent_name)
                background_path = await war2_cosmetics.get_equipped_background_path(result.opponent_user_id)
            except Exception:
                pass
        opponent_cap = RANKED_SALARY_CAP
        if result.opponent_user_id is not None:
            try:
                opponent_cap = (await ranked_captain.get_captain_status(result.opponent_user_id)).effective_cap
            except Exception:
                pass
        opponent_render_overview = replace(overview, salary_cap=opponent_cap)
        image_path = render_lineup_image(
            opponent_render_overview, result.opponent_user_id or 0,
            title=f"СОСТАВ СОПЕРНИКА: {opponent_name}",
            background_override_path=background_path, show_salary_cap=True,
        )
        await callback.bot.send_photo(
            chat_id=chat_id, photo=FSInputFile(image_path),
            caption=f"<b>Состав соперника</b>\n{opponent_name}\nOVR: <b>{overview.average_overall or '—'}</b> (+{overview.chemistry_bonus})",
        )
    except Exception as error:
        logger.exception("Failed to render Ranked lineups: %s", error)


def _build_ranked_goal_timeline(result) -> list[tuple[str, object | None]]:
    goal_events = [event for event in (result.events or []) if event.event_type == "GOAL"]
    user_left = max(0, result.user_score)
    opponent_left = max(0, result.opponent_score)
    timeline: list[tuple[str, object | None]] = []
    for event in goal_events:
        description = event.description.strip()
        opponent_goal = description.startswith(f"{result.opponent_name} ")
        if opponent_goal and opponent_left > 0:
            timeline.append(("opponent", event)); opponent_left -= 1
        elif user_left > 0:
            timeline.append(("user", event)); user_left -= 1
        elif opponent_left > 0:
            timeline.append(("opponent", event)); opponent_left -= 1
    timeline.extend(("user", None) for _ in range(user_left))
    timeline.extend(("opponent", None) for _ in range(opponent_left))
    return timeline


async def _edit_ranked_animation_message(bot, chat_id: int, message_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def _show_ranked_live_match(bot, chat_id: int, message_id: int, result) -> None:
    timeline = _build_ranked_goal_timeline(result)
    if not timeline:
        await _edit_ranked_animation_message(bot, chat_id, message_id, build_match_no_goal_live_text(result))
        await asyncio.sleep(RANKED_MATCH_PLAYING_SECONDS)
        return
    user_score = 0
    opponent_score = 0
    interval = RANKED_MATCH_PLAYING_SECONDS / (len(timeline) + 1)
    for side, event in timeline:
        await asyncio.sleep(interval)
        if side == "user": user_score += 1
        else: opponent_score += 1
        await _edit_ranked_animation_message(
            bot, chat_id, message_id,
            build_match_goal_live_text(result, event=event, user_score=user_score, opponent_score=opponent_score, scorer_side=side),
        )
    await asyncio.sleep(interval)


def _shootout_keyboard(token: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=ranked_shootout.CORNER_TITLES["TL"],
                callback_data=f"ranked:shootout:{token}:TL",
            ),
            InlineKeyboardButton(
                text=ranked_shootout.CORNER_TITLES["TR"],
                callback_data=f"ranked:shootout:{token}:TR",
            ),
        ],
        [
            InlineKeyboardButton(
                text=ranked_shootout.CORNER_TITLES["BL"],
                callback_data=f"ranked:shootout:{token}:BL",
            ),
            InlineKeyboardButton(
                text=ranked_shootout.CORNER_TITLES["BR"],
                callback_data=f"ranked:shootout:{token}:BR",
            ),
        ],
    ]
    # During a live 10-second choice a universal "Back" button would allow the
    # player to abandon the match while MatchGuard is active, so it is explicitly
    # suppressed only for these four-button keyboards.
    with suppress_auto_back_button():
        return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ranked:shootout:"))
async def ranked_shootout_corner(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Некорректный выбор.", show_alert=True)
        return
    token, corner = parts[2], parts[3].upper()
    waiter = _RANKED_SHOOTOUT_WAITERS.get(token)
    if waiter is None or waiter.future.done():
        await callback.answer("Время на этот буллит уже истекло.", show_alert=True)
        return
    if callback.from_user.id != waiter.telegram_id:
        await callback.answer("Это не твой буллит.", show_alert=True)
        return
    if corner not in ranked_shootout.CORNERS:
        await callback.answer("Некорректный угол.", show_alert=True)
        return
    waiter.future.set_result(corner)
    await callback.answer("Угол выбран")


async def _wait_for_shootout_corner(
    bot,
    *,
    chat_id: int,
    message_id: int,
    telegram_id: int,
    text: str,
) -> str | None:
    token = secrets.token_hex(5)
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    _RANKED_SHOOTOUT_WAITERS[token] = _ShootoutWaiter(telegram_id=telegram_id, future=future)
    try:
        await _edit_ranked_animation_message(
            bot,
            chat_id,
            message_id,
            text,
            _shootout_keyboard(token),
        )
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=SHOOTOUT_CHOICE_SECONDS)
        except asyncio.TimeoutError:
            return None
    finally:
        _RANKED_SHOOTOUT_WAITERS.pop(token, None)
        if not future.done():
            future.cancel()


def _shootout_score_text(result, user_goals: int, opponent_goals: int, round_title: str) -> str:
    return (
        "<b>🎯 СЕРИЯ БУЛЛИТОВ</b>\n\n"
        f"После матча: <b>{result.user_score}:{result.opponent_score}</b>\n"
        f"Буллиты: <b>{user_goals}:{opponent_goals}</b>\n"
        f"Соперник: {result.opponent_name}\n\n"
        f"{round_title}"
    )


def _shootout_outcome_text(outcome: ranked_shootout.ShootoutAttemptResult) -> str:
    if outcome.reason == "shooter_timeout":
        return "⏱ Бросающий не выбрал угол — броска нет."
    if outcome.reason == "goalie_timeout":
        return "🥅 Вратарь не выбрал угол — гол."
    if outcome.reason == "save":
        return "🧤 Вратарь угадал угол — сейв."
    return "🥅 Углы не совпали — гол."


async def _show_shootout_attempt_result(
    bot,
    *,
    chat_id: int,
    message_id: int,
    result,
    user_goals: int,
    opponent_goals: int,
    title: str,
    outcome: ranked_shootout.ShootoutAttemptResult,
) -> None:
    detail = _shootout_outcome_text(outcome)
    if outcome.shooter_corner is not None:
        detail += f"\nБросок: {ranked_shootout.corner_title(outcome.shooter_corner)}"
    if outcome.goalie_corner is not None:
        detail += f"\nЗащита: {ranked_shootout.corner_title(outcome.goalie_corner)}"
    await _edit_ranked_animation_message(
        bot,
        chat_id,
        message_id,
        _shootout_score_text(result, user_goals, opponent_goals, f"{title}\n\n{detail}"),
        None,
    )
    await asyncio.sleep(SHOOTOUT_RESULT_PAUSE_SECONDS)


async def _run_ranked_shootout(
    bot,
    *,
    chat_id: int,
    message_id: int,
    telegram_id: int,
    result,
) -> tuple[bool, int, int, list[dict[str, object]]]:
    """Play three pairs of attempts, then sudden death until the score differs.

    Ranked matchmaking is currently asynchronous: the selected opponent is a
    roster/ratings opponent rather than a second live Telegram session.  The
    initiating player therefore controls their own shooter and goalie, while the
    opponent's shot/defence corners are selected by the match engine.
    """
    user_goals = 0
    opponent_goals = 0
    user_attempts = 0
    opponent_attempts = 0
    log: list[dict[str, object]] = []

    async def user_shoot(round_title: str, round_number: int) -> None:
        nonlocal user_goals, user_attempts
        goalie_corner = random.choice(ranked_shootout.CORNERS)
        shooter_corner = await _wait_for_shootout_corner(
            bot,
            chat_id=chat_id,
            message_id=message_id,
            telegram_id=telegram_id,
            text=_shootout_score_text(
                result,
                user_goals,
                opponent_goals,
                f"{round_title}\n\n🏒 Ты бросаешь. Выбери угол за {SHOOTOUT_CHOICE_SECONDS} секунд.",
            ),
        )
        outcome = ranked_shootout.resolve_attempt(shooter_corner, goalie_corner)
        user_attempts += 1
        if outcome.is_goal:
            user_goals += 1
        log.append(
            {
                "round": round_number,
                "phase": "user_shoots",
                "shooter_corner": outcome.shooter_corner,
                "goalie_corner": outcome.goalie_corner,
                "goal": outcome.is_goal,
                "reason": outcome.reason,
            }
        )
        await _show_shootout_attempt_result(
            bot,
            chat_id=chat_id,
            message_id=message_id,
            result=result,
            user_goals=user_goals,
            opponent_goals=opponent_goals,
            title=f"{round_title}: твой бросок",
            outcome=outcome,
        )

    async def user_defends(round_title: str, round_number: int) -> None:
        nonlocal opponent_goals, opponent_attempts
        shooter_corner = random.choice(ranked_shootout.CORNERS)
        goalie_corner = await _wait_for_shootout_corner(
            bot,
            chat_id=chat_id,
            message_id=message_id,
            telegram_id=telegram_id,
            text=_shootout_score_text(
                result,
                user_goals,
                opponent_goals,
                f"{round_title}\n\n🧤 Ты вратарь. Выбери угол защиты за {SHOOTOUT_CHOICE_SECONDS} секунд.",
            ),
        )
        outcome = ranked_shootout.resolve_attempt(shooter_corner, goalie_corner)
        opponent_attempts += 1
        if outcome.is_goal:
            opponent_goals += 1
        log.append(
            {
                "round": round_number,
                "phase": "user_defends",
                "shooter_corner": outcome.shooter_corner,
                "goalie_corner": outcome.goalie_corner,
                "goal": outcome.is_goal,
                "reason": outcome.reason,
            }
        )
        await _show_shootout_attempt_result(
            bot,
            chat_id=chat_id,
            message_id=message_id,
            result=result,
            user_goals=user_goals,
            opponent_goals=opponent_goals,
            title=f"{round_title}: бросок соперника",
            outcome=outcome,
        )

    for round_number in range(1, 4):
        title = f"Раунд {round_number}/3"
        await user_shoot(title, round_number)
        if ranked_shootout.is_regulation_clinched(
            user_goals, opponent_goals, user_attempts, opponent_attempts
        ):
            break
        await user_defends(title, round_number)
        if ranked_shootout.is_regulation_clinched(
            user_goals, opponent_goals, user_attempts, opponent_attempts
        ):
            break

    sudden_round = 0
    while user_goals == opponent_goals:
        sudden_round += 1
        title = f"Внезапная смерть · раунд {sudden_round}"
        await user_shoot(title, 3 + sudden_round)
        await user_defends(title, 3 + sudden_round)

    return user_goals > opponent_goals, user_goals, opponent_goals, log


def _build_ranked_result_text(result) -> str:
    icon = "🏆" if result.result == "win" else "💔"
    lines = [
        f"<b>{icon} {result.user_score}:{result.opponent_score}</b>", "",
        f"Результат: {'Победа' if result.result == 'win' else 'Поражение'}",
        f"Рейтинг: {'+' if result.rank_delta >= 0 else ''}{result.rank_delta}",
        f"MVP: {result.mvp_title}",
    ]
    if result.is_shootout:
        lines.append(
            f"🎯 Буллиты: {result.shootout_user_goals}:{result.shootout_opponent_goals}."
        )
    elif result.is_overtime: lines.append("⏱ Матч завершился в овертайме.")
    if result.new_league is not None: lines.append(f"Лига: {result.new_league.title}")
    if result.league_up: lines.append("🎉 Новая лига! Награда начислена.")
    return "\n".join(lines)


async def _replace_with_ranked_playing(callback: CallbackQuery, result) -> Message | None:
    if not isinstance(callback.message, Message):
        return None
    text = build_match_playing_text(result.opponent_name, result.opponent_type)
    message = callback.message
    try:
        if message.photo:
            await safe_delete_message(message)
            return await callback.bot.send_message(chat_id=message.chat.id, text=text)
        await message.edit_text(text)
        return message
    except TelegramBadRequest:
        return await callback.bot.send_message(chat_id=message.chat.id, text=text)


@router.callback_query(F.data == "ranked:play")
async def ranked_play(callback: CallbackQuery) -> None:
    try:
        result = await ranked_core.play_ranked_match(callback.from_user.id, interactive_shootout=True)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return

    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer("Профиль не найден.", show_alert=True)
        return

    animation_lock = None
    shootout_finalized = False
    if not result.pending_shootout:
        animation_lock = await match_guard.acquire_player_match_lock(
            profile.id,
            "ranked",
            request_id=f"ranked-animation:{result.match_id}",
            ttl_seconds=180,
        )
        if animation_lock.acquired and animation_lock.lock_id is not None:
            await match_guard.bind_lock_to_match(animation_lock.lock_id, result.match_id)
    else:
        # The original Ranked lock from play_ranked_match remains active until the
        # mini-game commits the real winner.
        await match_guard.heartbeat_lock(profile.id, extend_seconds=900)

    try:
        await _send_ranked_lineup_previews(callback, result, profile.id)
        animation_message = await _replace_with_ranked_playing(callback, result)
        if animation_message is None:
            return
        await _show_ranked_live_match(
            callback.bot, animation_message.chat.id, animation_message.message_id, result
        )

        if result.pending_shootout:
            user_won, user_so, opponent_so, shootout_log = await _run_ranked_shootout(
                callback.bot,
                chat_id=animation_message.chat.id,
                message_id=animation_message.message_id,
                telegram_id=callback.from_user.id,
                result=result,
            )
            result = await ranked_core.finalize_ranked_shootout(
                result,
                user_won=user_won,
                shootout_user_goals=user_so,
                shootout_opponent_goals=opponent_so,
                shootout_log=shootout_log,
            )
            shootout_finalized = True

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏒 Ещё матч", callback_data="ranked:play")],
                _back_row(),
            ]
        )
        await _edit_ranked_animation_message(
            callback.bot,
            animation_message.chat.id,
            animation_message.message_id,
            _build_ranked_result_text(result),
            keyboard,
        )
    finally:
        if result.pending_shootout and not shootout_finalized:
            await match_guard.cancel_match(profile.id, reason="RANKED_SHOOTOUT_INTERRUPTED")
        elif animation_lock is not None and animation_lock.acquired:
            await match_guard.finalize_match(
                profile.id,
                match_id=result.match_id,
                reason="RANKED_ANIMATION_COMPLETED",
            )


@router.callback_query(F.data == "ranked:history")
async def ranked_history(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    items = await ranked_core.get_match_history(profile.id)
    if not items:
        text = "<b>📜 История матчей</b>\n\nПока нет сыгранных Ranked-матчей."
    else:
        lines = ["<b>📜 История матчей</b>", ""]
        for item in items:
            icon = "🏆" if item.result == "win" else "💔"
            sign = "+" if item.rank_delta >= 0 else ""
            lines.append(f"{icon} {item.user_score}:{item.opponent_score} vs {item.opponent_name} ({sign}{item.rank_delta})")
        text = "\n".join(lines)
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=[_back_row()]))


@router.callback_query(F.data == "ranked:leaderboard")
async def ranked_leaderboard(callback: CallbackQuery) -> None:
    season = await ranked_core.get_active_season()
    if season is None:
        await _edit_or_send(callback, "<b>🏆 Таблица лидеров</b>\n\nСезон не активен.", InlineKeyboardMarkup(inline_keyboard=[_back_row()]))
        return
    rows = await ranked_core.get_ranked_leaderboard(season.id)
    lines = ["<b>🏆 Таблица лидеров</b>", ""]
    for index, row in enumerate(rows, 1):
        league_title = row["league_title"] or "—"
        lines.append(f"{index}. {row['nickname']} — {row['rank_points']} ({league_title})")
    if not rows:
        lines.append("Пока никто не сыграл в этом сезоне.")
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[_back_row()]))


# ---------------------------------------------------------------------------
# Косметика (NICK_BADGE/PROFILE_BACKGROUND/TITLE — глобальная экипировка, общий
# каталог с CLAN WAR 2.0 через app.services.war2_cosmetics)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("ranked:cosmetics:"))
async def ranked_cosmetics_list(callback: CallbackQuery) -> None:
    cosmetic_type = callback.data.split(":")[2]
    await _render_cosmetics_list(callback, cosmetic_type)


async def _render_cosmetics_list(callback: CallbackQuery, cosmetic_type: str) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    items = await war2_cosmetics.get_user_cosmetics_page(profile.id, cosmetic_type)
    title = RANKED_COSMETIC_TYPE_TITLES.get(cosmetic_type, cosmetic_type)
    text = f"<b>{title}</b>\n\n" + ("У тебя пока нет таких предметов." if not items else "Выбери, что экипировать:")

    keyboard = []
    for item in items:
        mark = "✅ " if item.equipped else ""
        label = f"{mark}{item.title}" + (f" [{item.badge_text}]" if item.badge_text else "")
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"ranked:eq:{item.id}:{cosmetic_type}")])

    type_row = [
        InlineKeyboardButton(text=("• " if code == cosmetic_type else "") + label, callback_data=f"ranked:cosmetics:{code}")
        for code, label in RANKED_COSMETIC_TYPE_TITLES.items()
    ]
    keyboard.append(type_row)
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("ranked:eq:"))
async def ranked_cosmetics_equip(callback: CallbackQuery) -> None:
    _, _, owned_id_text, cosmetic_type = callback.data.split(":")
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        await war2_cosmetics.equip_cosmetic(profile.id, int(owned_id_text))
    except War2Error as error:
        # war2_cosmetics.equip_cosmetic() — общий каталог, унаследованный от CLAN WAR
        # 2.0 (см. app/services/war2_cosmetics.py) — бросает War2Error, не RankedError;
        # оба имеют одинаковую форму (code/message), ловим оба явно, не глотаем молча.
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Экипировано.")
    await _render_cosmetics_list(callback, cosmetic_type)


# ---------------------------------------------------------------------------
# CARD_FRAME — привязка к конкретной карте (раздел RANK REWARDS ТЗ)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ranked:frames")
async def ranked_frames_list(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    items = await ranked_cosmetics.list_owned_card_frames(profile.id)
    text = "<b>🖼 Рамки для карт</b>\n\n" + ("У тебя пока нет рамок." if not items else "Выбери рамку, чтобы привязать её к карте:")
    keyboard = []
    for item in items:
        mark = "✅ " if item["bound_card_id"] else ""
        keyboard.append([InlineKeyboardButton(text=f"{mark}{item['title']}", callback_data=f"ranked:frame_pick:{item['owned_id']}")])
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("ranked:frame_pick:"))
async def ranked_frame_pick(callback: CallbackQuery) -> None:
    owned_id = int(callback.data.split(":")[2])
    await _render_frame_card_page(callback, owned_id, 1)


async def _render_frame_card_page(callback: CallbackQuery, owned_id: int, page: int) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    cards_page = await get_player_cards_page(profile.id, page=page, per_page=5)
    text = f"<b>🖼 На какую карту надеть рамку?</b> (стр. {cards_page.page}/{cards_page.pages_count})"
    keyboard = [
        [InlineKeyboardButton(text=f"{card.name} · {card.position} {card.overall}", callback_data=f"ranked:frame_apply:{owned_id}:{card.id}")]
        for card in cards_page.cards
    ]
    nav_row = []
    if cards_page.page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"ranked:frame_page:{owned_id}:{cards_page.page - 1}"))
    if cards_page.page < cards_page.pages_count:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"ranked:frame_page:{owned_id}:{cards_page.page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append(_back_row("ranked:frames"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("ranked:frame_page:"))
async def ranked_frame_page(callback: CallbackQuery) -> None:
    _, _, owned_id_text, page_text = callback.data.split(":")
    await _render_frame_card_page(callback, int(owned_id_text), int(page_text))


@router.callback_query(F.data.startswith("ranked:frame_apply:"))
async def ranked_frame_apply(callback: CallbackQuery) -> None:
    _, _, owned_id_text, user_card_id_text = callback.data.split(":")
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        await ranked_cosmetics.bind_frame_to_card(profile.id, int(owned_id_text), int(user_card_id_text))
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Рамка привязана к карте.")
    await ranked_frames_list(callback)


# ---------------------------------------------------------------------------
# Ranked Packs
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ranked:packs")
async def ranked_packs_list(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    from app.database.db import get_connection

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT ranked_packs.id, ranked_packs.name, user_ranked_packs.quantity
            FROM user_ranked_packs
            JOIN ranked_packs ON ranked_packs.id = user_ranked_packs.pack_id
            WHERE user_ranked_packs.user_id = ? AND user_ranked_packs.quantity > 0
            """,
            (profile.id,),
        ).fetchall()

    text = "<b>📦 Ranked Packs</b>\n\n" + ("У тебя пока нет паков." if not rows else "Выбери пак, чтобы открыть:")
    keyboard = [
        [InlineKeyboardButton(text=f"{row['name']} ({row['quantity']})", callback_data=f"ranked:pack_open:{row['id']}")]
        for row in rows
    ]
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("ranked:pack_open:"))
async def ranked_pack_open(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[2])
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        result = await ranked_packs.open_ranked_pack(profile.id, pack_id)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return

    lines = [f"<b>📦 {result.pack_code}</b>", ""]
    for reward in result.rewards:
        if reward.reward_type == "card":
            lines.append(f"🃏 {reward.title}")
        elif reward.reward_type == "currency":
            lines.append(f"💰 {reward.title}: {reward.amount}")
        elif reward.reward_type == "xp":
            lines.append(f"⭐ Ranked XP: {reward.amount}")
        else:
            lines.append(f"🎁 {reward.title}")
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[_back_row("ranked:packs")]))


# ---------------------------------------------------------------------------
# Ranked Pass
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ranked:pass")
async def ranked_pass_main(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    active_pass = await ranked_pass.get_active_pass()
    if active_pass is None:
        await _edit_or_send(callback, "<b>🎫 Ranked Pass</b>\n\nПропуск ещё не создан администрацией.", InlineKeyboardMarkup(inline_keyboard=[_back_row()]))
        return

    state = await ranked_pass.get_user_pass_state(profile.id, active_pass.id)
    track = "Platinum" if state.platinum_unlocked else ("Gold" if state.gold_unlocked else "Free")
    lines = [
        f"<b>🎫 {active_pass.title}</b>",
        "",
        f"Уровень: {state.level}/{active_pass.levels_count}",
        f"XP: {state.xp}",
        f"Линия: {track}",
    ]
    keyboard = [
        [InlineKeyboardButton(text="🎁 Free-награды", callback_data=f"ranked:pass_rewards:{active_pass.id}:free")],
        [InlineKeyboardButton(text="🥇 Gold-награды", callback_data=f"ranked:pass_rewards:{active_pass.id}:gold")],
        [InlineKeyboardButton(text="💠 Platinum-награды", callback_data=f"ranked:pass_rewards:{active_pass.id}:platinum")],
    ]
    if not state.gold_unlocked:
        keyboard.append([InlineKeyboardButton(text="💳 Купить Gold Pass", callback_data=f"ranked:pass_buy_gold:{active_pass.id}")])
    elif not state.platinum_unlocked:
        keyboard.append([InlineKeyboardButton(text="⬆️ Апгрейд до Platinum", callback_data=f"ranked:pass_upgrade:{active_pass.id}")])
    keyboard.append(_back_row())
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("ranked:pass_rewards:"))
async def ranked_pass_rewards(callback: CallbackQuery) -> None:
    _, _, pass_id_text, track = callback.data.split(":")
    pass_id = int(pass_id_text)
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    from app.database.db import get_connection

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM ranked_pass_rewards WHERE pass_id = ? AND track = ? AND active = 1 ORDER BY level",
            (pass_id, track),
        ).fetchall()
        claimed_ids = {
            row["reward_id"]
            for row in connection.execute(
                "SELECT reward_id FROM user_ranked_pass_rewards WHERE user_id = ?", (profile.id,)
            ).fetchall()
        }

    state = await ranked_pass.get_user_pass_state(profile.id, pass_id)
    text = f"<b>🎁 Награды ({track})</b>\n\nТвой уровень: {state.level}"
    keyboard = []
    for row in rows:
        claimed = row["id"] in claimed_ids
        reached = int(row["level"]) <= state.level
        label = f"Ур. {row['level']}: {row['title'] or row['reward_type']}"
        if claimed:
            label = "✅ " + label
        elif not reached:
            label = "🔒 " + label
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"ranked:pass_claim:{row['id']}" if reached and not claimed else "ranked:noop")])
    keyboard.append(_back_row("ranked:pass"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data == "ranked:noop")
async def ranked_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("ranked:pass_claim:"))
async def ranked_pass_claim(callback: CallbackQuery) -> None:
    reward_id = int(callback.data.split(":")[2])
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        await ranked_pass.claim_reward(profile.id, reward_id)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Награда получена!")
    await ranked_pass_main(callback)


@router.callback_query(F.data.startswith("ranked:pass_buy_gold:"))
async def ranked_pass_buy_gold(callback: CallbackQuery) -> None:
    pass_id = int(callback.data.split(":")[2])
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        await ranked_pass.purchase_gold(profile.id, pass_id)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Gold Pass куплен!")
    await ranked_pass_main(callback)


@router.callback_query(F.data.startswith("ranked:pass_upgrade:"))
async def ranked_pass_upgrade(callback: CallbackQuery) -> None:
    pass_id = int(callback.data.split(":")[2])
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        granted = await ranked_pass.upgrade_gold_to_platinum(profile.id, pass_id)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer(f"Platinum Pass куплен! Выдано наград: {granted}.", show_alert=True)
    await ranked_pass_main(callback)
