"""Global player cosmetics UI.

Cosmetics are not tied to Ranked or CLAN WAR.  Backgrounds and nickname
suffixes are equipped on the player, while each owned frame copy is attached to
one concrete card copy.  Bound/equipped copies remain in inventory but are not
available for trades until explicitly removed.
"""
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services import ranked_cosmetics, war2_cosmetics
from app.services.card_sorting import set_user_card_sort_order
from app.services.ranked_common import RankedError
from app.services.user_cards import get_player_cards_page
from app.services.users import get_player_profile_by_telegram_id
from app.services.war2_common import War2Error
from app.utils.messages import safe_delete_callback_message, safe_delete_message

router = Router()
COSMETICS_BUTTON_TEXT = "🎨 Косметика"
PER_PAGE = 6


async def _profile(target: CallbackQuery | Message):
    if target.from_user is None:
        return None
    return await get_player_profile_by_telegram_id(target.from_user.id)


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        if message.photo:
            await message.delete()
            await callback.bot.send_message(message.chat.id, text, reply_markup=keyboard)
        else:
            await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(message.chat.id, text, reply_markup=keyboard)


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Рамки карт", callback_data="cosmetics:frames")],
        [InlineKeyboardButton(text="🏞 Фоны профиля и состава", callback_data="cosmetics:list:PROFILE_BACKGROUND")],
        [InlineKeyboardButton(text="🏷 Приписки к нику", callback_data="cosmetics:list:NICK_BADGE")],
        [InlineKeyboardButton(text="🎖 Титулы", callback_data="cosmetics:list:TITLE")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")],
    ])


async def _main_text(user_id: int) -> str:
    frames = await war2_cosmetics.get_user_cosmetics_page(user_id, "CARD_FRAME")
    backgrounds = await war2_cosmetics.get_user_cosmetics_page(user_id, "PROFILE_BACKGROUND")
    prefixes = await war2_cosmetics.get_user_cosmetics_page(user_id, "NICK_BADGE")
    titles = await war2_cosmetics.get_user_cosmetics_page(user_id, "TITLE")
    bound = sum(1 for item in frames if item.bound_user_card_id is not None)
    return (
        "<b>🎨 Косметика</b>\n\n"
        "Все предметы работают во всех режимах и являются отдельными экземплярами. "
        "Их можно покупать на Чёрном рынке и обменивать.\n\n"
        f"🖼 Рамки: <b>{len(frames)}</b> · установлено <b>{bound}</b>\n"
        f"🏞 Фоны: <b>{len(backgrounds)}</b>\n"
        f"🏷 Приписки: <b>{len(prefixes)}</b>\n"
        f"🎖 Титулы: <b>{len(titles)}</b>\n\n"
        "Один экземпляр рамки можно поставить только на одну карту. Для второй карты нужен второй экземпляр."
    )


@router.message(F.text == COSMETICS_BUTTON_TEXT)
async def cosmetics_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await safe_delete_message(message)
    profile = await _profile(message)
    if profile is None:
        await message.answer("Открой игру через /start.")
        return
    await message.answer(await _main_text(profile.id), reply_markup=_main_keyboard())


@router.callback_query(F.data == "cosmetics:main")
async def cosmetics_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    await _edit_or_send(callback, await _main_text(profile.id), _main_keyboard())
    await callback.answer()


