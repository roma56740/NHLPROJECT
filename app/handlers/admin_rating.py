from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_rating import (
    build_admin_league_keyboard,
    build_admin_leaderboard_keyboard,
    build_admin_rating_back_keyboard,
    build_admin_rating_main_keyboard,
)
from app.services.rating import get_leaderboard_page
from app.texts.admin_rating import ADMIN_RATING_MAIN_TEXT
from app.texts.rating import build_leaderboard_text, build_leagues_text
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()

ADMIN_RATING_BUTTON_TEXT = "🏆 Лиги и рейтинг"


async def edit_or_answer(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


@router.message(F.text == ADMIN_RATING_BUTTON_TEXT)
async def admin_rating_button(message: Message) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await safe_delete_message(message)
    await message.answer(ADMIN_RATING_MAIN_TEXT, reply_markup=build_admin_rating_main_keyboard())


@router.callback_query(F.data == "admin_rating:main")
async def admin_rating_main(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await edit_or_answer(callback, ADMIN_RATING_MAIN_TEXT, reply_markup=build_admin_rating_main_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_rating:global:"))
async def admin_rating_global(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    rating_page = await get_leaderboard_page(
        page=page,
        per_page=5,
        mode="global",
        title="📊 Общий топ игроков",
        league=None,
    )
    await edit_or_answer(callback, build_leaderboard_text(rating_page), reply_markup=build_admin_leaderboard_keyboard(rating_page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_rating:league:"))
async def admin_rating_league(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    league = parts[2]
    page = int(parts[3])
    rating_page = await get_leaderboard_page(
        page=page,
        per_page=5,
        mode=f"league:{league}",
        title=f"🏆 Топ лиги {league}",
        league=league,
    )
    await edit_or_answer(callback, build_leaderboard_text(rating_page), reply_markup=build_admin_league_keyboard(league, rating_page))
    await callback.answer()


@router.callback_query(F.data == "admin_rating:leagues")
async def admin_rating_leagues(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await edit_or_answer(callback, build_leagues_text(), reply_markup=build_admin_rating_back_keyboard())
    await callback.answer()
