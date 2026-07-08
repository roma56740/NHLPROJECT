from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_users import (
    ADMIN_USER_CARDS_PER_PAGE,
    ADMIN_USERS_PER_PAGE,
    build_admin_user_currency_keyboard,
    build_admin_user_give_card_keyboard,
    build_admin_user_leagues_keyboard,
    build_admin_user_profile_keyboard,
    build_admin_users_cancel_keyboard,
    build_admin_users_list_keyboard,
    build_admin_users_main_keyboard,
)
from app.keyboards.packs import (
    ADMIN_GIVE_PACKS_PER_PAGE,
    build_admin_give_pack_keyboard,
    build_admin_pack_cancel_keyboard,
)
from app.services.admin_users import (
    add_currency_to_user,
    get_admin_user_profile,
    get_users_page,
    toggle_user_ban,
    toggle_user_premium_pass,
    toggle_user_trade_block,
    update_user_league,
)
from app.services.admin_notifications import (
    build_card_reward_notification,
    build_currency_reward_notification,
    build_pack_reward_notification,
    build_premium_reward_notification,
    send_admin_reward_notification,
)
from app.services.packs import get_pack_choice_page, get_pack_info, give_pack_to_user
from app.services.user_cards import get_card_choice_page, give_card_to_user
from app.states.admin_users import AdminUsersStates
from app.texts.admin_users import (
    ADMIN_USERS_CURRENCY_AMOUNT_TEXT,
    ADMIN_USERS_CURRENCY_TEXT,
    ADMIN_USERS_GIVE_CARD_SEARCH_TEXT,
    ADMIN_USERS_LEAGUE_TEXT,
    ADMIN_USERS_MAIN_TEXT,
    ADMIN_USERS_SEARCH_TEXT,
    build_admin_give_card_page_text,
    build_admin_user_profile_text,
    build_admin_users_page_text,
    get_currency_title,
)
from app.texts.packs import (
    ADMIN_GIVE_PACK_SEARCH_TEXT,
    build_admin_give_pack_page_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()

ADMIN_USERS_BUTTON_TEXT = "👥 Пользователи"
ADMIN_USERS_SEARCH_CACHE: dict[int, str] = {}
ADMIN_GIVE_CARD_SEARCH_CACHE: dict[tuple[int, int], str] = {}
ADMIN_GIVE_PACK_SEARCH_CACHE: dict[tuple[int, int], str] = {}


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


async def show_users_page(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    users_page = await get_users_page(
        page=page,
        per_page=ADMIN_USERS_PER_PAGE,
        search=search,
    )

    await edit_admin_message(
        callback,
        build_admin_users_page_text(users_page),
        reply_markup=build_admin_users_list_keyboard(
            users=users_page.users,
            page=users_page.page,
            pages_count=users_page.pages_count,
            search=users_page.search,
        ),
    )


async def show_user_profile(callback: CallbackQuery, user_id: int, page: int) -> None:
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )


async def show_give_card_page(
    callback: CallbackQuery,
    user_id: int,
    user_page: int,
    card_page: int = 1,
    search: str | None = None,
) -> None:
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    cards_page = await get_card_choice_page(
        page=card_page,
        per_page=ADMIN_USER_CARDS_PER_PAGE,
        search=search,
    )

    await edit_admin_message(
        callback,
        build_admin_give_card_page_text(cards_page, nickname=profile.nickname),
        reply_markup=build_admin_user_give_card_keyboard(
            user_id=user_id,
            user_page=user_page,
            cards=cards_page.cards,
            card_page=cards_page.page,
            pages_count=cards_page.pages_count,
            search=cards_page.search,
        ),
    )


async def show_give_pack_page(
    callback: CallbackQuery,
    user_id: int,
    user_page: int,
    pack_page: int = 1,
    search: str | None = None,
) -> None:
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    packs_page = await get_pack_choice_page(
        page=pack_page,
        per_page=ADMIN_GIVE_PACKS_PER_PAGE,
        search=search,
    )

    await edit_admin_message(
        callback,
        build_admin_give_pack_page_text(packs_page, nickname=profile.nickname),
        reply_markup=build_admin_give_pack_keyboard(
            user_id=user_id,
            user_page=user_page,
            packs=packs_page.packs,
            pack_page=packs_page.page,
            pages_count=packs_page.pages_count,
            search=packs_page.search,
        ),
    )


@router.message(F.text == ADMIN_USERS_BUTTON_TEXT)
async def admin_users_button(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await state.clear()
    await safe_delete_message(message)
    await message.answer(
        ADMIN_USERS_MAIN_TEXT,
        reply_markup=build_admin_users_main_keyboard(),
    )


@router.callback_query(F.data == "admin_users:main")
async def admin_users_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await edit_admin_message(
        callback,
        ADMIN_USERS_MAIN_TEXT,
        reply_markup=build_admin_users_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:list:"))
async def admin_users_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_users_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:search_list:"))
async def admin_users_search_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    search = ADMIN_USERS_SEARCH_CACHE.get(callback.from_user.id)
    await show_users_page(callback, page=page, search=search)
    await callback.answer()


@router.callback_query(F.data == "admin_users:search")
async def admin_users_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.clear()
    await state.set_state(AdminUsersStates.search)
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await message.edit_text(
        ADMIN_USERS_SEARCH_TEXT,
        reply_markup=build_admin_users_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminUsersStates.search)
async def admin_users_search_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    search = message.text or ""
    await safe_delete_message(message)

    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    ADMIN_USERS_SEARCH_CACHE[message.from_user.id] = search
    users_page = await get_users_page(page=1, per_page=ADMIN_USERS_PER_PAGE, search=search)

    if chat_id and message_id:
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_admin_users_page_text(users_page),
            reply_markup=build_admin_users_list_keyboard(
                users=users_page.users,
                page=users_page.page,
                pages_count=users_page.pages_count,
                search=users_page.search,
            ),
        )
    else:
        await message.answer(
            build_admin_users_page_text(users_page),
            reply_markup=build_admin_users_list_keyboard(
                users=users_page.users,
                page=users_page.page,
                pages_count=users_page.pages_count,
                search=users_page.search,
            ),
        )

    await state.clear()


@router.callback_query(F.data.startswith("admin_users:view:"))
async def admin_users_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3])
    await show_user_profile(callback, user_id=user_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:give_card:"))
async def admin_users_give_card(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    user_page = int(parts[3])
    ADMIN_GIVE_CARD_SEARCH_CACHE.pop((callback.from_user.id, user_id), None)
    await show_give_card_page(callback, user_id=user_id, user_page=user_page, card_page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:give_card_list:"))
async def admin_users_give_card_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    card_page = int(parts[3])
    user_page = int(parts[4])
    search = ADMIN_GIVE_CARD_SEARCH_CACHE.get((callback.from_user.id, user_id))
    await show_give_card_page(
        callback,
        user_id=user_id,
        user_page=user_page,
        card_page=card_page,
        search=search,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:give_card_search:"))
async def admin_users_give_card_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    user_page = int(parts[3])

    await state.clear()
    await state.set_state(AdminUsersStates.give_card_search)
    await state.update_data(
        user_id=user_id,
        user_page=user_page,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await message.edit_text(
        ADMIN_USERS_GIVE_CARD_SEARCH_TEXT,
        reply_markup=build_admin_users_cancel_keyboard(user_id=user_id, page=user_page),
    )
    await callback.answer()


@router.message(AdminUsersStates.give_card_search)
async def admin_users_give_card_search_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    search = message.text or ""
    await safe_delete_message(message)

    data = await state.get_data()
    user_id = int(data["user_id"])
    user_page = int(data.get("user_page", 1))
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    ADMIN_GIVE_CARD_SEARCH_CACHE[(message.from_user.id, user_id)] = search

    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await message.answer("🏒 Игрок не найден.")
        await state.clear()
        return

    cards_page = await get_card_choice_page(
        page=1,
        per_page=ADMIN_USER_CARDS_PER_PAGE,
        search=search,
    )

    text = build_admin_give_card_page_text(cards_page, nickname=profile.nickname)
    keyboard = build_admin_user_give_card_keyboard(
        user_id=user_id,
        user_page=user_page,
        cards=cards_page.cards,
        card_page=cards_page.page,
        pages_count=cards_page.pages_count,
        search=cards_page.search,
    )

    if chat_id and message_id:
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
        )
    else:
        await message.answer(text, reply_markup=keyboard)

    await state.clear()


@router.callback_query(F.data.startswith("admin_users:give_card_do:"))
async def admin_users_give_card_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    card_id = int(parts[3])
    user_page = int(parts[4])

    player_card = await give_card_to_user(
        user_id=user_id,
        card_id=card_id,
        obtained_from="admin",
    )

    if player_card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=user_page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )
    await send_admin_reward_notification(
        callback.bot,
        profile.telegram_id,
        build_card_reward_notification(player_card),
    )
    await callback.answer("Карточка выдана")


@router.callback_query(F.data.startswith("admin_users:give_pack:"))
async def admin_users_give_pack(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    user_page = int(parts[3])
    ADMIN_GIVE_PACK_SEARCH_CACHE.pop((callback.from_user.id, user_id), None)
    await show_give_pack_page(callback, user_id=user_id, user_page=user_page, pack_page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:give_pack_list:"))
async def admin_users_give_pack_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    pack_page = int(parts[3])
    user_page = int(parts[4])
    search = ADMIN_GIVE_PACK_SEARCH_CACHE.get((callback.from_user.id, user_id))
    await show_give_pack_page(
        callback,
        user_id=user_id,
        user_page=user_page,
        pack_page=pack_page,
        search=search,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:give_pack_search:"))
async def admin_users_give_pack_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    user_page = int(parts[3])

    await state.clear()
    await state.set_state(AdminUsersStates.give_pack_search)
    await state.update_data(
        user_id=user_id,
        user_page=user_page,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await message.edit_text(
        ADMIN_GIVE_PACK_SEARCH_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(user_id=user_id, page=user_page),
    )
    await callback.answer()


@router.message(AdminUsersStates.give_pack_search)
async def admin_users_give_pack_search_value(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    search = message.text or ""
    await safe_delete_message(message)

    data = await state.get_data()
    user_id = int(data["user_id"])
    user_page = int(data.get("user_page", 1))
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    ADMIN_GIVE_PACK_SEARCH_CACHE[(message.from_user.id, user_id)] = search

    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await message.answer("🏒 Игрок не найден.")
        await state.clear()
        return

    packs_page = await get_pack_choice_page(
        page=1,
        per_page=ADMIN_GIVE_PACKS_PER_PAGE,
        search=search,
    )

    text = build_admin_give_pack_page_text(packs_page, nickname=profile.nickname)
    keyboard = build_admin_give_pack_keyboard(
        user_id=user_id,
        user_page=user_page,
        packs=packs_page.packs,
        pack_page=packs_page.page,
        pages_count=packs_page.pages_count,
        search=packs_page.search,
    )

    if chat_id and message_id:
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
        )
    else:
        await message.answer(text, reply_markup=keyboard)

    await state.clear()


@router.callback_query(F.data.startswith("admin_users:give_pack_do:"))
async def admin_users_give_pack_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    pack_id = int(parts[3])
    user_page = int(parts[4])

    success = await give_pack_to_user(
        user_id=user_id,
        pack_id=pack_id,
        quantity=1,
    )

    if not success:
        await callback.answer("Пак не найден", show_alert=True)
        return

    pack = await get_pack_info(pack_id)
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=user_page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )
    if pack is not None:
        await send_admin_reward_notification(
            callback.bot,
            profile.telegram_id,
            build_pack_reward_notification(pack.name, quantity=1),
        )
    await callback.answer("Пак выдан")


@router.callback_query(F.data.startswith("admin_users:currency:"))
async def admin_users_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3])
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        ADMIN_USERS_CURRENCY_TEXT.format(nickname=profile.nickname),
        reply_markup=build_admin_user_currency_keyboard(user_id=profile.id, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:currency_code:"))
async def admin_users_currency_code(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    currency_code = parts[3]
    page = int(parts[4])

    await state.clear()
    await state.set_state(AdminUsersStates.currency_amount)
    await state.update_data(
        user_id=user_id,
        currency_code=currency_code,
        page=page,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )

    await message.edit_text(
        ADMIN_USERS_CURRENCY_AMOUNT_TEXT.format(currency_title=get_currency_title(currency_code)),
        reply_markup=build_admin_users_cancel_keyboard(user_id=user_id, page=page),
    )
    await callback.answer()


@router.message(AdminUsersStates.currency_amount)
async def admin_users_currency_amount(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    raw_amount = (message.text or "").replace(" ", "").strip()
    await safe_delete_message(message)

    if not raw_amount.lstrip("-").isdigit():
        await message.answer("💱 Отправь сумму числом, например 10000.")
        return

    amount = int(raw_amount)
    data = await state.get_data()
    user_id = int(data["user_id"])
    currency_code = str(data["currency_code"])
    page = int(data.get("page", 1))
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    profile = await add_currency_to_user(
        user_id=user_id,
        currency_code=currency_code,
        amount=amount,
    )

    if profile is None:
        await message.answer("🏒 Игрок не найден.")
        await state.clear()
        return

    if chat_id and message_id:
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_admin_user_profile_text(profile),
            reply_markup=build_admin_user_profile_keyboard(
                user_id=profile.id,
                page=page,
                premium_pass=profile.hockey_pass_premium_unlocked,
                is_banned=profile.is_banned,
                trade_blocked=profile.trade_blocked,
            ),
        )
    else:
        await message.answer(
            build_admin_user_profile_text(profile),
            reply_markup=build_admin_user_profile_keyboard(
                user_id=profile.id,
                page=page,
                premium_pass=profile.hockey_pass_premium_unlocked,
                is_banned=profile.is_banned,
                trade_blocked=profile.trade_blocked,
            ),
        )

    if amount != 0:
        await send_admin_reward_notification(
            message.bot,
            profile.telegram_id,
            build_currency_reward_notification(get_currency_title(currency_code), amount),
        )
    await state.clear()


@router.callback_query(F.data.startswith("admin_users:league:"))
async def admin_users_league(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3])
    profile = await get_admin_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        ADMIN_USERS_LEAGUE_TEXT.format(nickname=profile.nickname, league=profile.league),
        reply_markup=build_admin_user_leagues_keyboard(user_id=profile.id, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users:set_league:"))
async def admin_users_set_league(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    league = parts[3]
    page = int(parts[4])
    profile = await update_user_league(user_id=user_id, league=league)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )
    await callback.answer("Лига обновлена")


@router.callback_query(F.data.startswith("admin_users:premium:"))
async def admin_users_premium(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3])
    previous_profile = await get_admin_user_profile(user_id)
    was_premium = bool(previous_profile and previous_profile.hockey_pass_premium_unlocked)
    profile = await toggle_user_premium_pass(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )
    if profile.hockey_pass_premium_unlocked and not was_premium:
        await send_admin_reward_notification(
            callback.bot,
            profile.telegram_id,
            build_premium_reward_notification(profile.hockey_pass_title),
        )
    await callback.answer("Premium Pass обновлён")


@router.callback_query(F.data.startswith("admin_users:trade_block:"))
async def admin_users_trade_block(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3])
    profile = await toggle_user_trade_block(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )
    await callback.answer("Статус обменов обновлён")


@router.callback_query(F.data.startswith("admin_users:ban:"))
async def admin_users_ban(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3])
    profile = await toggle_user_ban(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_user_profile_text(profile),
        reply_markup=build_admin_user_profile_keyboard(
            user_id=profile.id,
            page=page,
            premium_pass=profile.hockey_pass_premium_unlocked,
            is_banned=profile.is_banned,
            trade_blocked=profile.trade_blocked,
        ),
    )
    await callback.answer("Статус игрока обновлён")


@router.callback_query(F.data == "admin_users:page_info")
async def admin_users_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
