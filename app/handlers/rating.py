from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.rating import (
    RATING_PER_PAGE,
    build_leaderboard_keyboard,
    build_rating_back_keyboard,
    build_rating_main_keyboard,
)
from app.services.rating import (
    get_current_league_leaderboard_page,
    get_global_leaderboard_page,
    get_olympics_leaderboard_page,
    get_rating_profile,
)
from app.texts.rating import build_leaderboard_text, build_leagues_text, build_rating_main_text
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()

RATING_BUTTON_TEXT = "🏆 Рейтинг"


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

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


async def show_rating_main(callback: CallbackQuery) -> None:
    profile = await get_rating_profile(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_rating_main_text(profile),
        reply_markup=build_rating_main_keyboard(),
    )


@router.message(F.text == RATING_BUTTON_TEXT)
async def rating_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await safe_delete_message(message)

    if message.from_user is None:
        return

    profile = await get_rating_profile(message.from_user.id)

    if profile is None:
        await message.answer("🏆 Открой игру через /start.")
        return

    await message.answer(
        build_rating_main_text(profile),
        reply_markup=build_rating_main_keyboard(),
    )


@router.callback_query(F.data == "rating:main")
async def rating_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_rating_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("rating:global:"))
async def rating_global(callback: CallbackQuery) -> None:
    page = parse_page(callback.data)
    leaderboard = await get_global_leaderboard_page(page=page, per_page=RATING_PER_PAGE)

    await edit_or_send(
        callback,
        build_leaderboard_text(leaderboard),
        reply_markup=build_leaderboard_keyboard(leaderboard),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rating:league:"))
async def rating_league(callback: CallbackQuery) -> None:
    page = parse_page(callback.data)
    leaderboard = await get_current_league_leaderboard_page(
        telegram_id=callback.from_user.id,
        page=page,
        per_page=RATING_PER_PAGE,
    )

    if leaderboard is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_leaderboard_text(leaderboard),
        reply_markup=build_leaderboard_keyboard(leaderboard),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rating:olympics:"))
async def rating_olympics(callback: CallbackQuery) -> None:
    page = parse_page(callback.data)
    leaderboard = await get_olympics_leaderboard_page(page=page, per_page=RATING_PER_PAGE)

    await edit_or_send(
        callback,
        build_leaderboard_text(leaderboard),
        reply_markup=build_leaderboard_keyboard(leaderboard),
    )
    await callback.answer()


@router.callback_query(F.data == "rating:leagues")
async def rating_leagues(callback: CallbackQuery) -> None:
    profile = await get_rating_profile(callback.from_user.id)
    current_league = profile.league if profile is not None else None

    await edit_or_send(
        callback,
        build_leagues_text(current_league),
        reply_markup=build_rating_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "rating:page_info")
async def rating_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Ты уже на этой странице")


def parse_page(value: str | None) -> int:
    if value is None:
        return 1

    try:
        return max(1, int(value.rsplit(":", 1)[-1]))
    except ValueError:
        return 1
