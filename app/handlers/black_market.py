"""Пользовательские экраны BLACK MARKET.

Витрина генерируется лениво при первом рендере на сегодня (см.
app/services/black_market_store.py:list_storefront) — здесь только отображение и
покупка, никакой генерации напрямую.

Поток покупки — список (пагинация) -> карточка товара (подробности + preview) ->
явное подтверждение/отмена -> результат. Раньше покупка выполнялась сразу по клику
в списке без отдельного шага подтверждения — это было исправлено при аудите
(раздел 1 ТЗ аудита: "подтвердить или отменить покупку").
"""

from __future__ import annotations

import logging
import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.keyboards import black_market as keyboards
from app.services.black_market_common import BlackMarketError, format_next_reset_hint
from app.services.black_market_items import get_preview_render_args
from app.services.black_market_store import list_storefront, purchase
from app.services import error_log
from app.services.renders import render_black_market_item_preview
from app.services.users import get_player_profile_by_telegram_id
from app.texts import black_market as texts
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()
logger = logging.getLogger(__name__)

BLACK_MARKET_BUTTON_TEXT = "🕶 Чёрный рынок"


def error_text(error: BlackMarketError) -> str:
    return texts.error_text(error.code, error.message)


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


async def _profile(callback_or_message):
    user = callback_or_message.from_user
    if user is None:
        return None
    return await get_player_profile_by_telegram_id(user.id)


