from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_wallets import (
    ADMIN_WALLETS_USERS_PER_PAGE,
    build_admin_wallet_action_keyboard,
    build_admin_wallet_cancel_keyboard,
    build_admin_wallet_currencies_keyboard,
    build_admin_wallet_user_keyboard,
    build_admin_wallets_main_keyboard,
    build_admin_wallets_users_keyboard,
)
from app.services.admin_notifications import (
    build_currency_reward_notification,
    send_admin_reward_notification,
)
from app.services.admin_wallets import (
    change_wallet_balance,
    get_wallet_currencies,
    get_wallet_currency,
    get_wallet_user_profile,
    get_wallet_users_page,
)
from app.states.admin_wallets import AdminWalletsStates
from app.texts.admin_wallets import (
    ADMIN_WALLETS_BAD_AMOUNT_TEXT,
    ADMIN_WALLETS_MAIN_TEXT,
    ADMIN_WALLETS_SEARCH_TEXT,
    build_admin_wallet_action_text,
    build_admin_wallet_amount_text,
    build_admin_wallet_currencies_text,
    build_admin_wallet_success_text,
    build_admin_wallet_user_text,
    build_admin_wallets_users_page_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()

ADMIN_WALLETS_BUTTON_TEXT = "💱 Валюты"
ADMIN_WALLETS_SEARCH_CACHE: dict[int, str] = {}


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


async def edit_stored_message(message: Message, chat_id: int, message_id: int, text: str, reply_markup=None) -> None:
    try:
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


async def show_wallet_users_page(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    users_page = await get_wallet_users_page(
        page=page,
        per_page=ADMIN_WALLETS_USERS_PER_PAGE,
        search=search,
    )
    await edit_admin_message(
        callback,
        build_admin_wallets_users_page_text(users_page),
        reply_markup=build_admin_wallets_users_keyboard(
            users=users_page.users,
            page=users_page.page,
            pages_count=users_page.pages_count,
            search=users_page.search,
        ),
    )


async def show_wallet_user(callback: CallbackQuery, user_id: int, page: int) -> None:
    profile = await get_wallet_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_wallet_user_text(profile),
        reply_markup=build_admin_wallet_user_keyboard(user_id=user_id, page=page),
    )


@router.message(F.text == ADMIN_WALLETS_BUTTON_TEXT)
async def admin_wallets_button(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await state.clear()
    await safe_delete_message(message)
    await message.answer(
        ADMIN_WALLETS_MAIN_TEXT,
        reply_markup=build_admin_wallets_main_keyboard(),
    )


@router.callback_query(F.data == "admin_wallets:main")
async def admin_wallets_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await edit_admin_message(
        callback,
        ADMIN_WALLETS_MAIN_TEXT,
        reply_markup=build_admin_wallets_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallets:users:"))
async def admin_wallets_users(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_wallet_users_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallets:search_users:"))
async def admin_wallets_search_users(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    search = ADMIN_WALLETS_SEARCH_CACHE.get(callback.from_user.id)
    await show_wallet_users_page(callback, page=page, search=search)
    await callback.answer()


@router.callback_query(F.data == "admin_wallets:search")
async def admin_wallets_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.clear()
    await state.set_state(AdminWalletsStates.search)
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await message.edit_text(
        ADMIN_WALLETS_SEARCH_TEXT,
        reply_markup=build_admin_wallet_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminWalletsStates.search)
async def admin_wallets_search_result(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    data = await state.get_data()
    chat_id = int(data.get("chat_id", message.chat.id))
    message_id = int(data.get("message_id", 0))
    search = (message.text or "").strip()

    await safe_delete_message(message)
    await state.clear()
    ADMIN_WALLETS_SEARCH_CACHE[message.from_user.id] = search

    users_page = await get_wallet_users_page(
        page=1,
        per_page=ADMIN_WALLETS_USERS_PER_PAGE,
        search=search,
    )
    await edit_stored_message(
        message,
        chat_id=chat_id,
        message_id=message_id,
        text=build_admin_wallets_users_page_text(users_page),
        reply_markup=build_admin_wallets_users_keyboard(
            users=users_page.users,
            page=users_page.page,
            pages_count=users_page.pages_count,
            search=users_page.search,
        ),
    )


@router.callback_query(F.data.startswith("admin_wallets:view:"))
async def admin_wallets_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    _, _, user_id, page = callback.data.split(":")
    await show_wallet_user(callback, user_id=int(user_id), page=int(page))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallets:currencies:"))
async def admin_wallets_currencies(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    _, _, user_id, page = callback.data.split(":")
    profile = await get_wallet_user_profile(int(user_id))

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    currencies = await get_wallet_currencies()
    await edit_admin_message(
        callback,
        build_admin_wallet_currencies_text(profile),
        reply_markup=build_admin_wallet_currencies_keyboard(
            user_id=int(user_id),
            page=int(page),
            currencies=currencies,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallets:currency:"))
async def admin_wallets_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    _, _, user_id, currency_code, page = callback.data.split(":")
    profile = await get_wallet_user_profile(int(user_id))
    currency = await get_wallet_currency(currency_code)

    if profile is None or currency is None:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_admin_wallet_action_text(profile, currency),
        reply_markup=build_admin_wallet_action_keyboard(
            user_id=int(user_id),
            currency_code=currency_code,
            page=int(page),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallets:action:"))
async def admin_wallets_action(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    _, _, user_id, currency_code, action, page = callback.data.split(":")
    profile = await get_wallet_user_profile(int(user_id))
    currency = await get_wallet_currency(currency_code)

    if profile is None or currency is None:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    await state.clear()
    await state.set_state(AdminWalletsStates.amount)
    await state.update_data(
        chat_id=message.chat.id,
        message_id=message.message_id,
        user_id=int(user_id),
        currency_code=currency_code,
        action=action,
        page=int(page),
    )
    await message.edit_text(
        build_admin_wallet_amount_text(profile, currency, action),
        reply_markup=build_admin_wallet_cancel_keyboard(user_id=int(user_id), page=int(page)),
    )
    await callback.answer()


@router.message(AdminWalletsStates.amount)
async def admin_wallets_amount(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    data = await state.get_data()
    chat_id = int(data.get("chat_id", message.chat.id))
    message_id = int(data.get("message_id", 0))
    user_id = int(data.get("user_id", 0))
    currency_code = str(data.get("currency_code", ""))
    action = str(data.get("action", ""))
    page = int(data.get("page", 1))
    raw_amount = (message.text or "").replace(" ", "").strip()

    await safe_delete_message(message)

    if not raw_amount.isdigit() or int(raw_amount) <= 0:
        await edit_stored_message(
            message,
            chat_id=chat_id,
            message_id=message_id,
            text=ADMIN_WALLETS_BAD_AMOUNT_TEXT,
            reply_markup=build_admin_wallet_cancel_keyboard(user_id=user_id, page=page),
        )
        return

    await state.clear()
    result = await change_wallet_balance(
        user_id=user_id,
        currency_code=currency_code,
        amount=int(raw_amount),
        action=action,
    )

    if result is None:
        await edit_stored_message(
            message,
            chat_id=chat_id,
            message_id=message_id,
            text="<b>⚠️ Баланс не изменён</b>\n\nПопробуй выбрать игрока и валюту заново.",
            reply_markup=build_admin_wallet_cancel_keyboard(),
        )
        return

    await edit_stored_message(
        message,
        chat_id=chat_id,
        message_id=message_id,
        text=build_admin_wallet_success_text(result),
        reply_markup=build_admin_wallet_user_keyboard(user_id=user_id, page=page),
    )
    signed_amount = result.amount if result.action == "add" else -result.amount
    await send_admin_reward_notification(
        message.bot,
        result.profile.telegram_id,
        build_currency_reward_notification(
            f"{result.currency.icon} {result.currency.name}",
            signed_amount,
        ),
    )


@router.callback_query(F.data == "admin_wallets:page_info")
async def admin_wallets_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
