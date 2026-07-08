from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.starter_kit import (
    STARTER_KIT_SLOT_ORDER,
    STARTER_KIT_SLOTS,
    StarterKitCardsPage,
    StarterKitOverview,
)

STARTER_KIT_CARDS_PER_PAGE = 5


def build_starter_kit_main_keyboard(overview: StarterKitOverview) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for slot_code in STARTER_KIT_SLOT_ORDER:
        slot = STARTER_KIT_SLOTS[slot_code]
        card = overview.slots.get(slot_code)
        selected = "✅" if card else "➕"
        title = f"{selected} {slot.icon} {slot.title}"
        rows.append([InlineKeyboardButton(text=title, callback_data=f"starter_kit:choose:{slot_code}:1")])

    if overview.filled_count:
        rows.append([InlineKeyboardButton(text="🧹 Очистить стартовый набор", callback_data="starter_kit:clear_all")])

    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_starter_kit_cards_keyboard(page: StarterKitCardsPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for card in page.cards:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⭐ {card.overall} • {card.name}",
                    callback_data=f"starter_kit:set:{page.slot_code}:{card.id}:{page.page}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"starter_kit:choose:{page.slot_code}:{max(page.page - 1, 1)}",
            ),
            InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="starter_kit:page_info"),
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"starter_kit:choose:{page.slot_code}:{min(page.page + 1, page.pages_count)}",
            ),
        ]
    )
    rows.append([InlineKeyboardButton(text="🧹 Очистить слот", callback_data=f"starter_kit:clear:{page.slot_code}")])
    rows.append([InlineKeyboardButton(text="⬅️ В стартовый набор", callback_data="starter_kit:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
