from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.reply import build_admin_main_keyboard
from app.keyboards.starter_kit import (
    STARTER_KIT_CARDS_PER_PAGE,
    build_starter_kit_cards_keyboard,
    build_starter_kit_main_keyboard,
)
from app.services.starter_kit import (
    clear_starter_kit,
    clear_starter_kit_slot,
    get_starter_kit_cards_page,
    get_starter_kit_overview,
    set_starter_kit_card,
)
from app.texts.starter_kit import (
    STARTER_KIT_CARD_SELECTED_TEXT,
    STARTER_KIT_CLEARED_TEXT,
    STARTER_KIT_NOT_FOUND_TEXT,
    STARTER_KIT_SLOT_CLEARED_TEXT,
    build_starter_kit_cards_text,
    build_starter_kit_main_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()

STARTER_KIT_BUTTON_TEXT = "🏁 Стартовый набор"
ACTIVE_STARTER_KIT_MESSAGES: dict[int, tuple[int, int]] = {}


def remember_starter_kit_message(user_id: int | None, message: Message | None) -> None:
    if user_id is None or message is None:
        return

    ACTIVE_STARTER_KIT_MESSAGES[user_id] = (message.chat.id, message.message_id)


async def delete_starter_kit_message(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass


async def delete_saved_starter_kit_message(user_id: int | None, bot) -> None:
    if user_id is None:
        return

    active_message = ACTIVE_STARTER_KIT_MESSAGES.pop(user_id, None)

    if active_message is not None:
        await delete_starter_kit_message(bot, active_message[0], active_message[1])


async def answer_admin_only(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else None

    if is_admin(user_id):
        return True

    await message.answer("🏒 Раздел доступен только администрации лиги.")
    return False


async def answer_callback_admin_only(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True

    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def edit_starter_kit_message(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass

    remember_starter_kit_message(callback.from_user.id, message)


async def show_starter_kit_main(callback: CallbackQuery) -> None:
    overview = await get_starter_kit_overview()
    await edit_starter_kit_message(
        callback,
        build_starter_kit_main_text(overview),
        reply_markup=build_starter_kit_main_keyboard(overview),
    )


async def show_starter_kit_cards(callback: CallbackQuery, slot_code: str, page: int = 1) -> None:
    cards_page = await get_starter_kit_cards_page(
        slot_code=slot_code,
        page=page,
        per_page=STARTER_KIT_CARDS_PER_PAGE,
    )
    await edit_starter_kit_message(
        callback,
        build_starter_kit_cards_text(cards_page),
        reply_markup=build_starter_kit_cards_keyboard(cards_page),
    )


@router.message(F.text == STARTER_KIT_BUTTON_TEXT)
async def starter_kit_button(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    user_id = message.from_user.id if message.from_user else None
    await state.clear()
    await delete_saved_starter_kit_message(user_id, message.bot)
    await safe_delete_message(message)

    overview = await get_starter_kit_overview()
    sent_message = await message.answer(
        build_starter_kit_main_text(overview),
        reply_markup=build_starter_kit_main_keyboard(overview),
    )
    remember_starter_kit_message(user_id, sent_message)


@router.callback_query(F.data == "starter_kit:main")
async def starter_kit_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await show_starter_kit_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("starter_kit:choose:"))
async def starter_kit_choose(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = (callback.data or "").split(":")
    slot_code = parts[2] if len(parts) > 2 else "G"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await show_starter_kit_cards(callback, slot_code=slot_code, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("starter_kit:set:"))
async def starter_kit_set(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = (callback.data or "").split(":")

    if len(parts) < 5:
        await callback.answer(STARTER_KIT_NOT_FOUND_TEXT, show_alert=True)
        return

    slot_code = parts[2]
    card_id = int(parts[3]) if parts[3].isdigit() else 0
    success = await set_starter_kit_card(slot_code, card_id)

    if not success:
        await callback.answer(STARTER_KIT_NOT_FOUND_TEXT, show_alert=True)
        return

    await show_starter_kit_main(callback)
    await callback.answer(STARTER_KIT_CARD_SELECTED_TEXT)


@router.callback_query(F.data.startswith("starter_kit:clear:"))
async def starter_kit_clear_slot(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = (callback.data or "").split(":")
    slot_code = parts[2] if len(parts) > 2 else ""
    await clear_starter_kit_slot(slot_code)
    await show_starter_kit_main(callback)
    await callback.answer(STARTER_KIT_SLOT_CLEARED_TEXT)


@router.callback_query(F.data == "starter_kit:clear_all")
async def starter_kit_clear_all(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await clear_starter_kit()
    await show_starter_kit_main(callback)
    await callback.answer(STARTER_KIT_CLEARED_TEXT)


@router.callback_query(F.data == "starter_kit:page_info")
async def starter_kit_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Выбери карточку или перелистни страницу.")
