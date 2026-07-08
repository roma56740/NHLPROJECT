from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.user_cards import (
    USER_CARDS_PER_PAGE,
    build_bulk_sell_confirm_keyboard,
    build_bulk_sell_menu_keyboard,
    build_quick_sell_confirm_keyboard,
    build_user_card_profile_keyboard,
    build_user_cards_cancel_keyboard,
    build_user_cards_filters_keyboard,
    build_user_cards_list_keyboard,
    build_user_cards_main_keyboard,
)
from app.services.community import get_user_id_by_telegram_id
from app.services.quick_sell import (
    get_sell_preview,
    quick_sell_bulk,
    quick_sell_single,
    toggle_card_lock,
)
from app.services.renders import render_collection_image
from app.services.user_cards import (
    get_player_card_profile,
    get_player_cards_page,
    normalize_position,
    normalize_rarity,
)
from app.services.users import get_player_profile_by_telegram_id
from app.states.user_cards import UserCardsStates
from app.texts.user_cards import (
    USER_CARDS_FILTERS_TEXT,
    USER_CARDS_MAIN_TEXT,
    USER_CARDS_SEARCH_TEXT,
    build_player_card_profile_text,
    build_player_cards_page_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()

USER_CARDS_BUTTON_TEXT = "🃏 Карты"
USER_CARDS_FILTER_CACHE: dict[int, dict[str, str | None]] = {}


def get_filter_cache(telegram_id: int) -> dict[str, str | None]:
    return USER_CARDS_FILTER_CACHE.setdefault(
        telegram_id,
        {
            "search": None,
            "position": None,
            "rarity": None,
        },
    )


def clear_filter_cache(telegram_id: int) -> None:
    USER_CARDS_FILTER_CACHE[telegram_id] = {
        "search": None,
        "position": None,
        "rarity": None,
    }


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




async def send_cards_page_view(
    target: CallbackQuery | Message,
    cards_page,
    reply_markup=None,
) -> None:
    if isinstance(target, CallbackQuery):
        message = target.message
        bot = target.bot
        user_id = target.from_user.id
    else:
        message = target
        bot = target.bot
        user_id = target.from_user.id if target.from_user else 0

    if not isinstance(message, Message):
        return

    text = build_player_cards_page_text(cards_page)

    try:
        render_path = render_collection_image(cards_page, user_id=user_id)
    except Exception:
        render_path = None

    if render_path is None:
        if isinstance(target, CallbackQuery):
            await edit_or_send(target, text, reply_markup=reply_markup)
        else:
            await message.answer(text, reply_markup=reply_markup)
        return

    if isinstance(target, CallbackQuery):
        await safe_delete_callback_message(target)
    else:
        await safe_delete_message(message)

    await bot.send_photo(
        chat_id=message.chat.id,
        photo=FSInputFile(render_path),
        caption=text,
        reply_markup=reply_markup,
    )


async def show_cards_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    filters = get_filter_cache(callback.from_user.id)
    cards_page = await get_player_cards_page(
        user_id=profile.id,
        page=page,
        per_page=USER_CARDS_PER_PAGE,
        search=filters.get("search"),
        position=filters.get("position"),
        rarity=filters.get("rarity"),
    )

    await send_cards_page_view(
        callback,
        cards_page,
        reply_markup=build_user_cards_list_keyboard(
            cards=cards_page.cards,
            page=cards_page.page,
            pages_count=cards_page.pages_count,
            search=cards_page.search,
            position=cards_page.position,
            rarity=cards_page.rarity,
        ),
    )


async def show_card_profile(callback: CallbackQuery, user_card_id: int, page: int) -> None:
    card = await get_player_card_profile(
        user_card_id=user_card_id,
        telegram_id=callback.from_user.id,
    )

    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    text = build_player_card_profile_text(card)
    keyboard = build_user_card_profile_keyboard(
        user_card_id=card.id,
        page=page,
        is_locked=card.trade_locked,
        in_lineup=card.is_in_lineup,
    )
    image_path = Path(card.image_path)

    if image_path.exists():
        await safe_delete_callback_message(callback)
        await callback.bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=keyboard,
        )
        return

    await edit_or_send(callback, text, reply_markup=keyboard)


