from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.user_cards import PlayerCardListItem


USER_CARDS_PER_PAGE = 5
RARITIES = ["Common", "Rare", "Epic", "Legendary", "Event", "Icon"]
POSITIONS = ["G", "D", "F"]


def filter_value(value: str | None) -> str:
    return value if value else "all"


def build_user_cards_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои карточки", callback_data="user_cards:list:1")],
            [InlineKeyboardButton(text="🔎 Найти карточку", callback_data="user_cards:search")],
            [InlineKeyboardButton(text="🎛 Фильтры", callback_data="user_cards:filters")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_user_cards_list_keyboard(
    cards: list[PlayerCardListItem],
    page: int,
    pages_count: int,
    search: str | None = None,
    position: str | None = None,
    rarity: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for card in cards:
        status = "⭐" if card.is_in_lineup else "🃏"
        lock = " 🔒" if card.trade_locked else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {card.name} · {card.overall} · {card.position}{lock}",
                    callback_data=f"user_cards:view:{card.id}:{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"user_cards:list:{page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="user_cards:page_info"))

    if page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"user_cards:list:{page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([
        InlineKeyboardButton(text="🔎 Поиск", callback_data="user_cards:search"),
        InlineKeyboardButton(text="🎛 Фильтры", callback_data="user_cards:filters"),
    ])

    if search or position or rarity:
        keyboard.append([InlineKeyboardButton(text="🧹 Сбросить", callback_data="user_cards:clear_filters")])

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="user_cards:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_card_profile_keyboard(user_card_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К карточкам", callback_data=f"user_cards:list:{page}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def build_user_cards_filters_keyboard(
    position: str | None = None,
    rarity: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    keyboard.append([InlineKeyboardButton(text="🏒 Все позиции", callback_data="user_cards:filter_position:all")])
    keyboard.append(
        [
            InlineKeyboardButton(text=(f"✅ {position_name}" if position == position_name else position_name), callback_data=f"user_cards:filter_position:{position_name}")
            for position_name in POSITIONS
        ]
    )

    keyboard.append([InlineKeyboardButton(text="✨ Все редкости", callback_data="user_cards:filter_rarity:all")])

    for rarity_name in RARITIES:
        text = f"✅ {rarity_name}" if rarity == rarity_name else rarity_name
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"user_cards:filter_rarity:{rarity_name}")])

    keyboard.append([InlineKeyboardButton(text="📋 Показать карточки", callback_data="user_cards:list:1")])
    keyboard.append([InlineKeyboardButton(text="🧹 Сбросить", callback_data="user_cards:clear_filters")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="user_cards:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_cards_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="user_cards:main")],
        ]
    )
