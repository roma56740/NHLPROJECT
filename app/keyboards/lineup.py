from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.lineup import (
    LINEUP_SLOT_ORDER,
    LineupCardsPage,
    LineupOverview,
    get_slot_info,
)


LINEUP_CARDS_PER_PAGE = 5


def build_lineup_main_keyboard(overview: LineupOverview) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="lineup:main")])

    for slot_code in LINEUP_SLOT_ORDER:
        slot = get_slot_info(slot_code)
        card = overview.slots.get(slot_code)
        value = "свободно" if card is None else f"{card.name} · {card.overall}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{slot.icon} {slot.title}: {value}",
                    callback_data=f"lineup:slot:{slot_code}:1",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton(text="🧹 Очистить состав", callback_data="lineup:clear_confirm")])
    keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_lineup_slot_cards_keyboard(page: LineupCardsPage, current_filled: bool) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for card in page.cards:
        mark = "✅" if card.lineup_slot == page.slot_code else "🃏"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {card.name} · {card.overall} · {card.team}",
                    callback_data=f"lineup:set:{page.slot_code}:{card.user_card_id}:{page.page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"lineup:slot:{page.slot_code}:{page.page - 1}")
        )

    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="lineup:page_info"))

    if page.page < page.pages_count:
        navigation.append(
            InlineKeyboardButton(text="➡️", callback_data=f"lineup:slot:{page.slot_code}:{page.page + 1}")
        )

    if navigation:
        keyboard.append(navigation)

    if current_filled:
        keyboard.append([InlineKeyboardButton(text="❌ Освободить слот", callback_data=f"lineup:remove:{page.slot_code}")])

    keyboard.append([InlineKeyboardButton(text="⬅️ К составу", callback_data="lineup:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_lineup_clear_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Очистить", callback_data="lineup:clear")],
            [InlineKeyboardButton(text="⬅️ Оставить состав", callback_data="lineup:main")],
        ]
    )
