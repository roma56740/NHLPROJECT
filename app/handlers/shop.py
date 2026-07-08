from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.shop import (
    SHOP_HISTORY_PER_PAGE,
    SHOP_PACKS_PER_PAGE,
    build_shop_confirm_keyboard,
    build_shop_history_keyboard,
    build_shop_main_keyboard,
    build_shop_pack_list_keyboard,
    build_shop_pack_profile_keyboard,
    build_shop_purchase_result_keyboard,
)
from app.services.shop import (
    get_shop_history_page,
    get_shop_pack_details,
    get_shop_packs_page,
    purchase_shop_pack,
)
from app.services.users import get_player_profile_by_telegram_id
from app.texts.shop import (
    RUBLES_PURCHASE_TEXT,
    build_shop_main_text,
    SHOP_MAIN_TEXT,
    build_shop_confirm_text,
    build_shop_history_text,
    build_shop_pack_profile_text,
    build_shop_packs_page_text,
    build_shop_purchase_error_text,
    build_shop_purchase_success_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()

SHOP_BUTTON_TEXT = "🛒 Магазин"


async def get_current_player(event: Message | CallbackQuery):
    telegram_user = event.from_user

    if telegram_user is None:
        return None

    profile = await get_player_profile_by_telegram_id(telegram_user.id)

    if profile is None:
        if isinstance(event, CallbackQuery):
            await event.answer("Открой профиль через /start", show_alert=True)
        else:
            await event.answer("Сначала открой игру через /start")
        return None

    return profile


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


async def show_shop_main(callback: CallbackQuery) -> None:
    profile = await get_current_player(callback)
    if profile is None:
        return
    await edit_or_send(callback, build_shop_main_text(profile), reply_markup=build_shop_main_keyboard())


async def show_shop_packs_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    packs_page = await get_shop_packs_page(
        user_id=profile.id,
        page=page,
        per_page=SHOP_PACKS_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_shop_packs_page_text(packs_page),
        reply_markup=build_shop_pack_list_keyboard(
            packs=packs_page.packs,
            page=packs_page.page,
            pages_count=packs_page.pages_count,
        ),
    )


async def show_shop_pack_profile(callback: CallbackQuery, pack_id: int, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    pack = await get_shop_pack_details(user_id=profile.id, pack_id=pack_id)

    if pack is None:
        await callback.answer("Пак уже недоступен", show_alert=True)
        return

    text = build_shop_pack_profile_text(pack)
    keyboard = build_shop_pack_profile_keyboard(
        pack_id=pack.id,
        page=page,
        can_buy=pack.selected_cards_count > 0,
    )
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    image_path = Path(pack.image_path) if pack.image_path else None

    if image_path and image_path.exists():
        await safe_delete_callback_message(callback)
        await callback.bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=keyboard,
        )
        return

    await edit_or_send(callback, text, reply_markup=keyboard)


async def show_shop_history_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    history_page = await get_shop_history_page(
        user_id=profile.id,
        page=page,
        per_page=SHOP_HISTORY_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_shop_history_text(history_page),
        reply_markup=build_shop_history_keyboard(
            purchases=history_page.purchases,
            page=history_page.page,
            pages_count=history_page.pages_count,
        ),
    )


@router.message(F.text == SHOP_BUTTON_TEXT)
async def shop_button(message: Message) -> None:
    profile = await get_current_player(message)

    if profile is None:
        return

    await safe_delete_message(message)
    await message.answer(build_shop_main_text(profile), reply_markup=build_shop_main_keyboard())


@router.callback_query(F.data == "shop:main")
async def shop_main_callback(callback: CallbackQuery) -> None:
    await show_shop_main(callback)
    await callback.answer()


@router.callback_query(F.data == "shop:buy_rubles")
async def shop_buy_rubles_callback(callback: CallbackQuery) -> None:
    await edit_or_send(callback, RUBLES_PURCHASE_TEXT, reply_markup=build_shop_main_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("shop:packs:"))
async def shop_packs_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":") if callback.data else []
    page = int(parts[2])
    await show_shop_packs_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("shop:view:"))
async def shop_pack_view_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await show_shop_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("shop:confirm:"))
async def shop_confirm_callback(callback: CallbackQuery) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    pack = await get_shop_pack_details(user_id=profile.id, pack_id=pack_id)

    if pack is None:
        await callback.answer("Пак уже недоступен", show_alert=True)
        return

    if pack.selected_cards_count <= 0:
        await callback.answer("Пак скоро появится", show_alert=True)
        return

    await edit_or_send(
        callback,
        build_shop_confirm_text(pack),
        reply_markup=build_shop_confirm_keyboard(pack_id=pack.id, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy_callback(callback: CallbackQuery) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    result, error = await purchase_shop_pack(user_id=profile.id, pack_id=pack_id)

    if error or result is None:
        await edit_or_send(
            callback,
            build_shop_purchase_error_text(error or "Покупка не выполнена."),
            reply_markup=build_shop_pack_profile_keyboard(pack_id=pack_id, page=page, can_buy=True),
        )
        await callback.answer()
        return

    await edit_or_send(
        callback,
        build_shop_purchase_success_text(result),
        reply_markup=build_shop_purchase_result_keyboard(pack_id=result.pack_id),
    )
    await callback.answer("Пак куплен")


@router.callback_query(F.data.startswith("shop:history:"))
async def shop_history_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":") if callback.data else []
    page = int(parts[2])
    await show_shop_history_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data == "shop:page_info")
async def shop_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Листай страницы стрелками")
