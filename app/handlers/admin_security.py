from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_security import (
    SECURITY_CARDS_PER_PAGE,
    SECURITY_LOGS_PER_PAGE,
    SECURITY_USERS_PER_PAGE,
    build_admin_security_main_keyboard,
    build_security_cancel_keyboard,
    build_security_cards_keyboard,
    build_security_logs_keyboard,
    build_security_user_keyboard,
    build_security_users_keyboard,
)
from app.services.security import (
    get_security_logs_page,
    get_security_summary,
    get_security_user_cards_page,
    get_security_user_profile,
    get_security_users_page,
    lock_user_card_trade,
    toggle_security_user_ban,
    unlock_user_card_trade,
)
from app.states.admin_security import AdminSecurityStates
from app.texts.admin_security import (
    ADMIN_SECURITY_CARD_LOCKED_TEXT,
    ADMIN_SECURITY_CARD_UNLOCKED_TEXT,
    ADMIN_SECURITY_LOCK_REASON_TEXT,
    ADMIN_SECURITY_SEARCH_TEXT,
    build_admin_security_main_text,
    build_security_cards_page_text,
    build_security_logs_page_text,
    build_security_user_profile_text,
    build_security_users_page_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()
ADMIN_SECURITY_BUTTON_TEXT = "🛡 Безопасность"


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


async def show_security_main(callback: CallbackQuery | Message) -> None:
    summary = await get_security_summary()
    text = build_admin_security_main_text(summary)
    keyboard = build_admin_security_main_keyboard()

    if isinstance(callback, Message):
        await callback.answer(text, reply_markup=keyboard)
    else:
        await edit_admin_message(callback, text, reply_markup=keyboard)


async def show_security_users(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    users_page = await get_security_users_page(
        page=page,
        per_page=SECURITY_USERS_PER_PAGE,
        search=search,
    )
    await edit_admin_message(
        callback,
        build_security_users_page_text(users_page),
        reply_markup=build_security_users_keyboard(
            users=users_page.users,
            page=users_page.page,
            pages_count=users_page.pages_count,
            search=users_page.search,
        ),
    )


async def show_security_user(callback: CallbackQuery, user_id: int, page: int) -> None:
    profile = await get_security_user_profile(user_id)

    if profile is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await edit_admin_message(
        callback,
        build_security_user_profile_text(profile),
        reply_markup=build_security_user_keyboard(
            user_id=user_id,
            page=page,
            is_banned=profile.is_banned,
        ),
    )


async def show_security_cards(callback: CallbackQuery, user_id: int, page: int) -> None:
    cards_page = await get_security_user_cards_page(
        user_id=user_id,
        page=page,
        per_page=SECURITY_CARDS_PER_PAGE,
    )
    await edit_admin_message(
        callback,
        build_security_cards_page_text(cards_page),
        reply_markup=build_security_cards_keyboard(
            cards=cards_page.cards,
            user_id=user_id,
            page=cards_page.page,
            pages_count=cards_page.pages_count,
        ),
    )


@router.message(F.text == ADMIN_SECURITY_BUTTON_TEXT)
async def admin_security_button(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    await state.clear()
    await safe_delete_message(message)
    await show_security_main(message)


@router.callback_query(F.data == "admin_security:main")
async def admin_security_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await show_security_main(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_security:users:"))
async def admin_security_users(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_security_users(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_security:users_search_page:"))
async def admin_security_users_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    page = int(parts[2]) if len(parts) > 2 else 1
    search = parts[3] if len(parts) > 3 else None
    await show_security_users(callback, page=page, search=search)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_security:search_users:"))
async def admin_security_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.set_state(AdminSecurityStates.waiting_for_user_search)
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await message.edit_text(ADMIN_SECURITY_SEARCH_TEXT, reply_markup=build_security_cancel_keyboard())
    await callback.answer()


@router.message(AdminSecurityStates.waiting_for_user_search)
async def admin_security_search_result(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    search = (message.text or "").strip()
    data = await state.get_data()
    chat_id = int(data.get("chat_id") or message.chat.id)
    message_id = int(data.get("message_id") or 0)

    await safe_delete_message(message)
    await state.clear()

    users_page = await get_security_users_page(
        page=1,
        per_page=SECURITY_USERS_PER_PAGE,
        search=search,
    )
    text = build_security_users_page_text(users_page)
    keyboard = build_security_users_keyboard(
        users=users_page.users,
        page=users_page.page,
        pages_count=users_page.pages_count,
        search=search,
    )

    if message_id:
        try:
            await message.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=keyboard)
            return
        except Exception:
            pass

    await message.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_security:user:"))
async def admin_security_user(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1
    await show_security_user(callback, user_id=user_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_security:toggle_ban:"))
async def admin_security_toggle_ban(callback: CallbackQuery) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1
    result = await toggle_security_user_ban(user_id, admin_telegram_id=callback.from_user.id)

    if result is None:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await show_security_user(callback, user_id=user_id, page=page)
    await callback.answer("🚫 Статус игрока обновлён")


@router.callback_query(F.data.startswith("admin_security:cards:"))
async def admin_security_cards(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1
    await show_security_cards(callback, user_id=user_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_security:card:"))
async def admin_security_card_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    user_id = int(parts[2])
    user_card_id = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 else 1

    cards_page = await get_security_user_cards_page(user_id=user_id, page=page, per_page=SECURITY_CARDS_PER_PAGE)
    card = next((item for item in cards_page.cards if item.user_card_id == user_card_id), None)

    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return

    if card.trade_locked:
        updated_user_id = await unlock_user_card_trade(user_card_id, admin_telegram_id=callback.from_user.id)
        if updated_user_id is None:
            await callback.answer("Карточка не найдена", show_alert=True)
            return
        await show_security_cards(callback, user_id=updated_user_id, page=page)
        await callback.answer("🔓 Ограничение снято")
        return

    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return

    await state.set_state(AdminSecurityStates.waiting_for_lock_reason)
    await state.update_data(
        user_id=user_id,
        user_card_id=user_card_id,
        page=page,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await message.edit_text(ADMIN_SECURITY_LOCK_REASON_TEXT, reply_markup=build_security_cancel_keyboard())
    await callback.answer()


@router.message(AdminSecurityStates.waiting_for_lock_reason)
async def admin_security_save_lock_reason(message: Message, state: FSMContext) -> None:
    if not await answer_admin_only(message):
        return

    data = await state.get_data()
    user_card_id = int(data.get("user_card_id") or 0)
    page = int(data.get("page") or 1)
    chat_id = int(data.get("chat_id") or message.chat.id)
    message_id = int(data.get("message_id") or 0)
    reason = (message.text or "").strip()[:120] or "Решение администрации лиги"

    await safe_delete_message(message)
    updated_user_id = await lock_user_card_trade(
        user_card_id=user_card_id,
        reason=reason,
        admin_telegram_id=message.from_user.id if message.from_user else 0,
    )
    await state.clear()

    if updated_user_id is None:
        await message.bot.send_message(chat_id=chat_id, text="Карточка не найдена.")
        return

    cards_page = await get_security_user_cards_page(
        user_id=updated_user_id,
        page=page,
        per_page=SECURITY_CARDS_PER_PAGE,
    )
    text = f"{ADMIN_SECURITY_CARD_LOCKED_TEXT}\n\n{build_security_cards_page_text(cards_page)}"
    keyboard = build_security_cards_keyboard(
        cards=cards_page.cards,
        user_id=updated_user_id,
        page=cards_page.page,
        pages_count=cards_page.pages_count,
    )

    if message_id:
        try:
            await message.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=keyboard)
            return
        except Exception:
            pass

    await message.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_security:logs:"))
async def admin_security_logs(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    logs_page = await get_security_logs_page(page=page, per_page=SECURITY_LOGS_PER_PAGE)
    await edit_admin_message(
        callback,
        build_security_logs_page_text(logs_page),
        reply_markup=build_security_logs_keyboard(page=logs_page.page, pages_count=logs_page.pages_count),
    )
    await callback.answer()
