from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.lineup import (
    LINEUP_CARDS_PER_PAGE,
    build_lineup_clear_confirm_keyboard,
    build_lineup_main_keyboard,
    build_lineup_slot_cards_keyboard,
)
from app.services.lineup import (
    clear_lineup,
    get_lineup_cards_page,
    get_lineup_overview,
    is_valid_slot,
    remove_lineup_slot,
    set_lineup_card,
)
from app.services.users import get_player_profile_by_telegram_id
from app.texts.lineup import LINEUP_CLEAR_CONFIRM_TEXT, build_lineup_text, build_slot_cards_text
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()

LINEUP_BUTTON_TEXT = "🧩 Состав"


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


async def get_current_player(callback_or_message: CallbackQuery | Message):
    from_user = callback_or_message.from_user

    if from_user is None:
        return None

    return await get_player_profile_by_telegram_id(from_user.id)


async def show_lineup(callback: CallbackQuery) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    overview = await get_lineup_overview(profile.id)
    await edit_or_send(
        callback,
        build_lineup_text(overview),
        reply_markup=build_lineup_main_keyboard(overview),
    )


async def show_slot_cards(callback: CallbackQuery, slot_code: str, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    if not is_valid_slot(slot_code):
        await callback.answer("Слот не найден", show_alert=True)
        return

    cards_page = await get_lineup_cards_page(
        user_id=profile.id,
        slot_code=slot_code,
        page=page,
        per_page=LINEUP_CARDS_PER_PAGE,
    )
    overview = await get_lineup_overview(profile.id)
    current_filled = overview.slots.get(slot_code) is not None

    await edit_or_send(
        callback,
        build_slot_cards_text(cards_page),
        reply_markup=build_lineup_slot_cards_keyboard(cards_page, current_filled=current_filled),
    )


@router.message(F.text == LINEUP_BUTTON_TEXT)
async def lineup_button(message: Message, state: FSMContext) -> None:
    profile = await get_current_player(message)

    if profile is None:
        await safe_delete_message(message)
        await message.answer("🏒 Открой игру через /start.")
        return

    await state.clear()
    await safe_delete_message(message)

    overview = await get_lineup_overview(profile.id)
    await message.answer(
        build_lineup_text(overview),
        reply_markup=build_lineup_main_keyboard(overview),
    )


@router.callback_query(F.data == "lineup:main")
async def lineup_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_lineup(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("lineup:slot:"))
async def lineup_slot(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    slot_code = parts[2] if len(parts) > 2 else ""
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await show_slot_cards(callback, slot_code=slot_code, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("lineup:set:"))
async def lineup_set_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    parts = callback.data.split(":") if callback.data else []
    slot_code = parts[2] if len(parts) > 2 else ""
    user_card_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1

    result = await set_lineup_card(
        user_id=profile.id,
        slot_code=slot_code,
        user_card_id=user_card_id,
    )

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    await show_slot_cards(callback, slot_code=slot_code, page=page)
    await callback.answer(result.message)


@router.callback_query(F.data.startswith("lineup:remove:"))
async def lineup_remove_slot(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    slot_code = callback.data.split(":")[-1] if callback.data else ""
    result = await remove_lineup_slot(user_id=profile.id, slot_code=slot_code)

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    await show_lineup(callback)
    await callback.answer(result.message)


@router.callback_query(F.data == "lineup:clear_confirm")
async def lineup_clear_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(
        callback,
        LINEUP_CLEAR_CONFIRM_TEXT,
        reply_markup=build_lineup_clear_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "lineup:clear")
async def lineup_clear(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    result = await clear_lineup(profile.id)
    await show_lineup(callback)
    await callback.answer(result.message)


@router.callback_query(F.data == "lineup:page_info")
async def lineup_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
