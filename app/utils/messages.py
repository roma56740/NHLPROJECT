from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


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


async def safe_edit_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Редактирует сообщение callback'а. Telegram-ошибку "message is not modified" не
    считает сбоем: отвечает пользователю и тихо завершает update (не логирует ERROR,
    не пробрасывает исключение). Любую другую TelegramBadRequest пробрасывает дальше —
    это не единственное место, где сообщение редактируется, и глушить реальные ошибки
    (например "message to edit not found") здесь не нужно.

    Возвращает True, если сообщение было отредактировано, False — если содержимое уже
    было актуальным (или callback пришёл без сообщения).
    """
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return False

    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            await callback.answer("Данные уже актуальны")
            return False
        raise
