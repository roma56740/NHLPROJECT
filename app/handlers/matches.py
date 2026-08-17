import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.matches import (
    build_active_match_blocked_keyboard,
    build_match_captcha_keyboard,
    MATCH_HISTORY_PER_PAGE,
    build_match_details_keyboard,
    build_match_history_keyboard,
    build_match_not_ready_keyboard,
    build_match_result_keyboard,
    build_match_search_keyboard,
    build_matches_main_keyboard,
)
from app.services.lineup import get_lineup_overview
from app.services.cache_cleanup import remove_render_cache_file
from app.services.renders import render_lineup_image, render_opponent_lineup_placeholder
from app.services.matches import (
    MatchPlayResult,
    cancel_match_search,
    enter_matchmaking,
    finish_waiting_search_with_bot,
    finish_waiting_search_with_bot_by_queue_id,
    get_expired_match_queue_items,
    get_match_details,
    get_match_history_page,
    get_match_main_info,
)
from app.services.community import get_user_id_by_telegram_id
from app.services import match_guard
from app.services.match_guard import (
    CAPTCHA_TTL_SECONDS,
    generate_captcha,
    has_active_match,
    release_match_lock,
    try_acquire_match_lock,
    utc_now,
)
from app.services.users import get_player_profile_by_telegram_id
from app.texts.matches import (
    build_match_captcha_text,
    MATCH_ALREADY_SEARCHING_TEXT,
    MATCH_CANCELLED_TEXT,
    MATCH_SEARCH_TEXT,
    build_match_details_text,
    build_match_goal_live_text,
    build_match_history_text,
    build_match_main_text,
    build_match_no_goal_live_text,
    build_match_not_ready_text,
    build_match_playing_text,
    build_match_queue_fallback_text,
    build_match_result_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()
logger = logging.getLogger(__name__)

MATCHES_BUTTON_TEXT = "🏒 Играть"
MATCH_PLAYING_SECONDS = 15
MATCH_QUEUE_WATCHER_INTERVAL_SECONDS = 3

background_tasks: set[asyncio.Task] = set()
match_queue_watcher_task: asyncio.Task | None = None


def track_background_task(task: asyncio.Task) -> None:
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


def start_match_queue_watcher(bot) -> None:
    global match_queue_watcher_task

    if match_queue_watcher_task is not None and not match_queue_watcher_task.done():
        return

    match_queue_watcher_task = asyncio.create_task(run_match_queue_watcher(bot))
    track_background_task(match_queue_watcher_task)


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    start_match_queue_watcher(callback.bot)

    try:
        if message.photo:
            await message.delete()
            await callback.bot.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=reply_markup,
            )
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
        )


