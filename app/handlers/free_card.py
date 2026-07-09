
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.free_card import (
    build_free_card_admin_cancel_keyboard,
    build_free_card_admin_keyboard,
    build_free_card_user_keyboard,
)
from app.services.renders import render_card_profile_image
from app.services.free_card import (
    add_free_card_collection,
    claim_free_card,
    get_free_card_admin_status,
    get_free_card_status,
    remove_free_card_collection,
    set_free_card_collection,
)
from app.services.users import get_player_profile_by_telegram_id
from app.states.free_card import FreeCardStates
from app.texts.free_card import (
    FREE_CARD_BUTTON_TEXT,
    FREE_CARD_ADD_COLLECTION_TEXT,
    FREE_CARD_COLLECTION_NOT_FOUND_TEXT,
    FREE_CARD_REMOVE_COLLECTION_TEXT,
    FREE_CARD_SET_COLLECTION_TEXT,
    build_free_card_admin_text,
    build_free_card_collection_added_text,
    build_free_card_collection_removed_text,
    build_free_card_collection_saved_text,
    build_free_card_reward_text,
    build_free_card_user_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()


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


async def show_user_free_card(message: Message, telegram_id: int) -> None:
    profile = await get_player_profile_by_telegram_id(telegram_id)

    if profile is None:
        await message.answer("🏒 Открой профиль через /start.")
        return

    status = await get_free_card_status(profile.id)
    await message.answer(
        build_free_card_user_text(status),
        reply_markup=build_free_card_user_keyboard(status.is_ready),
    )


async def show_admin_free_card(message: Message) -> None:
    status = await get_free_card_admin_status()
    await message.answer(
        build_free_card_admin_text(status),
        reply_markup=build_free_card_admin_keyboard(),
    )


@router.message(F.text == FREE_CARD_BUTTON_TEXT)
async def free_card_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    await safe_delete_message(message)

    if is_admin(message.from_user.id):
        await show_admin_free_card(message)
        return

    await show_user_free_card(message, message.from_user.id)


@router.callback_query(F.data == "free_card:user")
async def free_card_user_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    status = await get_free_card_status(profile.id)
    await edit_or_send(
        callback,
        build_free_card_user_text(status),
        reply_markup=build_free_card_user_keyboard(status.is_ready),
    )
    await callback.answer()


@router.callback_query(F.data == "free_card:admin")
async def free_card_admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору", show_alert=True)
        return

    status = await get_free_card_admin_status()
    await edit_or_send(
        callback,
        build_free_card_admin_text(status),
        reply_markup=build_free_card_admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "free_card:claim")
async def free_card_claim_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    reward, status = await claim_free_card(profile.id)

    if reward is None:
        await edit_or_send(
            callback,
            build_free_card_user_text(status),
            reply_markup=build_free_card_user_keyboard(status.is_ready),
        )
        await callback.answer()
        return

    text = build_free_card_reward_text(reward)

    await safe_delete_callback_message(callback)

    try:
        image_path = render_card_profile_image(reward, user_id=callback.from_user.id)
    except Exception:
        image_path = None

    if image_path is not None:
        await callback.bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=build_free_card_user_keyboard(False),
        )
    else:
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=build_free_card_user_keyboard(False),
        )

    await callback.answer("Карточка добавлена в коллекцию")


@router.callback_query(F.data == "free_card:admin:add_collection")
async def free_card_add_collection(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору", show_alert=True)
        return
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(FreeCardStates.add_collection)
    if message.photo:
        await message.delete()
        sent_message = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=FREE_CARD_ADD_COLLECTION_TEXT,
            reply_markup=build_free_card_admin_cancel_keyboard(),
        )
        await state.update_data(chat_id=sent_message.chat.id, message_id=sent_message.message_id)
    else:
        await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
        await message.edit_text(FREE_CARD_ADD_COLLECTION_TEXT, reply_markup=build_free_card_admin_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "free_card:admin:remove_collection")
async def free_card_remove_collection(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору", show_alert=True)
        return
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(FreeCardStates.remove_collection)
    if message.photo:
        await message.delete()
        sent_message = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=FREE_CARD_REMOVE_COLLECTION_TEXT,
            reply_markup=build_free_card_admin_cancel_keyboard(),
        )
        await state.update_data(chat_id=sent_message.chat.id, message_id=sent_message.message_id)
    else:
        await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
        await message.edit_text(FREE_CARD_REMOVE_COLLECTION_TEXT, reply_markup=build_free_card_admin_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "free_card:admin:set_collection")
async def free_card_set_collection(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору", show_alert=True)
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.clear()
    await state.set_state(FreeCardStates.collection)

    if message.photo:
        await message.delete()
        sent_message = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=FREE_CARD_SET_COLLECTION_TEXT,
            reply_markup=build_free_card_admin_cancel_keyboard(),
        )
        await state.update_data(chat_id=sent_message.chat.id, message_id=sent_message.message_id)
    else:
        await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
        await message.edit_text(
            FREE_CARD_SET_COLLECTION_TEXT,
            reply_markup=build_free_card_admin_cancel_keyboard(),
        )

    await callback.answer()


async def _finish_collection_edit(message: Message, state: FSMContext, collection, text_builder) -> None:
    await safe_delete_message(message)
    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if collection is None:
        if chat_id and message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=FREE_CARD_COLLECTION_NOT_FOUND_TEXT,
                    reply_markup=build_free_card_admin_cancel_keyboard(),
                )
            except TelegramBadRequest:
                await message.answer(FREE_CARD_COLLECTION_NOT_FOUND_TEXT, reply_markup=build_free_card_admin_cancel_keyboard())
        else:
            await message.answer(FREE_CARD_COLLECTION_NOT_FOUND_TEXT, reply_markup=build_free_card_admin_cancel_keyboard())
        return

    await state.clear()
    text = text_builder(collection)
    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_free_card_admin_keyboard(),
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=build_free_card_admin_keyboard())


@router.message(FreeCardStates.add_collection)
async def free_card_add_collection_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not is_admin(message.from_user.id):
        await state.clear()
        await safe_delete_message(message)
        return
    collection = await add_free_card_collection(message.text or "")
    await _finish_collection_edit(message, state, collection, build_free_card_collection_added_text)


@router.message(FreeCardStates.remove_collection)
async def free_card_remove_collection_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not is_admin(message.from_user.id):
        await state.clear()
        await safe_delete_message(message)
        return
    collection = await remove_free_card_collection(message.text or "")
    await _finish_collection_edit(message, state, collection, build_free_card_collection_removed_text)


@router.message(FreeCardStates.collection)
async def free_card_set_collection_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    if not is_admin(message.from_user.id):
        await state.clear()
        await safe_delete_message(message)
        return

    query = message.text or ""
    collection = await set_free_card_collection(query)
    await safe_delete_message(message)

    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if collection is None:
        if chat_id and message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=FREE_CARD_COLLECTION_NOT_FOUND_TEXT,
                    reply_markup=build_free_card_admin_cancel_keyboard(),
                )
            except TelegramBadRequest:
                await message.answer(
                    FREE_CARD_COLLECTION_NOT_FOUND_TEXT,
                    reply_markup=build_free_card_admin_cancel_keyboard(),
                )
        else:
            await message.answer(
                FREE_CARD_COLLECTION_NOT_FOUND_TEXT,
                reply_markup=build_free_card_admin_cancel_keyboard(),
            )
        return

    await state.clear()
    text = build_free_card_collection_saved_text(collection)

    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_free_card_admin_keyboard(),
            )
            return
        except TelegramBadRequest:
            pass

    await message.answer(text, reply_markup=build_free_card_admin_keyboard())