async def build_storefront_screen(user_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    rotation = await list_storefront(user_id)
    lines = ["🕶 <b>Чёрный рынок</b>", "", format_next_reset_hint(), ""]
    if not rotation.items:
        lines.append("Сегодня ассортимент пуст. Загляни позже.")
    else:
        lines.append("Выбери товар, чтобы увидеть подробности и купить:")

    return "\n".join(lines), keyboards.build_storefront_keyboard(rotation, page)


def _find_item(rotation, rotation_item_id: int):
    return next((item for item in rotation.items if item.id == rotation_item_id), None)


async def build_item_detail_screen(user_id: int, rotation_item_id: int, return_page: int):
    rotation = await list_storefront(user_id)
    item = _find_item(rotation, rotation_item_id)
    if item is None:
        return None, None, None

    icon = texts.RARITY_ICONS.get(item.rarity, "")
    status_label = texts.ITEM_STATUS_LABELS.get(item.item_status, item.item_status)
    lines = [
        f"{icon} <b>{item.name}</b>",
        f"Тип: {texts.ITEM_TYPE_LABELS.get(item.item_type, item.item_type)}",
        f"Редкость: {item.rarity}",
        f"Цена: {item.price_amount} {item.price_currency_code}",
        f"Твой остаток: {item.remaining_personal_stock}/{item.initial_personal_stock}",
        f"Личный лимит покупок: {'без ограничений' if item.personal_purchase_limit <= 0 else item.personal_purchase_limit}",
        f"Уже куплено тобой: {item.purchased_quantity}",
        f"Статус: {status_label}",
    ]
    if item.description:
        lines.append("")
        lines.append(item.description)

    with get_connection() as connection:
        preview_args = get_preview_render_args(
            connection, item_type=item.item_type, reference_id=item.item_reference_id, preview_path=item.preview, rarity=item.rarity
        )
    preview_path = render_black_market_item_preview(cache_key=f"pool_item_{item.pool_item_id}", **preview_args)

    return "\n".join(lines), keyboards.build_item_detail_keyboard(item, return_page), preview_path


@router.message(F.text == BLACK_MARKET_BUTTON_TEXT)
async def black_market_button(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    if message.from_user is None:
        return

    if is_admin(message.from_user.id):
        from app.handlers.admin_black_market import show_admin_dashboard_message

        await show_admin_dashboard_message(message)
        return

    profile = await _profile(message)
    if profile is None:
        await message.answer("🏒 Открой игру через /start.")
        return

    try:
        text, keyboard = await build_storefront_screen(profile.id, 1)
    except BlackMarketError as error:
        await message.answer(error_text(error))
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "bm:main")
async def black_market_main_callback(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        text, keyboard = await build_storefront_screen(profile.id, 1)
    except BlackMarketError as error:
        await callback.answer(error_text(error), show_alert=True)
        return
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "bm:noop")
async def black_market_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("bm:page:"))
async def black_market_page_callback(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    try:
        page = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 1
    try:
        text, keyboard = await build_storefront_screen(profile.id, page)
    except BlackMarketError as error:
        await callback.answer(error_text(error), show_alert=True)
        return
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("bm:item:"))
async def black_market_item_detail(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    try:
        rotation_item_id = int(parts[2])
        return_page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Товар не найден.", show_alert=True)
        return

    try:
        text, keyboard, preview_path = await build_item_detail_screen(profile.id, rotation_item_id, return_page)
    except BlackMarketError as error:
        await callback.answer(error_text(error), show_alert=True)
        return
    if text is None:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    request_id = str(uuid.uuid4())
    await state.update_data(**{f"bm_req_{rotation_item_id}": request_id})

    message = callback.message
    if isinstance(message, Message):
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_photo(message.chat.id, FSInputFile(preview_path), caption=text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("bm:confirm:"))
async def black_market_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    try:
        rotation_item_id = int(parts[2])
        return_page = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Товар не найден.", show_alert=True)
        return

    # Acknowledge BEFORE any SQLite work. Previously the callback query remained
    # unanswered until the whole purchase transaction finished; if SQLite waited on
    # another writer or an unexpected exception occurred Telegram displayed an endless
    # loading spinner and the button looked broken.
    try:
        await callback.answer("Покупка обрабатывается…")
    except TelegramBadRequest:
        pass

    data = await state.get_data()
    request_id = data.get(f"bm_req_{rotation_item_id}")
    if not request_id:
        request_id = str(uuid.uuid4())
        await state.update_data(**{f"bm_req_{rotation_item_id}": request_id})

    message = callback.message

    try:
        result = await purchase(profile.id, rotation_item_id, str(request_id))
    except BlackMarketError as error:
        # Since the callback has already been acknowledged, show the error as a normal
        # message instead of trying to answer the same callback a second time.
        if isinstance(message, Message):
            await callback.bot.send_message(
                message.chat.id,
                f"❌ {error_text(error)}",
            )
        return
    except Exception as error:
        logger.exception(
            "Unhandled Black Market purchase error: telegram_id=%s user_id=%s rotation_item_id=%s",
            callback.from_user.id if callback.from_user else None,
            profile.id,
            rotation_item_id,
        )
        error_log.record_error(
            "black_market.confirm",
            error,
            context=f"user_id={profile.id} rotation_item_id={rotation_item_id}",
        )
        if isinstance(message, Message):
            await callback.bot.send_message(
                message.chat.id,
                "❌ Покупка не завершена. Ошибка записана в диагностику. Попробуй ещё раз.",
            )
        return

    # Clear the idempotency key only after a committed successful purchase.
    await state.update_data(**{f"bm_req_{rotation_item_id}": None})

    try:
        text, keyboard = await build_storefront_screen(profile.id, return_page)
    except BlackMarketError as error:
        if isinstance(message, Message):
            await callback.bot.send_message(
                message.chat.id,
                f"✅ Куплено: <b>{result.name}</b>\n"
                f"Списано: <b>{result.price_amount} {result.price_currency_code}</b>\n\n"
                f"⚠️ {error_text(error)}",
            )
        return

    if isinstance(message, Message):
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

        success_text = (
            f"✅ <b>Покупка успешна</b>\n"
            f"{result.name}\n"
            f"Списано: <b>{result.price_amount} {result.price_currency_code}</b>\n"
            f"Остаток товара: <b>{max(0, result.new_remaining_stock)}</b>\n\n"
        )
        await callback.bot.send_message(
            message.chat.id,
            success_text + text,
            reply_markup=keyboard,
        )
