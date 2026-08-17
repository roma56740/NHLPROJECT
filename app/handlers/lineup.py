from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.lineup import (
    LINEUP_CARDS_PER_PAGE,
    build_lineup_clear_confirm_keyboard,
    build_lineup_main_keyboard,
    build_lineup_slot_cards_keyboard,
)
from app.services.lineup import (
    auto_fill_best_lineup,
    clear_lineup,
    get_lineup_cards_page,
    get_lineup_overview,
    is_valid_slot,
    remove_lineup_slot,
    set_lineup_card,
)
from app.services.renders import render_lineup_image
from app.services.cache_cleanup import remove_render_cache_file
from app.services.card_sorting import set_user_card_sort_order
from app.services.users import get_player_profile_by_telegram_id
from app.texts.lineup import LINEUP_CLEAR_CONFIRM_TEXT, build_lineup_text, build_slot_cards_text
from app.utils.messages import safe_delete_callback_message, safe_delete_message


router = Router()

LINEUP_BUTTON_TEXT = "🧩 Состав"


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




async def send_lineup_view(target: CallbackQuery | Message, overview, reply_markup=None, player_id: int | None = None) -> None:
    """`player_id` — внутренний users.id (НЕ telegram_id, который ниже локально
    называется `user_id` и используется только для имени файла рендера) — нужен,
    чтобы подставить экипированные CLAN WAR 2.0 фон/рамку (app.services.war2_cosmetics
    работает по users.id). Опционален: без него (старые вызовы) рендер не меняется."""
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

    text = build_lineup_text(overview)

    background_path = frame_path = None
    if player_id is not None:
        try:
            from app.services import war2_cosmetics

            background_path = await war2_cosmetics.get_equipped_background_path(player_id)
            frame_path = await war2_cosmetics.get_equipped_frame_path(player_id)
        except Exception:
            background_path = frame_path = None

    try:
        render_path = render_lineup_image(
            overview, user_id=user_id, background_override_path=background_path, frame_override_path=frame_path
        )
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

    try:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(render_path),
            caption=text,
            reply_markup=reply_markup,
        )
    finally:
        remove_render_cache_file(render_path)


async def get_current_player(callback_or_message: CallbackQuery | Message):
    from_user = callback_or_message.from_user

    if from_user is None:
        return None

    return await get_player_profile_by_telegram_id(from_user.id)


async def show_lineup(callback: CallbackQuery) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    overview = await get_lineup_overview(profile.id)
    await send_lineup_view(callback, overview, reply_markup=build_lineup_main_keyboard(overview), player_id=profile.id)


async def show_slot_cards(callback: CallbackQuery, slot_code: str, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    if not is_valid_slot(slot_code):
        await callback.answer("Слот не найден", show_alert=True)
        return

    cards_page = await get_lineup_cards_page(
        user_id=profile.id,
        slot_code=slot_code,
        page=page,
        per_page=LINEUP_CARDS_PER_PAGE,
    )
    overview = await get_lineup_overview(profile.id)
    current_filled = overview.slots.get(slot_code) is not None

    await edit_or_send(
        callback,
        build_slot_cards_text(cards_page),
        reply_markup=build_lineup_slot_cards_keyboard(cards_page, current_filled=current_filled),
    )


@router.message(F.text == LINEUP_BUTTON_TEXT)
async def lineup_button(message: Message, state: FSMContext) -> None:
    profile = await get_current_player(message)

    if profile is None:
        await safe_delete_message(message)
        await message.answer("🏒 Открой игру через /start.")
        return

    await state.clear()
    await safe_delete_message(message)

    overview = await get_lineup_overview(profile.id)
    await send_lineup_view(message, overview, reply_markup=build_lineup_main_keyboard(overview), player_id=profile.id)


@router.callback_query(F.data == "lineup:main")
async def lineup_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_lineup(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("lineup:slot:"))
async def lineup_slot(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    slot_code = parts[2] if len(parts) > 2 else ""
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await show_slot_cards(callback, slot_code=slot_code, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("lineup:sort:"))
async def lineup_sort_cards(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = callback.data.split(":") if callback.data else []
    slot_code = parts[2] if len(parts) > 2 else "G"
    sort_order = parts[3] if len(parts) > 3 else "ovr_desc"
    await set_user_card_sort_order(profile.id, sort_order)
    await show_slot_cards(callback, slot_code=slot_code, page=1)
    await callback.answer("Сортировка сохранена")


@router.callback_query(F.data.startswith("lineup:set:"))
async def lineup_set_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    parts = callback.data.split(":") if callback.data else []
    slot_code = parts[2] if len(parts) > 2 else ""
    user_card_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1

    result = await set_lineup_card(
        user_id=profile.id,
        slot_code=slot_code,
        user_card_id=user_card_id,
    )

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    await show_slot_cards(callback, slot_code=slot_code, page=page)
    await callback.answer(result.message)


@router.callback_query(F.data.startswith("lineup:remove:"))
async def lineup_remove_slot(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    slot_code = callback.data.split(":")[-1] if callback.data else ""
    result = await remove_lineup_slot(user_id=profile.id, slot_code=slot_code)

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    await show_lineup(callback)
    await callback.answer(result.message)


@router.callback_query(F.data == "lineup:auto")
async def lineup_auto_fill(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    result = await auto_fill_best_lineup(profile.id)

    if not result.success:
        await callback.answer(result.message, show_alert=True)
        return

    await show_lineup(callback)
    await callback.answer(result.message)


@router.callback_query(F.data == "lineup:clear_confirm")
async def lineup_clear_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(
        callback,
        LINEUP_CLEAR_CONFIRM_TEXT,
        reply_markup=build_lineup_clear_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "lineup:clear")
async def lineup_clear(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return

    result = await clear_lineup(profile.id)
    await show_lineup(callback)
    await callback.answer(result.message)


@router.callback_query(F.data == "lineup:page_info")
async def lineup_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