async def edit_stored_message(bot, chat_id: int, message_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def _equipped_war2_cosmetics(user_id: int) -> tuple[str | None, str | None]:
    """CLAN WAR 2.0 фон/рамка для обычного превью состава — best-effort, никогда не
    бросает (отсутствие war2_cosmetics записей — штатный случай для всех игроков,
    которые ни разу не касались CLAN WAR 2.0)."""
    try:
        from app.services import war2_cosmetics

        return (
            await war2_cosmetics.get_equipped_background_path(user_id),
            await war2_cosmetics.get_equipped_frame_path(user_id),
        )
    except Exception:
        return None, None


async def _cosmetic_display_name(user_id: int, fallback: str) -> str:
    try:
        from app.services import war2_cosmetics
        from app.database.db import get_connection
        with get_connection() as connection:
            row = connection.execute("SELECT nickname FROM users WHERE id = ?", (user_id,)).fetchone()
        nickname = row["nickname"] if row else fallback
        return await war2_cosmetics.get_display_nickname(user_id, nickname)
    except Exception:
        return fallback


async def send_match_lineup_previews(*, bot, chat_id: int, result: MatchPlayResult) -> None:
    """Перед матчем отправляет две картинки: сначала состав игрока, потом состав соперника."""
    try:
        if result.user_id is not None:
            own_overview = await get_lineup_overview(result.user_id)
            own_background, own_frame = await _equipped_war2_cosmetics(result.user_id)
            own_name = await _cosmetic_display_name(result.user_id, "Ты")
            own_image = render_lineup_image(
                own_overview, result.user_id, title=f"ТВОЙ СОСТАВ: {own_name}",
                background_override_path=own_background, frame_override_path=own_frame,
            )
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=FSInputFile(own_image),
                    caption=f"<b>Твой состав</b>\n{own_name}\nOVR: <b>{own_overview.average_overall or '—'}</b> (+{own_overview.chemistry_bonus})",
                )
            finally:
                remove_render_cache_file(own_image)
            await asyncio.sleep(0.7)

        if result.opponent_user_id is not None:
            opponent_overview = await get_lineup_overview(result.opponent_user_id)
            opponent_background, opponent_frame = await _equipped_war2_cosmetics(result.opponent_user_id)
            opponent_name = await _cosmetic_display_name(result.opponent_user_id, result.opponent_name)
            opponent_image = render_lineup_image(
                opponent_overview,
                result.opponent_user_id,
                title=f"СОСТАВ СОПЕРНИКА: {opponent_name}",
                background_override_path=opponent_background,
                frame_override_path=opponent_frame,
            )
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=FSInputFile(opponent_image),
                    caption=(
                        f"<b>Состав соперника</b>\n"
                        f"{opponent_name}\n"
                        f"OVR: <b>{opponent_overview.average_overall or '—'}</b> (+{opponent_overview.chemistry_bonus})"
                    ),
                )
            finally:
                remove_render_cache_file(opponent_image)
        else:
            opponent_image = render_opponent_lineup_placeholder(
                opponent_name=result.opponent_name or "BOT",
                opponent_ovr=result.opponent_lineup_ovr,
                user_id=result.user_id or 0,
            )
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=FSInputFile(opponent_image),
                    caption=f"<b>Состав соперника</b>\n{result.opponent_name or 'BOT'}\nOVR: <b>{result.opponent_lineup_ovr}</b> (+0)",
                )
            finally:
                remove_render_cache_file(opponent_image)
            await asyncio.sleep(0.7)
    except Exception as error:
        logger.exception("Failed to render pre-match lineups: %s", error)


def build_goal_timeline(result: MatchPlayResult) -> list[tuple[str, object | None]]:
    goal_events = [event for event in (result.events or []) if event.event_type == "GOAL"]
    user_left = max(0, result.user_score)
    opponent_left = max(0, result.opponent_score)
    timeline: list[tuple[str, object | None]] = []

    for event in goal_events:
        description = event.description.strip()
        opponent_goal = description.startswith(f"{result.opponent_name} ")

        if opponent_goal and opponent_left > 0:
            timeline.append(("opponent", event))
            opponent_left -= 1
        elif user_left > 0:
            timeline.append(("user", event))
            user_left -= 1
        elif opponent_left > 0:
            timeline.append(("opponent", event))
            opponent_left -= 1

    while user_left > 0:
        timeline.append(("user", None))
        user_left -= 1

    while opponent_left > 0:
        timeline.append(("opponent", None))
        opponent_left -= 1

    return timeline


async def show_live_match_for_result(
    *,
    bot,
    chat_id: int,
    message_id: int,
    result: MatchPlayResult,
) -> None:
    goal_timeline = build_goal_timeline(result)
    total_goals = len(goal_timeline)

    if total_goals == 0:
        await edit_stored_message(
            bot,
            chat_id,
            message_id,
            build_match_no_goal_live_text(result),
        )
        await asyncio.sleep(MATCH_PLAYING_SECONDS)
        return

    user_score = 0
    opponent_score = 0
    interval = MATCH_PLAYING_SECONDS / (total_goals + 1)

    for index, (side, event) in enumerate(goal_timeline, start=1):
        await asyncio.sleep(interval)

        if side == "user":
            user_score += 1
        else:
            opponent_score += 1

        await edit_stored_message(
            bot,
            chat_id,
            message_id,
            build_match_goal_live_text(
                result,
                event=event,
                user_score=user_score,
                opponent_score=opponent_score,
                scorer_side=side,
            ),
        )

    await asyncio.sleep(interval)


