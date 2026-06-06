from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


async def safe_delete_message(message: Message | None) -> None:
    if message is None:
        return

    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def safe_delete_callback_message(callback: CallbackQuery) -> None:
    message = callback.message

    if isinstance(message, Message):
        await safe_delete_message(message)
