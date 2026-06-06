import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.matches import (
    MATCH_HISTORY_PER_PAGE,
    build_match_details_keyboard,
    build_match_history_keyboard,
    build_match_not_ready_keyboard,
    build_match_result_keyboard,
    build_match_search_keyboard,
    build_matches_main_keyboard,
)
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
from app.services.users import get_player_profile_by_telegram_id
from app.texts.matches import (
    MATCH_ALREADY_SEARCHING_TEXT,
    MATCH_CANCELLED_TEXT,
    MATCH_SEARCH_TEXT,
    build_match_details_text,
    build_match_history_text,
    build_match_main_text,
    build_match_not_ready_text,
    build_match_playing_text,
    build_match_queue_fallback_text,
    build_match_result_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()
logger = logging.getLogger(__name__)

MATCHES_BUTTON_TEXT = "🏒 Играть"
MATCH_PLAYING_SECONDS = 5
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


async def show_match_playing_and_result(
    *,
    callback: CallbackQuery,
    current_message: Message,
    current_result: MatchPlayResult,
    opponent_result: MatchPlayResult | None = None,
    opponent_chat_id: int | None = None,
    opponent_message_id: int | None = None,
) -> None:
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

    await asyncio.sleep(MATCH_PLAYING_SECONDS)

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
    await edit_stored_message(
        bot,
        chat_id,
        message_id,
        build_match_playing_text(result.opponent_name, result.opponent_type),
    )

    await asyncio.sleep(MATCH_PLAYING_SECONDS)

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
        await callback.answer()
        return

    if matchmaking.status == "already_queued":
        await edit_stored_message(
            callback.bot,
            message.chat.id,
            message.message_id,
            MATCH_ALREADY_SEARCHING_TEXT,
            reply_markup=build_match_search_keyboard(),
        )
        await callback.answer("Поиск уже идёт")
        return

    if matchmaking.status == "matched" and matchmaking.current_result is not None:
        await callback.answer("Соперник найден")
        await show_match_playing_and_result(
            callback=callback,
            current_message=message,
            current_result=matchmaking.current_result,
            opponent_result=matchmaking.opponent_result,
            opponent_chat_id=matchmaking.opponent.chat_id if matchmaking.opponent else None,
            opponent_message_id=matchmaking.opponent.message_id if matchmaking.opponent else None,
        )
        return

    await callback.answer("Ищем соперника")
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