async def show_match_playing_and_result(
    *,
    callback: CallbackQuery,
    current_message: Message,
    current_result: MatchPlayResult,
    opponent_result: MatchPlayResult | None = None,
    opponent_chat_id: int | None = None,
    opponent_message_id: int | None = None,
) -> None:
    # #2: помечаем матч активным на время анимации — второй матч не запустить.
    lock_user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if lock_user_id is not None:
        await try_acquire_match_lock(lock_user_id)

    try:
        await _run_match_animation_and_result(
            callback=callback,
            current_message=current_message,
            current_result=current_result,
            opponent_result=opponent_result,
            opponent_chat_id=opponent_chat_id,
            opponent_message_id=opponent_message_id,
        )
    finally:
        if lock_user_id is not None:
            await release_match_lock(lock_user_id)


async def _run_match_animation_and_result(
    *,
    callback: CallbackQuery,
    current_message: Message,
    current_result: MatchPlayResult,
    opponent_result: MatchPlayResult | None = None,
    opponent_chat_id: int | None = None,
    opponent_message_id: int | None = None,
) -> None:
    await send_match_lineup_previews(
        bot=callback.bot,
        chat_id=current_message.chat.id,
        result=current_result,
    )

    if opponent_result is not None and opponent_chat_id is not None:
        await send_match_lineup_previews(
            bot=callback.bot,
            chat_id=opponent_chat_id,
            result=opponent_result,
        )

    await edit_stored_message(
        callback.bot,
        current_message.chat.id,
        current_message.message_id,
        build_match_playing_text(current_result.opponent_name, current_result.opponent_type),
    )

    if opponent_result is not None and opponent_chat_id is not None and opponent_message_id is not None:
        await edit_stored_message(
            callback.bot,
            opponent_chat_id,
            opponent_message_id,
            build_match_playing_text(opponent_result.opponent_name, opponent_result.opponent_type),
        )

    live_tasks = [
        asyncio.create_task(
            show_live_match_for_result(
                bot=callback.bot,
                chat_id=current_message.chat.id,
                message_id=current_message.message_id,
                result=current_result,
            )
        )
    ]

    if opponent_result is not None and opponent_chat_id is not None and opponent_message_id is not None:
        live_tasks.append(
            asyncio.create_task(
                show_live_match_for_result(
                    bot=callback.bot,
                    chat_id=opponent_chat_id,
                    message_id=opponent_message_id,
                    result=opponent_result,
                )
            )
        )

    await asyncio.gather(*live_tasks)

    await edit_stored_message(
        callback.bot,
        current_message.chat.id,
        current_message.message_id,
        build_match_result_text(current_result),
        reply_markup=build_match_result_keyboard(current_result.match_id),
    )

    if opponent_result is not None and opponent_chat_id is not None and opponent_message_id is not None:
        await edit_stored_message(
            callback.bot,
            opponent_chat_id,
            opponent_message_id,
            build_match_result_text(opponent_result),
            reply_markup=build_match_result_keyboard(opponent_result.match_id),
        )


async def show_single_match_playing_and_result(
    *,
    bot,
    chat_id: int,
    message_id: int,
    result: MatchPlayResult,
) -> None:
    await send_match_lineup_previews(bot=bot, chat_id=chat_id, result=result)

    await edit_stored_message(
        bot,
        chat_id,
        message_id,
        build_match_playing_text(result.opponent_name, result.opponent_type),
    )

    await show_live_match_for_result(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        result=result,
    )

    await edit_stored_message(
        bot,
        chat_id,
        message_id,
        build_match_result_text(result),
        reply_markup=build_match_result_keyboard(result.match_id),
    )


async def finish_expired_queue_item_with_bot(
    *,
    bot,
    queue_id: int,
    chat_id: int,
    message_id: int,
) -> None:
    result = await finish_waiting_search_with_bot_by_queue_id(queue_id)

    if result is None:
        return

    if not result.success:
        await edit_stored_message(
            bot,
            chat_id,
            message_id,
            build_match_not_ready_text(result.message),
            reply_markup=build_match_not_ready_keyboard(),
        )
        return

    await edit_stored_message(
        bot,
        chat_id,
        message_id,
        build_match_queue_fallback_text(),
    )
    await asyncio.sleep(1)
    await show_single_match_playing_and_result(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        result=result,
    )