@router.message(F.text == USER_CARDS_BUTTON_TEXT)
async def user_cards_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    clear_filter_cache(message.from_user.id)
    await safe_delete_message(message)
    profile = await get_player_profile_by_telegram_id(message.from_user.id)

    if profile is None:
        await message.answer("🏒 Открой профиль через /start.")
        return

    cards_page = await get_player_cards_page(
        user_id=profile.id,
        page=1,
        per_page=USER_CARDS_PER_PAGE,
    )
    await send_cards_page_view(
        message,
        cards_page,
        reply_markup=build_user_cards_list_keyboard(
            cards=cards_page.cards,
            page=cards_page.page,
            pages_count=cards_page.pages_count,
            search=cards_page.search,
            position=cards_page.position,
            rarity=cards_page.rarity,
        ),
    )


@router.callback_query(F.data == "user_cards:main")
async def user_cards_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_cards_page(callback, page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:list:"))
async def user_cards_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_cards_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:view:"))
async def user_cards_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_card_id = int(parts[2])
    page = int(parts[3])
    await show_card_profile(callback, user_card_id=user_card_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:lock:"))
async def user_cards_lock(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_card_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    ok, message_text, _ = await toggle_card_lock(user_id, user_card_id)
    await callback.answer(message_text, show_alert=not ok)
    await show_card_profile(callback, user_card_id=user_card_id, page=page)


@router.callback_query(F.data.startswith("user_cards:sell:"))
async def user_cards_sell_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_card_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    preview, error = await get_sell_preview(user_id, user_card_id)
    if preview is None:
        await callback.answer(error or "Продажа недоступна", show_alert=True)
        return

    warn = "\n\n⚠️ Это ценная карта!" if preview["valuable"] else ""
    text = (
        f"<b>💰 Быстрая продажа</b>\n\n"
        f"🏒 <b>{escape(preview['name'], quote=False)}</b> · {preview['overall']} OVR · {preview['rarity']}\n"
        f"Цена: 🪙 <b>{preview['price']:,}</b> Coins".replace(",", " ")
        + warn
        + "\n\nПродать карту? Отменить будет нельзя."
    )
    await edit_or_send(callback, text, reply_markup=build_quick_sell_confirm_keyboard(user_card_id, page))
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:sell_do:"))
async def user_cards_sell_do(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_card_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    result = await quick_sell_single(user_id, user_card_id)
    balance_line = ""
    if result.new_balance is not None:
        balance_line = f"\n\n💰 Баланс: 🪙 <b>{result.new_balance:,}</b> Coins".replace(",", " ")
    text = f"<b>{result.title}</b>\n\n{result.description}{balance_line}"
    await edit_or_send(callback, text, reply_markup=build_user_cards_main_keyboard())
    await callback.answer(result.title, show_alert=not result.ok)


@router.callback_query(F.data == "user_cards:bulk_sell")
async def user_cards_bulk_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = (
        "<b>💰 Массовая продажа</b>\n\n"
        "♻️ Дубликаты — продаёт лишние копии, оставляя по одной каждой карты.\n"
        "⚪ Common — продаёт все обычные карты.\n\n"
        "Карты в составе и заблокированные карты не продаются."
    )
    await edit_or_send(callback, text, reply_markup=build_bulk_sell_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:bulk_confirm:"))
async def user_cards_bulk_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    mode = callback.data.split(":")[-1] if callback.data else ""
    label = "все дубликаты" if mode == "duplicates" else "все Common карты"
    text = (
        f"<b>💰 Подтверждение</b>\n\n"
        f"Продать {label}? Карты в составе и заблокированные будут пропущены.\n\n"
        f"Действие необратимо."
    )
    await edit_or_send(callback, text, reply_markup=build_bulk_sell_confirm_keyboard(mode))
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:bulk_sell_do:"))
async def user_cards_bulk_do(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    mode = callback.data.split(":")[-1] if callback.data else ""

    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    result = await quick_sell_bulk(user_id, mode)
    if not result.ok:
        await callback.answer("Не удалось выполнить продажу, попробуй ещё раз", show_alert=True)
        await user_cards_bulk_menu(callback, state)
        return

    skipped = f"\nПропущено {result.skipped_count} (в составе или заблокированы)." if result.skipped_count else ""
    balance = f"\n\n💰 Баланс: 🪙 <b>{result.new_balance:,}</b> Coins".replace(",", " ") if result.new_balance is not None else ""
    text = (
        f"<b>💰 Готово</b>\n\n"
        f"Продано карт: <b>{result.sold_count}</b>\n"
        f"Получено: 🪙 <b>{result.coins_earned:,}</b> Coins".replace(",", " ")
        + skipped
        + balance
    )
    await edit_or_send(callback, text, reply_markup=build_user_cards_main_keyboard())
    await callback.answer("Готово")


@router.callback_query(F.data == "user_cards:search")
async def user_cards_search(callback: CallbackQuery, state: FSMContext) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.clear()
    await state.set_state(UserCardsStates.search)

    if message.photo:
        await message.delete()
        sent_message = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=USER_CARDS_SEARCH_TEXT,
            reply_markup=build_user_cards_cancel_keyboard(),
        )
        await state.update_data(chat_id=sent_message.chat.id, message_id=sent_message.message_id)
    else:
        await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
        await message.edit_text(
            USER_CARDS_SEARCH_TEXT,
            reply_markup=build_user_cards_cancel_keyboard(),
        )

    await callback.answer()


@router.message(UserCardsStates.search)
async def user_cards_search_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    search = message.text or ""
    filters = get_filter_cache(message.from_user.id)
    filters["search"] = search

    await safe_delete_message(message)
    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    profile = await get_player_profile_by_telegram_id(message.from_user.id)

    if profile is None:
        await state.clear()
        await message.answer("🏒 Открой профиль через /start.")
        return

    cards_page = await get_player_cards_page(
        user_id=profile.id,
        page=1,
        per_page=USER_CARDS_PER_PAGE,
        search=filters.get("search"),
        position=filters.get("position"),
        rarity=filters.get("rarity"),
    )

    keyboard = build_user_cards_list_keyboard(
        cards=cards_page.cards,
        page=cards_page.page,
        pages_count=cards_page.pages_count,
        search=cards_page.search,
        position=cards_page.position,
        rarity=cards_page.rarity,
    )

    if chat_id and message_id:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            pass

    await send_cards_page_view(message, cards_page, reply_markup=keyboard)
    await state.clear()


@router.callback_query(F.data == "user_cards:filters")
async def user_cards_filters(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    filters = get_filter_cache(callback.from_user.id)
    await edit_or_send(
        callback,
        USER_CARDS_FILTERS_TEXT,
        reply_markup=build_user_cards_filters_keyboard(
            position=filters.get("position"),
            rarity=filters.get("rarity"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user_cards:filter_position:"))
async def user_cards_filter_position(callback: CallbackQuery) -> None:
    value = callback.data.split(":")[-1] if callback.data else "all"
    filters = get_filter_cache(callback.from_user.id)
    filters["position"] = normalize_position(value)
    await edit_or_send(
        callback,
        USER_CARDS_FILTERS_TEXT,
        reply_markup=build_user_cards_filters_keyboard(
            position=filters.get("position"),
            rarity=filters.get("rarity"),
        ),
    )
    await callback.answer("Фильтр обновлён")


@router.callback_query(F.data.startswith("user_cards:filter_rarity:"))
async def user_cards_filter_rarity(callback: CallbackQuery) -> None:
    value = callback.data.split(":")[-1] if callback.data else "all"
    filters = get_filter_cache(callback.from_user.id)
    filters["rarity"] = normalize_rarity(value)
    await edit_or_send(
        callback,
        USER_CARDS_FILTERS_TEXT,
        reply_markup=build_user_cards_filters_keyboard(
            position=filters.get("position"),
            rarity=filters.get("rarity"),
        ),
    )
    await callback.answer("Фильтр обновлён")


@router.callback_query(F.data == "user_cards:clear_filters")
async def user_cards_clear_filters(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    clear_filter_cache(callback.from_user.id)
    await show_cards_page(callback, page=1)
    await callback.answer("Фильтры сброшены")


@router.callback_query(F.data == "user_cards:page_info")
async def user_cards_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