async def _show_cosmetics_list(callback: CallbackQuery, user_id: int, cosmetic_type: str) -> None:
    if cosmetic_type not in {"PROFILE_BACKGROUND", "NICK_BADGE", "TITLE"}:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return
    items = await war2_cosmetics.get_user_cosmetics_page(user_id, cosmetic_type)
    title = war2_cosmetics.cosmetic_type_title(cosmetic_type)
    lines = [f"<b>🎨 {escape(title)}</b>", "", "✅ — предмет сейчас используется."]
    keyboard: list[list[InlineKeyboardButton]] = []
    if not items:
        lines.extend(["", "Предметов этого типа пока нет. Их можно получить в наградах, купить на Чёрном рынке или выменять."])
    for item in items:
        mark = "✅" if item.equipped else "▫️"
        suffix = f" [{item.badge_text}]" if item.badge_text else ""
        lines.append(f"{mark} <b>{escape(item.title)}</b>{escape(suffix)} · {item.rarity} · экземпляр #{item.id}")
        keyboard.append([InlineKeyboardButton(
            text=f"{mark} {item.title} · #{item.id}",
            callback_data=f"cosmetics:equip:{item.id}:{cosmetic_type}",
        )])
    if any(item.equipped for item in items):
        keyboard.append([InlineKeyboardButton(text="❌ Снять предмет", callback_data=f"cosmetics:unequip:{cosmetic_type}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Косметика", callback_data="cosmetics:main")])
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("cosmetics:list:"))
async def cosmetics_list(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    cosmetic_type = callback.data.split(":")[2]
    await _show_cosmetics_list(callback, profile.id, cosmetic_type)
    await callback.answer()


@router.callback_query(F.data.startswith("cosmetics:equip:"))
async def cosmetics_equip(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = callback.data.split(":")
    owned_id = int(parts[2])
    cosmetic_type = parts[3]
    try:
        await war2_cosmetics.equip_cosmetic(profile.id, owned_id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await _show_cosmetics_list(callback, profile.id, cosmetic_type)
    await callback.answer("Предмет установлен")


@router.callback_query(F.data.startswith("cosmetics:unequip:"))
async def cosmetics_unequip(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    cosmetic_type = callback.data.split(":")[2]
    await war2_cosmetics.unequip_cosmetic(profile.id, cosmetic_type)
    await _show_cosmetics_list(callback, profile.id, cosmetic_type)
    await callback.answer("Предмет снят")


@router.callback_query(F.data == "cosmetics:frames")
async def cosmetics_frames(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    items = await ranked_cosmetics.list_owned_card_frames(profile.id)
    lines = [
        "<b>🖼 Рамки карт</b>", "",
        "Каждая строка — отдельный экземпляр. Установленный экземпляр нельзя использовать повторно, пока рамка не снята.", "",
    ]
    keyboard: list[list[InlineKeyboardButton]] = []
    if not items:
        lines.append("Рамок пока нет. Они продаются на Чёрном рынке и участвуют в обменах.")
    for item in items:
        if item["bound_card_id"] is not None:
            slot = f" · {item['bound_lineup_slot']}" if item.get("bound_lineup_slot") else ""
            status = f"✅ {item['bound_card_name']} {item['bound_card_overall']} OVR{slot}"
        else:
            status = "свободна"
        lines.append(f"• <b>{escape(item['title'])}</b> · #{item['owned_id']} · {escape(status)}")
        keyboard.append([InlineKeyboardButton(
            text=f"{'✅' if item['bound_card_id'] else '🖼'} {item['title']} · #{item['owned_id']}",
            callback_data=f"cosmetics:frame:{item['owned_id']}",
        )])
    keyboard.append([InlineKeyboardButton(text="⬅️ Косметика", callback_data="cosmetics:main")])
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


async def _show_frame_details(callback: CallbackQuery, user_id: int, owned_id: int) -> None:
    items = await ranked_cosmetics.list_owned_card_frames(user_id)
    item = next((row for row in items if int(row["owned_id"]) == owned_id), None)
    if item is None:
        await callback.answer("Рамка не найдена", show_alert=True)
        return
    lines = [f"<b>🖼 {escape(item['title'])}</b>", f"Экземпляр: <b>#{owned_id}</b>", f"Редкость: <b>{item['rarity']}</b>", ""]
    keyboard: list[list[InlineKeyboardButton]] = []
    if item["bound_card_id"] is not None:
        lines.append(f"Установлена на: <b>{escape(item['bound_card_name'])}</b> · {item['bound_card_overall']} OVR")
        keyboard.append([InlineKeyboardButton(text="❌ Снять с карты", callback_data=f"cosmetics:frame_unbind:{owned_id}")])
    else:
        lines.append("Рамка свободна и может быть установлена на одну конкретную карту.")
        keyboard.append([InlineKeyboardButton(text="🃏 Выбрать карту", callback_data=f"cosmetics:frame_cards:{owned_id}:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К рамкам", callback_data="cosmetics:frames")])
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("cosmetics:frame:"))
async def cosmetics_frame_details(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    owned_id = int(callback.data.split(":")[2])
    await _show_frame_details(callback, profile.id, owned_id)
    await callback.answer()


async def _show_frame_cards(callback: CallbackQuery, user_id: int, owned_id: int, page_num: int = 1) -> None:
    items = await ranked_cosmetics.list_owned_card_frames(user_id)
    item = next((row for row in items if int(row["owned_id"]) == owned_id), None)
    if item is None or item["bound_card_id"] is not None:
        await callback.answer("Этот экземпляр уже используется", show_alert=True)
        return
    page = await get_player_cards_page(user_id, page=page_num, per_page=PER_PAGE)
    lines = [
        f"<b>🖼 Установка рамки «{escape(item['title'])}»</b>", "",
        "Выбери конкретный экземпляр карты. ⭐ отмечает карту из текущего состава.",
        f"Сортировка: <b>{'слабые → сильные' if page.sort_order == 'ovr_asc' else 'сильные → слабые'}</b>", "",
    ]
    keyboard: list[list[InlineKeyboardButton]] = []
    for card in page.cards:
        mark = "⭐" if card.is_in_lineup else "🃏"
        keyboard.append([InlineKeyboardButton(
            text=f"{mark} {card.name} · {card.overall} · #{card.id}",
            callback_data=f"cosmetics:frame_apply:{owned_id}:{card.id}",
        )])
    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"cosmetics:frame_cards:{owned_id}:{page.page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="cosmetics:noop"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"cosmetics:frame_cards:{owned_id}:{page.page+1}"))
    keyboard.append(nav)
    next_sort = "ovr_desc" if page.sort_order == "ovr_asc" else "ovr_asc"
    keyboard.append([InlineKeyboardButton(
        text="⬆️ Слабые → сильные" if page.sort_order == "ovr_asc" else "⬇️ Сильные → слабые",
        callback_data=f"cosmetics:frame_sort:{owned_id}:{next_sort}",
    )])
    keyboard.append([InlineKeyboardButton(text="⬅️ К рамке", callback_data=f"cosmetics:frame:{owned_id}")])
    await _edit_or_send(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("cosmetics:frame_cards:"))
async def cosmetics_frame_cards(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = callback.data.split(":")
    owned_id = int(parts[2])
    page_num = int(parts[3]) if len(parts) > 3 else 1
    await _show_frame_cards(callback, profile.id, owned_id, page_num)
    await callback.answer()


@router.callback_query(F.data.startswith("cosmetics:frame_sort:"))
async def cosmetics_frame_sort(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = callback.data.split(":")
    owned_id = int(parts[2])
    await set_user_card_sort_order(profile.id, parts[3])
    await _show_frame_cards(callback, profile.id, owned_id, 1)
    await callback.answer("Сортировка изменена")


@router.callback_query(F.data.startswith("cosmetics:frame_apply:"))
async def cosmetics_frame_apply(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    parts = callback.data.split(":")
    owned_id, user_card_id = int(parts[2]), int(parts[3])
    try:
        await ranked_cosmetics.bind_frame_to_card(profile.id, owned_id, user_card_id)
    except RankedError as error:
        await callback.answer(error.message, show_alert=True)
        return
    await _show_frame_details(callback, profile.id, owned_id)
    await callback.answer("Рамка установлена")


@router.callback_query(F.data.startswith("cosmetics:frame_unbind:"))
async def cosmetics_frame_unbind(callback: CallbackQuery) -> None:
    profile = await _profile(callback)
    if profile is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    owned_id = int(callback.data.split(":")[2])
    await ranked_cosmetics.unbind_frame_copy(profile.id, owned_id)
    await _show_frame_details(callback, profile.id, owned_id)
    await callback.answer("Рамка снята")


@router.callback_query(F.data == "cosmetics:noop")
async def cosmetics_noop(callback: CallbackQuery) -> None:
    await callback.answer()