async def run_match_queue_watcher(bot) -> None:
    while True:
        try:
            expired_items = await get_expired_match_queue_items(limit=10)

            for item in expired_items:
                await finish_expired_queue_item_with_bot(
                    bot=bot,
                    queue_id=item.queue_id,
                    chat_id=item.chat_id,
                    message_id=item.message_id,
                )

            await asyncio.sleep(MATCH_QUEUE_WATCHER_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Match queue watcher failed: %s", error)
            await asyncio.sleep(MATCH_QUEUE_WATCHER_INTERVAL_SECONDS)


async def finish_queued_search_after_wait(
    *,
    bot,
    telegram_id: int,
    chat_id: int,
    message_id: int,
    wait_seconds: int,
) -> None:
    try:
        await asyncio.sleep(wait_seconds)
        result = await finish_waiting_search_with_bot(telegram_id)

        if result is None:
            return

        if not result.success:
            await edit_stored_message(
                bot,
                chat_id,
                message_id,
                build_match_not_ready_text(result.message),
                reply_markup=build_match_not_ready_keyboard(),
            )
            return

        await edit_stored_message(
            bot,
            chat_id,
            message_id,
            build_match_queue_fallback_text(),
        )
        await asyncio.sleep(1)
        await show_single_match_playing_and_result(
            bot=bot,
            chat_id=chat_id,
            message_id=message_id,
            result=result,
        )
    except Exception as error:
        logger.exception("Match queue fallback failed: %s", error)


async def show_matches_main(callback: CallbackQuery) -> None:
    start_match_queue_watcher(callback.bot)
    telegram_id = callback.from_user.id if callback.from_user else 0
    info = await get_match_main_info(telegram_id)

    if info is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_match_main_text(info),
        reply_markup=build_matches_main_keyboard(info.is_ready),
    )


async def show_match_history(callback: CallbackQuery, page: int) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    history_page = await get_match_history_page(
        user_id=profile.id,
        page=page,
        per_page=MATCH_HISTORY_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_match_history_text(history_page),
        reply_markup=build_match_history_keyboard(history_page),
    )


@router.message(F.text == MATCHES_BUTTON_TEXT)
async def matches_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await safe_delete_message(message)

    if message.from_user is None:
        return

    start_match_queue_watcher(message.bot)

    info = await get_match_main_info(message.from_user.id)

    if info is None:
        await message.answer("🏒 Открой игру через /start.")
        return

    await message.answer(
        build_match_main_text(info),
        reply_markup=build_matches_main_keyboard(info.is_ready),
    )


@router.callback_query(F.data == "matches:main")
async def matches_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_matches_main(callback)
    await callback.answer()


