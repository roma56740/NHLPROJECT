from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.reply import ADMIN_MAIN_TEXTS, build_admin_main_keyboard
from app.keyboards.admin_cards import (
    ADMIN_CARDS_PER_PAGE,
    build_admin_card_back_keyboard,
    build_admin_card_edit_keyboard,
    build_admin_card_profile_keyboard,
    build_admin_card_owners_keyboard,
    build_admin_card_owner_copies_keyboard,
    build_admin_card_copy_keyboard,
    build_admin_card_revoke_confirm_keyboard,
    build_admin_cards_cancel_keyboard,
    build_admin_cards_confirm_keyboard,
    build_admin_cards_list_keyboard,
    build_admin_cards_main_keyboard,
    build_admin_cards_positions_keyboard,
    build_admin_cards_rarities_keyboard,
    build_admin_collections_keyboard,
)
from app.services.admin_cards import (
    CardDraft,
    create_card,
    get_card_profile,
    get_card_owners_page,
    get_card_owner_copies_page,
    get_owned_card_copy,
    revoke_owned_card_copy,
    get_cards_page,
    get_collections,
    toggle_card_active,
    update_card_collection,
    update_card_image_path,
    update_card_overall,
    update_card_salary,
    update_card_position,
    update_card_rarity,
    update_card_text_field,
    validate_name,
    validate_overall,
    validate_short_text,
)
from app.states.admin_cards import AdminCardsStates
from app.texts.admin_cards import (
    ADMIN_CARDS_BAD_IMAGE_TEXT,
    ADMIN_CARDS_BAD_NAME_TEXT,
    ADMIN_CARDS_BAD_OVERALL_TEXT,
    ADMIN_CARDS_BAD_TEXT_TEXT,
    ADMIN_CARDS_CANCEL_TEXT,
    ADMIN_CARDS_COLLECTION_TEXT,
    ADMIN_CARDS_SALARY_TEXT,
    ADMIN_CARDS_COUNTRY_TEXT,
    ADMIN_CARDS_EMPTY_TEXT,
    ADMIN_CARDS_IMAGE_TEXT,
    ADMIN_CARDS_MAIN_TEXT,
    ADMIN_CARDS_NAME_TEXT,
    ADMIN_CARDS_OVERALL_TEXT,
    ADMIN_CARDS_POSITION_TEXT,
    ADMIN_CARDS_RARITY_TEXT,
    ADMIN_CARDS_SAVED_TEXT,
    ADMIN_CARDS_SEARCH_TEXT,
    ADMIN_CARDS_TEAM_TEXT,
    build_card_draft_text,
    build_card_edit_text,
    build_card_profile_text,
    build_card_owners_text,
    build_card_owner_copies_text,
    build_owned_card_copy_text,
    build_revoke_owned_card_confirm_text,
    build_cards_page_text,
    build_collections_text,
    build_edit_image_text,
    build_edit_value_text,
    get_edit_field_title,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()

ADMIN_CARDS_BUTTON_TEXT = "🃏 Карточки"
ADMIN_CARDS_SEARCH_CACHE: dict[int, str] = {}
ACTIVE_ADMIN_CARDS_MESSAGES: dict[int, tuple[int, int]] = {}
CARD_IMAGES_DIR = Path("assets/uploads/cards")


def remember_admin_cards_message(user_id: int | None, message: Message | None) -> None:
    if user_id is None or message is None:
        return

    ACTIVE_ADMIN_CARDS_MESSAGES[user_id] = (message.chat.id, message.message_id)


async def delete_admin_cards_message(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass


async def delete_saved_admin_cards_message(state: FSMContext, user_id: int | None, bot) -> None:
    if user_id is None:
        return

    data = await state.get_data()
    saved_messages: set[tuple[int, int]] = set()

    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if chat_id and message_id:
        saved_messages.add((int(chat_id), int(message_id)))

    active_message = ACTIVE_ADMIN_CARDS_MESSAGES.pop(user_id, None)

    if active_message is not None:
        saved_messages.add(active_message)

    for saved_chat_id, saved_message_id in saved_messages:
        await delete_admin_cards_message(bot, saved_chat_id, saved_message_id)


ADMIN_CARDS_STATE_FILTER = StateFilter(
    AdminCardsStates.waiting_for_image,
    AdminCardsStates.waiting_for_name,
    AdminCardsStates.waiting_for_overall,
    AdminCardsStates.waiting_for_team,
    AdminCardsStates.waiting_for_country,
    AdminCardsStates.waiting_for_collection,
    AdminCardsStates.waiting_for_search,
    AdminCardsStates.waiting_for_edit_value,
    AdminCardsStates.waiting_for_edit_image,
)


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


async def edit_admin_message(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await message.edit_text(text, reply_markup=reply_markup)
    remember_admin_cards_message(callback.from_user.id, message)


async def edit_state_message(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            remember_admin_cards_message(message.from_user.id if message.from_user else None, message)
            return
        except Exception:
            pass

    user_id = message.from_user.id if message.from_user else None
    await delete_saved_admin_cards_message(state, user_id, message.bot)
    sent_message = await message.answer(text, reply_markup=reply_markup)
    remember_admin_cards_message(user_id, sent_message)
    await state.update_data(chat_id=sent_message.chat.id, message_id=sent_message.message_id)


async def show_cards_page(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    cards_page = await get_cards_page(
        page=page,
        per_page=ADMIN_CARDS_PER_PAGE,
        search=search,
    )

    await edit_admin_message(
        callback,
        build_cards_page_text(cards_page),
        reply_markup=build_admin_cards_list_keyboard(
            cards=cards_page.cards,
            page=cards_page.page,
            pages_count=cards_page.pages_count,
            search=cards_page.search,
        ),
    )


async def show_card_profile(callback: CallbackQuery, card_id: int, page: int) -> None:
    card = await get_card_profile(card_id)

    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_card_profile_text(card),
        reply_markup=build_admin_card_profile_keyboard(
            card_id=card.id,
            page=page,
            active=card.active,
        ),
    )


async def save_card_image(message: Message) -> str | None:
    CARD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    now_value = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0

    if message.photo:
        photo = message.photo[-1]
        file_name = f"card_{now_value}_{user_id}_{photo.file_unique_id}.jpg"
        file_path = CARD_IMAGES_DIR / file_name
        await message.bot.download(photo, destination=file_path)
        return file_path.as_posix()

    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        suffix = Path(message.document.file_name or "card.png").suffix.lower()

        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"

        file_name = f"card_{now_value}_{user_id}_{message.document.file_unique_id}{suffix}"
        file_path = CARD_IMAGES_DIR / file_name
        await message.bot.download(message.document, destination=file_path)
        return file_path.as_posix()

    return None


async def get_draft_from_state(state: FSMContext) -> CardDraft | None:
    data = await state.get_data()
    required_fields = [
        "image_path",
        "name",
        "position",
        "overall",
        "team",
        "country",
        "salary",
        "collection_name",
        "rarity",
    ]

    if any(field not in data for field in required_fields):
        return None

    return CardDraft(
        image_path=str(data["image_path"]),
        name=str(data["name"]),
        position=str(data["position"]),
        overall=int(data["overall"]),
        team=str(data["team"]),
        country=str(data["country"]),
        salary=int(data.get("salary", 0)),
        collection_name=str(data["collection_name"]),
        rarity=str(data["rarity"]),
    )


@router.message(F.text == ADMIN_CARDS_BUTTON_TEXT)
async def admin_cards_button(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    user_id = message.from_user.id if message.from_user else None
    await delete_saved_admin_cards_message(state, user_id, message.bot)
    await state.clear()
    await safe_delete_message(message)
    sent_message = await message.answer(
        ADMIN_CARDS_MAIN_TEXT,
        reply_markup=build_admin_cards_main_keyboard(),
    )
    remember_admin_cards_message(user_id, sent_message)


@router.message(ADMIN_CARDS_STATE_FILTER, F.text.in_(ADMIN_MAIN_TEXTS))
async def admin_cards_leave_to_admin_menu(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    user_id = message.from_user.id if message.from_user else None
    await delete_saved_admin_cards_message(state, user_id, message.bot)
    await state.clear()
    await safe_delete_message(message)

    sent_message = await message.answer(
        "🏒 Главное меню админ-панели\n\nВыбери нужный раздел ниже.",
        reply_markup=build_admin_main_keyboard(user_id),
    )
    remember_admin_cards_message(user_id, sent_message)


@router.callback_query(F.data == "admin_cards:main")
async def admin_cards_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await edit_admin_message(
        callback,
        ADMIN_CARDS_MAIN_TEXT,
        reply_markup=build_admin_cards_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cards:add")
async def admin_cards_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await state.set_state(AdminCardsStates.waiting_for_image)
    await edit_admin_message(
        callback,
        ADMIN_CARDS_IMAGE_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminCardsStates.waiting_for_image)
async def admin_cards_image(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    image_path = await save_card_image(message)
    await safe_delete_message(message)

    if image_path is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_IMAGE_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(image_path=image_path)
    await state.set_state(AdminCardsStates.waiting_for_name)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_NAME_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )


@router.message(AdminCardsStates.waiting_for_name)
async def admin_cards_name(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    name = validate_name(message.text or "")

    if name is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_NAME_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(name=name)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_POSITION_TEXT,
        reply_markup=build_admin_cards_positions_keyboard(),
    )


@router.callback_query(F.data.startswith("admin_cards:add_position:"))
async def admin_cards_position(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    position = callback.data.split(":")[-1] if callback.data else ""
    await state.update_data(position=position)
    await state.set_state(AdminCardsStates.waiting_for_overall)
    await edit_admin_message(
        callback,
        ADMIN_CARDS_OVERALL_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminCardsStates.waiting_for_overall)
async def admin_cards_overall(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    overall = validate_overall(message.text or "")

    if overall is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_OVERALL_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(overall=overall)
    await state.set_state(AdminCardsStates.waiting_for_team)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_TEAM_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )


@router.message(AdminCardsStates.waiting_for_team)
async def admin_cards_team(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    team = validate_short_text(message.text or "")

    if team is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_TEXT_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(team=team)
    await state.set_state(AdminCardsStates.waiting_for_country)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_COUNTRY_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )


@router.message(AdminCardsStates.waiting_for_country)
async def admin_cards_country(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    country = validate_short_text(message.text or "")

    if country is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_TEXT_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(country=country)
    await state.set_state(AdminCardsStates.waiting_for_salary)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_SALARY_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )


@router.message(AdminCardsStates.waiting_for_salary)
async def admin_cards_salary(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    from app.services.salary import parse_salary

    salary = parse_salary(message.text or "")
    if salary is None:
        await edit_state_message(
            message,
            state,
            "💵 Введи зарплату в миллионах, например 5.5. Число от 0 до 200.",
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(salary=salary)
    await state.set_state(AdminCardsStates.waiting_for_collection)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_COLLECTION_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )


@router.message(AdminCardsStates.waiting_for_collection)
async def admin_cards_collection(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    collection_name = validate_short_text(message.text or "")

    if collection_name is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_TEXT_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    await state.update_data(collection_name=collection_name)
    await edit_state_message(
        message,
        state,
        ADMIN_CARDS_RARITY_TEXT,
        reply_markup=build_admin_cards_rarities_keyboard(),
    )


@router.callback_query(F.data.startswith("admin_cards:add_rarity:"))
async def admin_cards_rarity(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    rarity = callback.data.split(":")[-1] if callback.data else ""
    await state.update_data(rarity=rarity)
    draft = await get_draft_from_state(state)

    if draft is None:
        await state.clear()
        await edit_admin_message(
            callback,
            ADMIN_CARDS_MAIN_TEXT,
            reply_markup=build_admin_cards_main_keyboard(),
        )
        await callback.answer("Начни добавление заново")
        return

    await edit_admin_message(
        callback,
        build_card_draft_text(draft),
        reply_markup=build_admin_cards_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cards:save")
async def admin_cards_save(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    draft = await get_draft_from_state(state)

    if draft is None:
        await state.clear()
        await callback.answer("Начни добавление заново", show_alert=True)
        return

    card = await create_card(draft)
    await state.clear()
    await edit_admin_message(
        callback,
        f"{ADMIN_CARDS_SAVED_TEXT}\n\n{build_card_profile_text(card)}",
        reply_markup=build_admin_card_profile_keyboard(card.id, page=1, active=card.active),
    )
    await callback.answer("Карточка сохранена")


@router.callback_query(F.data.startswith("admin_cards:list:"))
async def admin_cards_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_cards_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data == "admin_cards:search")
async def admin_cards_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await state.set_state(AdminCardsStates.waiting_for_search)
    await edit_admin_message(
        callback,
        ADMIN_CARDS_SEARCH_TEXT,
        reply_markup=build_admin_cards_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminCardsStates.waiting_for_search)
async def admin_cards_search_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    search = validate_short_text(message.text or "")

    if search is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_TEXT_TEXT,
            reply_markup=build_admin_cards_cancel_keyboard(),
        )
        return

    ADMIN_CARDS_SEARCH_CACHE[message.from_user.id] = search
    await state.clear()
    cards_page = await get_cards_page(
        page=1,
        per_page=ADMIN_CARDS_PER_PAGE,
        search=search,
    )
    await edit_state_message(
        message,
        state,
        build_cards_page_text(cards_page),
        reply_markup=build_admin_cards_list_keyboard(
            cards=cards_page.cards,
            page=cards_page.page,
            pages_count=cards_page.pages_count,
            search=cards_page.search,
        ),
    )


@router.callback_query(F.data.startswith("admin_cards:search_list:"))
async def admin_cards_search_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    search = ADMIN_CARDS_SEARCH_CACHE.get(callback.from_user.id)
    await show_cards_page(callback, page=page, search=search)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:view:"))
async def admin_cards_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    await show_card_profile(callback, card_id=card_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:toggle:"))
async def admin_cards_toggle(callback: CallbackQuery) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    card = await toggle_card_active(card_id)

    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_card_profile_text(card),
        reply_markup=build_admin_card_profile_keyboard(card.id, page=page, active=card.active),
    )
    await callback.answer("Статус карточки обновлён")


@router.callback_query(F.data.startswith("admin_cards:edit:"))
async def admin_cards_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    card = await get_card_profile(card_id)

    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_card_edit_text(card),
        reply_markup=build_admin_card_edit_keyboard(card.id, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:edit_text:"))
async def admin_cards_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    field = parts[4]

    await state.set_state(AdminCardsStates.waiting_for_edit_value)
    await state.update_data(card_id=card_id, page=page, field=field)
    await edit_admin_message(
        callback,
        build_edit_value_text(get_edit_field_title(field)),
        reply_markup=build_admin_card_back_keyboard(card_id, page),
    )
    await callback.answer()


@router.message(AdminCardsStates.waiting_for_edit_value)
async def admin_cards_edit_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await safe_delete_message(message)
    data = await state.get_data()
    card_id = int(data["card_id"])
    page = int(data["page"])
    field = str(data["field"])
    value = message.text or ""

    if field == "overall":
        card = await update_card_overall(card_id, value)
        error_text = ADMIN_CARDS_BAD_OVERALL_TEXT
    elif field == "salary":
        card = await update_card_salary(card_id, value)
        error_text = "💵 Введи зарплату в миллионах, например 5.5 (число от 0 до 200)."
    elif field == "collection":
        card = await update_card_collection(card_id, value)
        error_text = ADMIN_CARDS_BAD_TEXT_TEXT
    else:
        card = await update_card_text_field(card_id, field, value)
        error_text = ADMIN_CARDS_BAD_NAME_TEXT if field == "name" else ADMIN_CARDS_BAD_TEXT_TEXT

    if card is None:
        await edit_state_message(
            message,
            state,
            error_text,
            reply_markup=build_admin_card_back_keyboard(card_id, page),
        )
        return

    await state.clear()
    await edit_state_message(
        message,
        state,
        build_card_profile_text(card),
        reply_markup=build_admin_card_profile_keyboard(card.id, page=page, active=card.active),
    )


@router.callback_query(F.data.startswith("admin_cards:edit_position:"))
async def admin_cards_edit_position(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    await edit_admin_message(
        callback,
        ADMIN_CARDS_POSITION_TEXT,
        reply_markup=build_admin_cards_positions_keyboard(prefix=f"admin_cards:set_position:{card_id}:{page}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:set_position:"))
async def admin_cards_set_position(callback: CallbackQuery) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    position = parts[4]
    card = await update_card_position(card_id, position)

    if card is None:
        await callback.answer("Позиция не выбрана", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_card_profile_text(card),
        reply_markup=build_admin_card_profile_keyboard(card.id, page=page, active=card.active),
    )
    await callback.answer("Позиция обновлена")


@router.callback_query(F.data.startswith("admin_cards:edit_rarity:"))
async def admin_cards_edit_rarity(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    await edit_admin_message(
        callback,
        ADMIN_CARDS_RARITY_TEXT,
        reply_markup=build_admin_cards_rarities_keyboard(prefix=f"admin_cards:set_rarity:{card_id}:{page}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:set_rarity:"))
async def admin_cards_set_rarity(callback: CallbackQuery) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    rarity = parts[4]
    card = await update_card_rarity(card_id, rarity)

    if card is None:
        await callback.answer("Редкость не выбрана", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_card_profile_text(card),
        reply_markup=build_admin_card_profile_keyboard(card.id, page=page, active=card.active),
    )
    await callback.answer("Редкость обновлена")


@router.callback_query(F.data.startswith("admin_cards:edit_image:"))
async def admin_cards_edit_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    card_id = int(parts[2])
    page = int(parts[3])
    card = await get_card_profile(card_id)

    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    await state.set_state(AdminCardsStates.waiting_for_edit_image)
    await state.update_data(card_id=card_id, page=page)
    await edit_admin_message(
        callback,
        build_edit_image_text(card),
        reply_markup=build_admin_card_back_keyboard(card_id, page),
    )
    await callback.answer()


@router.message(AdminCardsStates.waiting_for_edit_image)
async def admin_cards_edit_image_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    image_path = await save_card_image(message)
    await safe_delete_message(message)
    data = await state.get_data()
    card_id = int(data["card_id"])
    page = int(data["page"])

    if image_path is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_BAD_IMAGE_TEXT,
            reply_markup=build_admin_card_back_keyboard(card_id, page),
        )
        return

    card = await update_card_image_path(card_id, image_path)
    await state.clear()

    if card is None:
        await edit_state_message(
            message,
            state,
            ADMIN_CARDS_EMPTY_TEXT,
            reply_markup=build_admin_cards_main_keyboard(),
        )
        return

    await edit_state_message(
        message,
        state,
        build_card_profile_text(card),
        reply_markup=build_admin_card_profile_keyboard(card.id, page=page, active=card.active),
    )



@router.callback_query(F.data.startswith("admin_cards:owners:"))
async def admin_cards_owners(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    if len(parts) < 4:
        await callback.answer("Некорректная карточка", show_alert=True)
        return
    card_id = int(parts[2])
    page = int(parts[3])
    owners = await get_card_owners_page(card_id, page=page)
    if owners is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return
    await edit_admin_message(callback, build_card_owners_text(owners), reply_markup=build_admin_card_owners_keyboard(owners))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:owner:"))
async def admin_cards_owner_copies(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    if len(parts) < 6:
        await callback.answer("Некорректный владелец", show_alert=True)
        return
    card_id = int(parts[2])
    owner_user_id = int(parts[3])
    owners_page = int(parts[4])
    copies_page = int(parts[5])
    copies = await get_card_owner_copies_page(card_id, owner_user_id, page=copies_page)
    if copies is None:
        await callback.answer("Владелец или карточка не найдены", show_alert=True)
        return
    if copies.total_count <= 0:
        owners = await get_card_owners_page(card_id, page=owners_page)
        if owners is None:
            await callback.answer("Карточка не найдена", show_alert=True)
            return
        await edit_admin_message(callback, build_card_owners_text(owners), reply_markup=build_admin_card_owners_keyboard(owners))
        await callback.answer("У игрока больше нет этой карты")
        return
    await edit_admin_message(
        callback,
        build_card_owner_copies_text(copies),
        reply_markup=build_admin_card_owner_copies_keyboard(copies, owners_page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:copy:"))
async def admin_cards_owner_copy(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    if len(parts) < 7:
        await callback.answer("Некорректный экземпляр", show_alert=True)
        return
    card_id = int(parts[2])
    owner_user_id = int(parts[3])
    owners_page = int(parts[4])
    user_card_id = int(parts[5])
    copies_page = int(parts[6])
    card = await get_card_profile(card_id)
    copy = await get_owned_card_copy(user_card_id)
    if card is None or copy is None or copy.user_id != owner_user_id:
        await callback.answer("Экземпляр уже недоступен", show_alert=True)
        return
    await edit_admin_message(
        callback,
        build_owned_card_copy_text(card, copy),
        reply_markup=build_admin_card_copy_keyboard(card_id, owner_user_id, owners_page, user_card_id, copies_page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:revoke_confirm:"))
async def admin_cards_revoke_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    if len(parts) < 7:
        await callback.answer("Некорректный экземпляр", show_alert=True)
        return
    card_id = int(parts[2])
    owner_user_id = int(parts[3])
    owners_page = int(parts[4])
    user_card_id = int(parts[5])
    copies_page = int(parts[6])
    card = await get_card_profile(card_id)
    copy = await get_owned_card_copy(user_card_id)
    if card is None or copy is None or copy.user_id != owner_user_id:
        await callback.answer("Экземпляр уже недоступен", show_alert=True)
        return
    await edit_admin_message(
        callback,
        build_revoke_owned_card_confirm_text(card, copy),
        reply_markup=build_admin_card_revoke_confirm_keyboard(card_id, owner_user_id, owners_page, user_card_id, copies_page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cards:revoke_do:"))
async def admin_cards_revoke_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    if len(parts) < 7:
        await callback.answer("Некорректный экземпляр", show_alert=True)
        return
    card_id = int(parts[2])
    owner_user_id = int(parts[3])
    owners_page = int(parts[4])
    user_card_id = int(parts[5])
    result = await revoke_owned_card_copy(user_card_id, admin_telegram_id=callback.from_user.id)
    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    copies = await get_card_owner_copies_page(card_id, owner_user_id, page=1)
    if copies is not None and copies.total_count > 0:
        await edit_admin_message(
            callback,
            f"✅ <b>Карточка забрана</b>\n\n{build_card_owner_copies_text(copies)}",
            reply_markup=build_admin_card_owner_copies_keyboard(copies, owners_page),
        )
    else:
        owners = await get_card_owners_page(card_id, page=owners_page)
        if owners is None:
            await callback.answer("Карточка не найдена", show_alert=True)
            return
        await edit_admin_message(
            callback,
            f"✅ <b>Карточка забрана у {result.owner_nickname}</b>\n\n{build_card_owners_text(owners)}",
            reply_markup=build_admin_card_owners_keyboard(owners),
        )
    await callback.answer("Карточка забрана")


@router.callback_query(F.data == "admin_cards:collections")
async def admin_cards_collections(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    collections = await get_collections()
    await edit_admin_message(
        callback,
        build_collections_text(collections),
        reply_markup=build_admin_collections_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cards:cancel")
async def admin_cards_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    user_id = callback.from_user.id
    message = callback.message

    await delete_saved_admin_cards_message(state, user_id, callback.bot)
    await state.clear()

    if isinstance(message, Message):
        sent_message = await callback.bot.send_message(
            chat_id=message.chat.id,
            text=ADMIN_CARDS_MAIN_TEXT,
            reply_markup=build_admin_cards_main_keyboard(),
        )
        remember_admin_cards_message(user_id, sent_message)

    await callback.answer("Отменено")


@router.callback_query(F.data == "admin_cards:page_info")
async def admin_cards_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
