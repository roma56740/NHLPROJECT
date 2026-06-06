from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.packs import (
    ADMIN_PACKS_PER_PAGE,
    PACK_HISTORY_PER_PAGE,
    USER_PACKS_PER_PAGE,
    build_admin_pack_cancel_keyboard,
    build_admin_pack_confirm_keyboard,
    build_admin_pack_available_cards_keyboard,
    build_admin_pack_cards_keyboard,
    build_admin_pack_currency_keyboard,
    build_admin_pack_profile_keyboard,
    build_admin_pack_shop_keyboard,
    build_admin_packs_list_keyboard,
    build_admin_packs_main_keyboard,
    build_pack_history_keyboard,
    build_pack_opening_result_keyboard,
    build_user_pack_inventory_keyboard,
    build_user_pack_profile_keyboard,
    build_user_packs_main_keyboard,
)
from app.services.packs import (
    PackDraft,
    add_card_to_pack,
    create_admin_pack,
    get_admin_pack_details,
    get_admin_packs_page,
    get_pack_history_page,
    get_pack_available_cards_page,
    get_pack_cards_page,
    get_pack_info,
    get_user_pack_inventory_page,
    get_user_pack_quantity,
    open_user_pack,
    parse_rarity_chances,
    remove_card_from_pack,
    toggle_pack_active,
    toggle_pack_shop,
    update_pack_cards_count,
    update_pack_image_path,
    update_pack_price,
    update_pack_rarity_chances,
    update_pack_text_field,
)
from app.services.users import get_player_profile_by_telegram_id
from app.states.packs import AdminPackStates
from app.texts.packs import (
    ADMIN_PACK_BAD_COUNT_TEXT,
    ADMIN_PACK_BAD_DESCRIPTION_TEXT,
    ADMIN_PACK_BAD_IMAGE_TEXT,
    ADMIN_PACK_BAD_NAME_TEXT,
    ADMIN_PACK_BAD_PRICE_TEXT,
    ADMIN_PACK_CANCEL_TEXT,
    ADMIN_PACK_CARD_SEARCH_TEXT,
    ADMIN_PACK_COUNT_TEXT,
    ADMIN_PACK_CURRENCY_TEXT,
    ADMIN_PACK_DESCRIPTION_TEXT,
    ADMIN_PACK_IMAGE_TEXT,
    ADMIN_PACK_NAME_TEXT,
    ADMIN_PACK_ODDS_TEXT,
    ADMIN_PACK_PRICE_TEXT,
    ADMIN_PACK_SEARCH_TEXT,
    ADMIN_PACK_SHOP_TEXT,
    ADMIN_PACKS_MAIN_TEXT,
    USER_PACKS_MAIN_TEXT,
    build_admin_pack_available_cards_text,
    build_admin_pack_cards_text,
    build_admin_pack_profile_text,
    build_admin_packs_page_text,
    build_pack_draft_text,
    build_pack_history_text,
    build_pack_opening_error_text,
    build_pack_opening_result_text,
    build_user_pack_inventory_text,
    build_user_pack_profile_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()

PACKS_BUTTON_TEXT = "🎁 Паки"
PACK_IMAGES_DIR = Path("assets/uploads/packs")
ADMIN_PACK_SEARCH_CACHE: dict[int, str] = {}
ADMIN_PACK_CARD_SEARCH_CACHE: dict[tuple[int, int], str] = {}


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


async def get_current_player(callback: CallbackQuery):
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return None

    return profile


async def answer_callback_admin_only(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True

    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def show_inventory_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    inventory_page = await get_user_pack_inventory_page(
        user_id=profile.id,
        page=page,
        per_page=USER_PACKS_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_user_pack_inventory_text(inventory_page),
        reply_markup=build_user_pack_inventory_keyboard(
            packs=inventory_page.packs,
            page=inventory_page.page,
            pages_count=inventory_page.pages_count,
        ),
    )


async def show_pack_profile(callback: CallbackQuery, pack_id: int, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    pack = await get_pack_info(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    quantity = await get_user_pack_quantity(user_id=profile.id, pack_id=pack.id)
    text = build_user_pack_profile_text(pack, quantity)
    keyboard = build_user_pack_profile_keyboard(pack_id=pack.id, page=page, quantity=quantity)
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


async def show_history_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    history_page = await get_pack_history_page(
        user_id=profile.id,
        page=page,
        per_page=PACK_HISTORY_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_pack_history_text(history_page),
        reply_markup=build_pack_history_keyboard(
            page=history_page.page,
            pages_count=history_page.pages_count,
        ),
    )


async def show_admin_packs_page(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    packs_page = await get_admin_packs_page(
        page=page,
        per_page=ADMIN_PACKS_PER_PAGE,
        search=search,
    )

    await edit_or_send(
        callback,
        build_admin_packs_page_text(packs_page),
        reply_markup=build_admin_packs_list_keyboard(
            packs=packs_page.packs,
            page=packs_page.page,
            pages_count=packs_page.pages_count,
            search=packs_page.search,
        ),
    )


async def show_admin_pack_profile(callback: CallbackQuery, pack_id: int, page: int) -> None:
    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    text = build_admin_pack_profile_text(pack)
    keyboard = build_admin_pack_profile_keyboard(
        pack_id=pack.id,
        page=page,
        active=pack.active,
        shop=pack.is_shop_available,
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


async def send_admin_pack_profile_after_input(message: Message, pack_id: int, page: int, state: FSMContext) -> None:
    data = await state.get_data()
    panel_chat_id = data.get("pack_panel_chat_id")
    panel_message_id = data.get("pack_panel_message_id")

    if panel_chat_id and panel_message_id:
        try:
            await message.bot.delete_message(chat_id=panel_chat_id, message_id=panel_message_id)
        except Exception:
            pass

    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await message.answer(ADMIN_PACKS_MAIN_TEXT, reply_markup=build_admin_packs_main_keyboard())
        return

    text = build_admin_pack_profile_text(pack)
    keyboard = build_admin_pack_profile_keyboard(
        pack_id=pack.id,
        page=page,
        active=pack.active,
        shop=pack.is_shop_available,
    )
    image_path = Path(pack.image_path) if pack.image_path else None

    if image_path and image_path.exists():
        sent = await message.answer_photo(
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=keyboard,
        )
    else:
        sent = await message.answer(text, reply_markup=keyboard)

    await state.update_data(pack_panel_chat_id=sent.chat.id, pack_panel_message_id=sent.message_id)


async def save_pack_image(message: Message) -> str | None:
    PACK_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    now_value = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0

    if message.photo:
        photo = message.photo[-1]
        file_name = f"pack_{now_value}_{user_id}_{photo.file_unique_id}.jpg"
        file_path = PACK_IMAGES_DIR / file_name
        await message.bot.download(photo, destination=file_path)
        return file_path.as_posix()

    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        suffix = Path(message.document.file_name or "pack.png").suffix.lower()

        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"

        file_name = f"pack_{now_value}_{user_id}_{message.document.file_unique_id}{suffix}"
        file_path = PACK_IMAGES_DIR / file_name
        await message.bot.download(message.document, destination=file_path)
        return file_path.as_posix()

    return None


def validate_pack_name(value: str) -> bool:
    return 2 <= len(value.strip()) <= 50


def validate_pack_description(value: str) -> bool:
    return 2 <= len(value.strip()) <= 300


def parse_positive_int(value: str, min_value: int, max_value: int) -> int | None:
    try:
        number = int(value.strip().replace(" ", ""))
    except ValueError:
        return None

    if number < min_value or number > max_value:
        return None

    return number


async def delete_saved_pack_panel(state: FSMContext, bot) -> None:
    data = await state.get_data()
    panel_chat_id = data.get("pack_panel_chat_id")
    panel_message_id = data.get("pack_panel_message_id")

    if not panel_chat_id or not panel_message_id:
        return

    try:
        await bot.delete_message(chat_id=panel_chat_id, message_id=panel_message_id)
    except Exception:
        pass


async def send_pack_prompt(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    await delete_saved_pack_panel(state, message.bot)
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(pack_panel_chat_id=sent.chat.id, pack_panel_message_id=sent.message_id)


async def prompt_from_callback(callback: CallbackQuery, state: FSMContext, text: str, reply_markup=None) -> None:
    message = callback.message

    if isinstance(message, Message):
        await state.update_data(pack_panel_chat_id=message.chat.id, pack_panel_message_id=message.message_id)

    await edit_or_send(callback, text, reply_markup=reply_markup)


async def show_pack_opening_result(callback: CallbackQuery, result) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await safe_delete_callback_message(callback)
    await callback.bot.send_message(chat_id=message.chat.id, text=build_pack_opening_result_text(result))

    for reward in result.rewards:
        image_path = Path(reward.image_path) if reward.image_path else None
        caption = (
            f"🃏 <b>{reward.name}</b>\n\n"
            f"⭐ {reward.overall} OVR · {reward.position}\n"
            f"🏒 {reward.team}\n"
            f"🌍 {reward.country}\n"
            f"🎨 {reward.collection_name}\n"
            f"💎 {reward.rarity}"
        )

        if image_path and image_path.exists():
            await callback.bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(image_path), caption=caption)
        else:
            await callback.bot.send_message(chat_id=message.chat.id, text=caption)

    await callback.bot.send_message(
        chat_id=message.chat.id,
        text="<b>✅ Карточки добавлены в коллекцию</b>",
        reply_markup=build_pack_opening_result_keyboard(),
    )


async def show_admin_pack_cards_page(callback: CallbackQuery, pack_id: int, list_page: int, back_page: int) -> None:
    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    cards_page = await get_pack_cards_page(pack_id=pack_id, page=list_page, per_page=ADMIN_PACKS_PER_PAGE)
    await edit_or_send(
        callback,
        build_admin_pack_cards_text(cards_page, pack.name),
        reply_markup=build_admin_pack_cards_keyboard(
            pack_id=pack_id,
            list_page=cards_page.page,
            back_page=back_page,
            cards=cards_page.cards,
            pages_count=cards_page.pages_count,
        ),
    )


async def show_admin_available_cards_page(
    callback: CallbackQuery,
    pack_id: int,
    back_page: int,
    card_page: int,
    search: str | None = None,
) -> None:
    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    cards_page = await get_pack_available_cards_page(
        pack_id=pack_id,
        page=card_page,
        per_page=ADMIN_PACKS_PER_PAGE,
        search=search,
    )
    await edit_or_send(
        callback,
        build_admin_pack_available_cards_text(cards_page, pack.name),
        reply_markup=build_admin_pack_available_cards_keyboard(
            pack_id=pack_id,
            back_page=back_page,
            card_page=cards_page.page,
            pages_count=cards_page.pages_count,
            cards=cards_page.cards,
            search=cards_page.search,
        ),
    )


@router.message(F.text == PACKS_BUTTON_TEXT)
async def packs_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    await safe_delete_message(message)

    if is_admin(message.from_user.id):
        await message.answer(
            ADMIN_PACKS_MAIN_TEXT,
            reply_markup=build_admin_packs_main_keyboard(),
        )
        return

    await message.answer(
        USER_PACKS_MAIN_TEXT,
        reply_markup=build_user_packs_main_keyboard(),
    )


@router.callback_query(F.data == "packs:main")
async def packs_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(
        callback,
        USER_PACKS_MAIN_TEXT,
        reply_markup=build_user_packs_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("packs:inventory:"))
async def packs_inventory(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_inventory_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("packs:view:"))
async def packs_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await show_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("packs:open:"))
async def packs_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])

    result, error = await open_user_pack(user_id=profile.id, pack_id=pack_id)

    if error or result is None:
        await edit_or_send(
            callback,
            build_pack_opening_error_text(error or "Пак не открыт."),
            reply_markup=build_user_packs_main_keyboard(),
        )
        await callback.answer()
        return

    await show_pack_opening_result(callback, result)
    await callback.answer("Пак открыт")


@router.callback_query(F.data.startswith("packs:history:"))
async def packs_history(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_history_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data == "packs:page_info")
async def packs_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")


@router.callback_query(F.data == "admin_packs:main")
async def admin_packs_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await edit_or_send(
        callback,
        ADMIN_PACKS_MAIN_TEXT,
        reply_markup=build_admin_packs_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:list:"))
async def admin_packs_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_admin_packs_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:search_page:"))
async def admin_packs_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    search = ADMIN_PACK_SEARCH_CACHE.get(callback.from_user.id)
    await show_admin_packs_page(callback, page=page, search=search)
    await callback.answer()


@router.callback_query(F.data == "admin_packs:search")
async def admin_packs_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await state.set_state(AdminPackStates.search)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_SEARCH_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPackStates.search)
async def admin_packs_search_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    search = (message.text or "").strip()
    ADMIN_PACK_SEARCH_CACHE[message.from_user.id] = search
    await safe_delete_message(message)
    await delete_saved_pack_panel(state, message.bot)
    await state.clear()

    packs_page = await get_admin_packs_page(page=1, per_page=ADMIN_PACKS_PER_PAGE, search=search)
    await message.answer(
        build_admin_packs_page_text(packs_page),
        reply_markup=build_admin_packs_list_keyboard(
            packs=packs_page.packs,
            page=packs_page.page,
            pages_count=packs_page.pages_count,
            search=packs_page.search,
        ),
    )


@router.callback_query(F.data.startswith("admin_packs:view:"))
async def admin_packs_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer()


@router.callback_query(F.data == "admin_packs:add")
async def admin_packs_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await state.set_state(AdminPackStates.waiting_for_image)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_IMAGE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_image)
async def admin_pack_add_image(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    image_path = await save_pack_image(message)
    await safe_delete_message(message)

    if image_path is None:
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_IMAGE_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(image_path=image_path)
    await state.set_state(AdminPackStates.waiting_for_name)
    await send_pack_prompt(message, state, ADMIN_PACK_NAME_TEXT, reply_markup=build_admin_pack_cancel_keyboard())


@router.message(AdminPackStates.waiting_for_name)
async def admin_pack_add_name(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    name = (message.text or "").strip()
    await safe_delete_message(message)

    if not validate_pack_name(name):
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_NAME_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(name=name)
    await state.set_state(AdminPackStates.waiting_for_description)
    await send_pack_prompt(message, state, ADMIN_PACK_DESCRIPTION_TEXT, reply_markup=build_admin_pack_cancel_keyboard())


@router.message(AdminPackStates.waiting_for_description)
async def admin_pack_add_description(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    description = (message.text or "").strip()
    await safe_delete_message(message)

    if not validate_pack_description(description):
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_DESCRIPTION_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(description=description)
    await state.set_state(None)
    await send_pack_prompt(
        message,
        state,
        ADMIN_PACK_CURRENCY_TEXT,
        reply_markup=build_admin_pack_currency_keyboard("add_currency"),
    )


@router.callback_query(F.data.startswith("admin_packs:add_currency:"))
async def admin_pack_add_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    currency = callback.data.split(":")[-1] if callback.data else "free"

    if currency == "free":
        await state.update_data(price_currency_code=None, price_amount=0)
        await state.set_state(AdminPackStates.waiting_for_cards_count)
        await edit_or_send(
            callback,
            ADMIN_PACK_COUNT_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(price_currency_code=currency)
    await state.set_state(AdminPackStates.waiting_for_price)
    await edit_or_send(
        callback,
        ADMIN_PACK_PRICE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_price)
async def admin_pack_add_price(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    price = parse_positive_int(message.text or "", 0, 999999999)
    await safe_delete_message(message)

    if price is None:
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_PRICE_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(price_amount=price)
    await state.set_state(AdminPackStates.waiting_for_cards_count)
    await send_pack_prompt(message, state, ADMIN_PACK_COUNT_TEXT, reply_markup=build_admin_pack_cancel_keyboard())


@router.message(AdminPackStates.waiting_for_cards_count)
async def admin_pack_add_count(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    cards_count = parse_positive_int(message.text or "", 1, 20)
    await safe_delete_message(message)

    if cards_count is None:
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_COUNT_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(cards_count=cards_count)
    await state.set_state(None)
    await send_pack_prompt(message, state, ADMIN_PACK_SHOP_TEXT, reply_markup=build_admin_pack_shop_keyboard())


@router.callback_query(F.data.startswith("admin_packs:add_shop:"))
async def admin_pack_add_shop(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    is_shop_available = callback.data.endswith(":1") if callback.data else False
    await state.update_data(is_shop_available=is_shop_available)
    data = await state.get_data()

    draft = PackDraft(
        image_path=str(data["image_path"]),
        name=str(data["name"]),
        description=str(data["description"]),
        price_currency_code=data.get("price_currency_code"),
        price_amount=int(data.get("price_amount", 0)),
        cards_count=int(data["cards_count"]),
        is_shop_available=bool(data["is_shop_available"]),
    )
    await state.update_data(draft=draft.__dict__)
    await edit_or_send(
        callback,
        build_pack_draft_text(draft),
        reply_markup=build_admin_pack_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_packs:add_confirm")
async def admin_pack_add_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    data = await state.get_data()
    draft_data = data.get("draft")

    if not isinstance(draft_data, dict):
        await edit_or_send(callback, ADMIN_PACKS_MAIN_TEXT, reply_markup=build_admin_packs_main_keyboard())
        await callback.answer()
        return

    draft = PackDraft(
        image_path=str(draft_data["image_path"]),
        name=str(draft_data["name"]),
        description=str(draft_data["description"]),
        price_currency_code=draft_data.get("price_currency_code"),
        price_amount=int(draft_data.get("price_amount", 0)),
        cards_count=int(draft_data["cards_count"]),
        is_shop_available=bool(draft_data["is_shop_available"]),
    )
    pack_id = await create_admin_pack(draft)
    await state.clear()
    await show_admin_pack_profile(callback, pack_id=pack_id, page=1)
    await callback.answer("Пак создан")


@router.callback_query(F.data.startswith("admin_packs:edit_image:"))
async def admin_pack_edit_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_image)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_IMAGE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_image)
async def admin_pack_edit_image_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    image_path = await save_pack_image(message)
    await safe_delete_message(message)

    if image_path is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_IMAGE_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_image_path(pack_id, image_path)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_name:") | F.data.startswith("admin_packs:edit_description:"))
async def admin_pack_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    action = parts[1]
    field = "name" if action == "edit_name" else "description"
    pack_id = int(parts[2])
    page = int(parts[3])
    text = ADMIN_PACK_NAME_TEXT if field == "name" else ADMIN_PACK_DESCRIPTION_TEXT
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page, field=field)
    await state.set_state(AdminPackStates.waiting_for_edit_text)
    await prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_text)
async def admin_pack_edit_text_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    field = str(data["field"])
    value = (message.text or "").strip()
    await safe_delete_message(message)

    if field == "name" and not validate_pack_name(value):
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_NAME_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    if field == "description" and not validate_pack_description(value):
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_DESCRIPTION_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_text_field(pack_id, field, value)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_price:"))
async def admin_pack_edit_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await edit_or_send(
        callback,
        ADMIN_PACK_CURRENCY_TEXT,
        reply_markup=build_admin_pack_currency_keyboard("edit_price_currency", pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:edit_price_currency:"))
async def admin_pack_edit_price_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    currency = parts[4]

    if currency == "free":
        await update_pack_price(pack_id, None, 0)
        await state.clear()
        await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
        await callback.answer("Цена обновлена")
        return

    await state.clear()
    await state.update_data(pack_id=pack_id, page=page, currency=currency)
    await state.set_state(AdminPackStates.waiting_for_edit_price)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_PRICE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_price)
async def admin_pack_edit_price_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    currency = str(data["currency"])
    price = parse_positive_int(message.text or "", 0, 999999999)
    await safe_delete_message(message)

    if price is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_PRICE_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_price(pack_id, currency, price)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_count:"))
async def admin_pack_edit_count(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_count)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_COUNT_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_count)
async def admin_pack_edit_count_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    cards_count = parse_positive_int(message.text or "", 1, 20)
    await safe_delete_message(message)

    if cards_count is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_COUNT_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_cards_count(pack_id, cards_count)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_odds:"))
async def admin_pack_edit_odds(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_odds)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_ODDS_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_odds)
async def admin_pack_edit_odds_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    chances, error = parse_rarity_chances(message.text or "")
    await safe_delete_message(message)

    if error or chances is None:
        await send_pack_prompt(
            message,
            state,
            build_pack_opening_error_text(error or "Шансы не сохранены."),
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_rarity_chances(pack_id, chances)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:cards:"))
async def admin_pack_cards(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    list_page = int(parts[3])
    back_page = int(parts[4])
    await show_admin_pack_cards_page(callback, pack_id=pack_id, list_page=list_page, back_page=back_page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:cards_add:"))
async def admin_pack_cards_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    back_page = int(parts[3])
    card_page = int(parts[4])
    await show_admin_available_cards_page(callback, pack_id=pack_id, back_page=back_page, card_page=card_page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:cards_search_page:"))
async def admin_pack_cards_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    back_page = int(parts[3])
    card_page = int(parts[4])
    search = ADMIN_PACK_CARD_SEARCH_CACHE.get((callback.from_user.id, pack_id))
    await show_admin_available_cards_page(
        callback,
        pack_id=pack_id,
        back_page=back_page,
        card_page=card_page,
        search=search,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:cards_search:"))
async def admin_pack_cards_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    back_page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=back_page)
    await state.set_state(AdminPackStates.waiting_for_card_search)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_CARD_SEARCH_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=back_page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_card_search)
async def admin_pack_cards_search_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    back_page = int(data.get("page", 1))
    search = (message.text or "").strip()
    ADMIN_PACK_CARD_SEARCH_CACHE[(message.from_user.id, pack_id)] = search
    await safe_delete_message(message)
    await delete_saved_pack_panel(state, message.bot)
    await state.clear()

    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await message.answer(ADMIN_PACKS_MAIN_TEXT, reply_markup=build_admin_packs_main_keyboard())
        return

    cards_page = await get_pack_available_cards_page(
        pack_id=pack_id,
        page=1,
        per_page=ADMIN_PACKS_PER_PAGE,
        search=search,
    )
    await message.answer(
        build_admin_pack_available_cards_text(cards_page, pack.name),
        reply_markup=build_admin_pack_available_cards_keyboard(
            pack_id=pack_id,
            back_page=back_page,
            card_page=cards_page.page,
            pages_count=cards_page.pages_count,
            cards=cards_page.cards,
            search=cards_page.search,
        ),
    )


@router.callback_query(F.data.startswith("admin_packs:cards_add_do:"))
async def admin_pack_cards_add_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    card_id = int(parts[3])
    back_page = int(parts[4])
    card_page = int(parts[5])
    await add_card_to_pack(pack_id=pack_id, card_id=card_id)
    await show_admin_available_cards_page(callback, pack_id=pack_id, back_page=back_page, card_page=card_page)
    await callback.answer("Карта добавлена")


@router.callback_query(F.data.startswith("admin_packs:cards_remove:"))
async def admin_pack_cards_remove(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    card_id = int(parts[3])
    list_page = int(parts[4])
    back_page = int(parts[5])
    await remove_card_from_pack(pack_id=pack_id, card_id=card_id)
    await show_admin_pack_cards_page(callback, pack_id=pack_id, list_page=list_page, back_page=back_page)
    await callback.answer("Карта убрана")


@router.callback_query(F.data.startswith("admin_packs:toggle_active:"))
async def admin_pack_toggle_active(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await toggle_pack_active(pack_id)
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_packs:toggle_shop:"))
async def admin_pack_toggle_shop(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await toggle_pack_shop(pack_id)
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer("Готово")


@router.callback_query(F.data == "admin_packs:page_info")
async def admin_packs_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