@router.callback_query(F.data == "matches:play")
async def matches_play(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    # ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK: user_id ВСЕГДА берётся из реального инициатора
    # Update (callback.from_user.id -> внутренний profile.id), а не из чего-либо,
    # что теоретически могло бы прийти в callback_data — так это же самое место
    # правильно блокирует не только повторный обычный матч, но и попытку начать
    # обычный матч, пока уже идёт Ranked/Stronghold/Clan War 2.0 (та же таблица
    # player_match_locks — единая для всех режимов).
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is not None:
        active_lock = await match_guard.get_active_match(user_id)
        if active_lock is not None:
            text = await match_guard.describe_active_match(active_lock)
            keyboard = build_active_match_blocked_keyboard(
                return_callback="matches:main",
                cancellable=match_guard.is_match_type_cancellable(active_lock.match_type),
                cancel_callback=None,
            )
            await callback.answer()
            if isinstance(message, Message):
                try:
                    await message.edit_text(text, reply_markup=keyboard)
                except TelegramBadRequest:
                    await callback.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
            return

    # #3: капча перед матчем (защита от автокликера).
    captcha = generate_captcha()
    await state.update_data(
        captcha_answer=captcha.correct,
        captcha_started=utc_now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    try:
        await message.edit_text(
            build_match_captcha_text(captcha.prompt),
            reply_markup=build_match_captcha_keyboard(captcha.options),
        )
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=build_match_captcha_text(captcha.prompt),
            reply_markup=build_match_captcha_keyboard(captcha.options),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("matches:captcha:"))
async def matches_captcha(callback: CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    choice = callback.data.split(":")[-1] if callback.data else ""
    data = await state.get_data()
    answer = data.get("captcha_answer")
    started = data.get("captcha_started")

    started_dt = None
    if started:
        try:
            started_dt = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            started_dt = None

    expired = started_dt is None or (utc_now() - started_dt).total_seconds() > CAPTCHA_TTL_SECONDS

    if expired or answer is None:
        captcha = generate_captcha()
        await state.update_data(captcha_answer=captcha.correct, captcha_started=utc_now().strftime("%Y-%m-%d %H:%M:%S"))
        await message.edit_text(
            build_match_captcha_text(captcha.prompt, retry="⏳ Время вышло, попробуй ещё раз."),
            reply_markup=build_match_captcha_keyboard(captcha.options),
        )
        await callback.answer("Время вышло")
        return

    if choice != answer:
        captcha = generate_captcha()
        await state.update_data(captcha_answer=captcha.correct, captcha_started=utc_now().strftime("%Y-%m-%d %H:%M:%S"))
        await message.edit_text(
            build_match_captcha_text(captcha.prompt, retry="❌ Неверно, попробуй ещё раз."),
            reply_markup=build_match_captcha_keyboard(captcha.options),
        )
        await callback.answer("Неверно")
        return

    # Капча пройдена — стартуем матч.
    await state.clear()
    await callback.answer("Проверка пройдена ✅")
    await start_matchmaking(callback, message)


async def start_matchmaking(callback: CallbackQuery, message: Message) -> None:
    start_match_queue_watcher(callback.bot)

    try:
        await message.edit_text(MATCH_SEARCH_TEXT, reply_markup=build_match_search_keyboard())
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        message = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=MATCH_SEARCH_TEXT,
            reply_markup=build_match_search_keyboard(),
        )

    matchmaking = await enter_matchmaking(
        telegram_id=callback.from_user.id,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )

    if matchmaking.status == "not_ready":
        await edit_stored_message(
            callback.bot,
            message.chat.id,
            message.message_id,
            build_match_not_ready_text(matchmaking.message),
            reply_markup=build_match_not_ready_keyboard(),
        )
        return

    if matchmaking.status == "already_queued":
        await edit_stored_message(
            callback.bot,
            message.chat.id,
            message.message_id,
            MATCH_ALREADY_SEARCHING_TEXT,
            reply_markup=build_match_search_keyboard(),
        )
        return

    if matchmaking.status == "matched" and matchmaking.current_result is not None:
        await show_match_playing_and_result(
            callback=callback,
            current_message=message,
            current_result=matchmaking.current_result,
            opponent_result=matchmaking.opponent_result,
            opponent_chat_id=matchmaking.opponent.chat_id if matchmaking.opponent else None,
            opponent_message_id=matchmaking.opponent.message_id if matchmaking.opponent else None,
        )
        return

    task = asyncio.create_task(
        finish_queued_search_after_wait(
            bot=callback.bot,
            telegram_id=callback.from_user.id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            wait_seconds=matchmaking.wait_seconds,
        )
    )
    track_background_task(task)


@router.callback_query(F.data == "matches:cancel")
async def matches_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    result = await cancel_match_search(callback.from_user.id)
    await edit_stored_message(
        callback.bot,
        message.chat.id,
        message.message_id,
        MATCH_CANCELLED_TEXT,
        reply_markup=build_matches_main_keyboard(True),
    )
    await callback.answer(result.message)


@router.callback_query(F.data.startswith("matches:history:"))
async def matches_history(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    await show_match_history(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("matches:details:"))
async def matches_details(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []

    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Матч не найден", show_alert=True)
        return

    match_id = int(parts[2])
    page = int(parts[3])
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    match = await get_match_details(profile.id, match_id)

    if match is None:
        await callback.answer("Матч не найден", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_match_details_text(match),
        reply_markup=build_match_details_keyboard(page),
    )
    await callback.answer()


@router.callback_query(F.data == "matches:page_info")
async def matches_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Это номер страницы")
