from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.broadcast import (
    build_broadcast_back_keyboard,
    build_broadcast_main_keyboard,
    build_broadcast_photo_keyboard,
    build_broadcast_preview_keyboard,
)
from app.services.broadcast import send_broadcast
from app.states.broadcast import BroadcastStates
from app.texts.broadcast import (
    BROADCAST_CANCELLED_TEXT,
    BROADCAST_MAIN_TEXT,
    BROADCAST_PHOTO_INPUT,
    BROADCAST_PREVIEW_TITLE,
    BROADCAST_TEXT_INPUT,
    build_broadcast_sent_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()

BROADCAST_BUTTON_TEXT = "📢 Рассылка"


async def delete_control_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("control_chat_id")
    message_id = data.get("control_message_id")
    if chat_id and message_id:
        try:
            await message.bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
        except Exception:
            pass


async def save_control_message(state: FSMContext, message: Message) -> None:
    await state.update_data(control_chat_id=message.chat.id, control_message_id=message.message_id)


async def send_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = str(data.get("text") or "").strip()
    photo_file_id = data.get("photo_file_id")
    preview_text = f"{BROADCAST_PREVIEW_TITLE}{text}"

    if photo_file_id:
        if len(preview_text) <= 1024:
            preview_message = await message.answer_photo(photo=photo_file_id, caption=preview_text, reply_markup=build_broadcast_preview_keyboard())
        else:
            await message.answer_photo(photo=photo_file_id)
            preview_message = await message.answer(preview_text, reply_markup=build_broadcast_preview_keyboard())
    else:
        preview_message = await message.answer(preview_text, reply_markup=build_broadcast_preview_keyboard())

    await save_control_message(state, preview_message)


@router.message(F.text == BROADCAST_BUTTON_TEXT)
async def broadcast_button(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await safe_delete_message(message)
    sent = await message.answer(BROADCAST_MAIN_TEXT, reply_markup=build_broadcast_main_keyboard())
    await save_control_message(state, sent)


@router.callback_query(F.data == "broadcast:main")
async def broadcast_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(BROADCAST_MAIN_TEXT, reply_markup=build_broadcast_main_keyboard())
            await save_control_message(state, message)
        except Exception:
            await safe_delete_message(message)
            sent = await callback.bot.send_message(callback.from_user.id, BROADCAST_MAIN_TEXT, reply_markup=build_broadcast_main_keyboard())
            await save_control_message(state, sent)
    await callback.answer()


@router.callback_query(F.data == "broadcast:start")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    await state.set_state(BroadcastStates.waiting_text)
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(BROADCAST_TEXT_INPUT)
            await save_control_message(state, message)
        except Exception:
            await safe_delete_message(message)
            sent = await callback.bot.send_message(callback.from_user.id, BROADCAST_TEXT_INPUT)
            await save_control_message(state, sent)
    await callback.answer()


@router.message(BroadcastStates.waiting_text)
async def broadcast_text_received(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    text = (message.text or "").strip()
    await safe_delete_message(message)
    if not text:
        await message.answer("Напиши текст рассылки.")
        return

    await delete_control_message(message, state)
    await state.update_data(text=text, photo_file_id=None)
    await state.set_state(BroadcastStates.waiting_photo)
    sent = await message.answer(BROADCAST_PHOTO_INPUT, reply_markup=build_broadcast_photo_keyboard())
    await save_control_message(state, sent)


@router.message(BroadcastStates.waiting_photo, F.photo)
async def broadcast_photo_received(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    photo_file_id = message.photo[-1].file_id
    await safe_delete_message(message)
    await delete_control_message(message, state)
    await state.update_data(photo_file_id=photo_file_id)
    await send_preview(message, state)


@router.callback_query(F.data == "broadcast:skip_photo")
async def broadcast_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    message = callback.message
    if isinstance(message, Message):
        await safe_delete_message(message)
        await state.update_data(photo_file_id=None)
        await send_preview(message, state)
    await callback.answer()


@router.callback_query(F.data == "broadcast:send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    data = await state.get_data()
    text = str(data.get("text") or "").strip()
    photo_file_id = data.get("photo_file_id")
    message = callback.message
    if not text:
        await callback.answer("Текст рассылки не найден", show_alert=True)
        return

    if isinstance(message, Message):
        try:
            await message.edit_text("<b>📢 Рассылка отправляется...</b>")
        except Exception:
            pass

    result = await send_broadcast(callback.bot, text=text, photo_file_id=photo_file_id)
    await state.clear()

    if isinstance(message, Message):
        await message.answer(build_broadcast_sent_text(result.total, result.success, result.failed), reply_markup=build_broadcast_back_keyboard())
    await callback.answer("Готово")


@router.callback_query(F.data == "broadcast:cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Раздел доступен администратору", show_alert=True)
        return
    await state.clear()
    message = callback.message
    if isinstance(message, Message):
        await safe_delete_message(message)
        await callback.bot.send_message(message.chat.id, BROADCAST_CANCELLED_TEXT, reply_markup=build_broadcast_back_keyboard())
    await callback.answer("Отменено")
