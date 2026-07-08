from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.packs import AdminPackListItem, PackCardItem, PackChoiceItem, PackInventoryItem


USER_PACKS_PER_PAGE = 5
PACK_HISTORY_PER_PAGE = 5
ADMIN_PACKS_PER_PAGE = 5
ADMIN_GIVE_PACKS_PER_PAGE = 5


def build_user_packs_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Мои паки", callback_data="packs:inventory:1")],
            [InlineKeyboardButton(text="📜 История открытий", callback_data="packs:history:1")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_user_pack_inventory_keyboard(
    packs: list[PackInventoryItem],
    page: int,
    pages_count: int,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for pack in packs:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🎁 {pack.name} ×{pack.quantity}",
                    callback_data=f"packs:view:{pack.id}:{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"packs:inventory:{page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="packs:page_info"))

    if page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"packs:inventory:{page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="📜 История", callback_data="packs:history:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="packs:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_pack_profile_keyboard(pack_id: int, page: int, quantity: int) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    if quantity > 0:
        keyboard.append([InlineKeyboardButton(text="✨ Открыть пак", callback_data=f"packs:open:{pack_id}:{page}")])

    keyboard.append([InlineKeyboardButton(text="🎁 К моим пакам", callback_data=f"packs:inventory:{page}")])
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_pack_opening_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Открыть ещё", callback_data="packs:inventory:1")],
            [InlineKeyboardButton(text="♻️ Продать дубликаты", callback_data="user_cards:bulk_confirm:duplicates")],
            [InlineKeyboardButton(text="🃏 Мои карточки", callback_data="user_cards:list:1")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


def build_pack_history_keyboard(page: int, pages_count: int) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"packs:history:{page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="packs:page_info"))

    if page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"packs:history:{page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🎁 Мои паки", callback_data="packs:inventory:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="packs:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_packs_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать пак", callback_data="admin_packs:add")],
            [InlineKeyboardButton(text="📋 Все паки", callback_data="admin_packs:list:1")],
            [InlineKeyboardButton(text="🔎 Найти пак", callback_data="admin_packs:search")],
            [InlineKeyboardButton(text="👥 Выдать пак игроку", callback_data="admin_users:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_packs_list_keyboard(
    packs: list[AdminPackListItem],
    page: int,
    pages_count: int,
    search: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for pack in packs:
        status = "✅" if pack.active else "⏸"
        shop = "🛒" if pack.is_shop_available else "🎯"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {shop} {pack.name} · {pack.cards_count} карт. · {pack.selected_cards_count} выбрано",
                    callback_data=f"admin_packs:view:{pack.id}:{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    callback_prefix = "admin_packs:search_page" if search else "admin_packs:list"

    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"{callback_prefix}:{page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="admin_packs:page_info"))

    if page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"{callback_prefix}:{page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="➕ Создать пак", callback_data="admin_packs:add")])

    if search:
        keyboard.append([InlineKeyboardButton(text="📋 Все паки", callback_data="admin_packs:list:1")])

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_packs:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_pack_profile_keyboard(pack_id: int, page: int, active: bool, shop: bool) -> InlineKeyboardMarkup:
    active_text = "⏸ Выключить" if active else "▶️ Включить"
    shop_text = "🎯 Убрать из магазина" if shop else "🛒 Добавить в магазин"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_packs:edit_name:{pack_id}:{page}")],
            [InlineKeyboardButton(text="📝 Описание", callback_data=f"admin_packs:edit_description:{pack_id}:{page}")],
            [InlineKeyboardButton(text="🖼 Фото пака", callback_data=f"admin_packs:edit_image:{pack_id}:{page}")],
            [InlineKeyboardButton(text="💰 Цена", callback_data=f"admin_packs:edit_price:{pack_id}:{page}")],
            [InlineKeyboardButton(text="🃏 Карт внутри", callback_data=f"admin_packs:edit_count:{pack_id}:{page}")],
            [InlineKeyboardButton(text="🏒 Карты в паке", callback_data=f"admin_packs:cards:{pack_id}:1:{page}")],
            [InlineKeyboardButton(text="🎲 Шансы редкостей", callback_data=f"admin_packs:edit_odds:{pack_id}:{page}")],
            [InlineKeyboardButton(text=shop_text, callback_data=f"admin_packs:toggle_shop:{pack_id}:{page}")],
            [InlineKeyboardButton(text=active_text, callback_data=f"admin_packs:toggle_active:{pack_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"admin_packs:list:{page}")],
        ]
    )


def build_admin_pack_cards_keyboard(
    pack_id: int,
    list_page: int,
    back_page: int,
    cards: list[PackCardItem],
    pages_count: int,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for card in cards:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {card.name} · {card.overall} OVR · {card.rarity}",
                    callback_data=f"admin_packs:cards_remove:{pack_id}:{card.card_id}:{list_page}:{back_page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if list_page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_packs:cards:{pack_id}:{list_page - 1}:{back_page}"))

    navigation.append(InlineKeyboardButton(text=f"{list_page}/{pages_count}", callback_data="admin_packs:page_info"))

    if list_page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_packs:cards:{pack_id}:{list_page + 1}:{back_page}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="➕ Добавить карту", callback_data=f"admin_packs:cards_add:{pack_id}:{back_page}:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К паку", callback_data=f"admin_packs:view:{pack_id}:{back_page}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_pack_available_cards_keyboard(
    pack_id: int,
    back_page: int,
    card_page: int,
    pages_count: int,
    cards: list[PackCardItem],
    search: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for card in cards:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"➕ {card.name} · {card.overall} OVR · {card.rarity}",
                    callback_data=f"admin_packs:cards_add_do:{pack_id}:{card.card_id}:{back_page}:{card_page}",
                )
            ]
        )

    callback_prefix = "admin_packs:cards_search_page" if search else "admin_packs:cards_add"
    navigation: list[InlineKeyboardButton] = []

    if card_page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"{callback_prefix}:{pack_id}:{back_page}:{card_page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{card_page}/{pages_count}", callback_data="admin_packs:page_info"))

    if card_page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"{callback_prefix}:{pack_id}:{back_page}:{card_page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🔎 Найти карту", callback_data=f"admin_packs:cards_search:{pack_id}:{back_page}")])

    if search:
        keyboard.append([InlineKeyboardButton(text="📋 Все карты", callback_data=f"admin_packs:cards_add:{pack_id}:{back_page}:1")])

    keyboard.append([InlineKeyboardButton(text="⬅️ К картам пака", callback_data=f"admin_packs:cards:{pack_id}:1:{back_page}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_pack_currency_keyboard(action: str, pack_id: int | None = None, page: int = 1) -> InlineKeyboardMarkup:
    prefix = f"admin_packs:{action}"

    if pack_id is None:
        make_data = lambda currency: f"{prefix}:{currency}"
        cancel_data = "admin_packs:main"
    else:
        make_data = lambda currency: f"{prefix}:{pack_id}:{page}:{currency}"
        cancel_data = f"admin_packs:view:{pack_id}:{page}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Coins", callback_data=make_data("coins"))],
            [InlineKeyboardButton(text="⚡ Energy", callback_data=make_data("energy"))],
            [InlineKeyboardButton(text="🏅 Rank-point", callback_data=make_data("rank_point"))],
            [InlineKeyboardButton(text="🎁 Бесплатно", callback_data=make_data("free"))],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_data)],
        ]
    )


def build_admin_pack_shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Показывать в магазине", callback_data="admin_packs:add_shop:1")],
            [InlineKeyboardButton(text="🎯 Только награды и выдача", callback_data="admin_packs:add_shop:0")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_packs:main")],
        ]
    )


def build_admin_pack_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сохранить пак", callback_data="admin_packs:add_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_packs:main")],
        ]
    )


def build_admin_pack_cancel_keyboard(pack_id: int | None = None, page: int = 1) -> InlineKeyboardMarkup:
    callback_data = f"admin_packs:view:{pack_id}:{page}" if pack_id else "admin_packs:main"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)],
        ]
    )


def build_admin_give_pack_keyboard(
    user_id: int,
    user_page: int,
    packs: list[PackChoiceItem],
    pack_page: int,
    pages_count: int,
    search: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for pack in packs:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🎁 {pack.name} · {pack.quantity_hint} карт.",
                    callback_data=f"admin_users:give_pack_do:{user_id}:{pack.id}:{user_page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if pack_page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"admin_users:give_pack_list:{user_id}:{pack_page - 1}:{user_page}",
            )
        )

    navigation.append(InlineKeyboardButton(text=f"{pack_page}/{pages_count}", callback_data="admin_users:page_info"))

    if pack_page < pages_count:
        navigation.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"admin_users:give_pack_list:{user_id}:{pack_page + 1}:{user_page}",
            )
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🔎 Найти пак", callback_data=f"admin_users:give_pack_search:{user_id}:{user_page}")])

    if search:
        keyboard.append([InlineKeyboardButton(text="📋 Все паки", callback_data=f"admin_users:give_pack_list:{user_id}:1:{user_page}")])

    keyboard.append([InlineKeyboardButton(text="⬅️ К игроку", callback_data=f"admin_users:view:{user_id}:{user_page}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_pack_user_cancel_keyboard(user_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К игроку", callback_data=f"admin_users:view:{user_id}:{page}")],
        ]
    )


# Старое имя оставлено для уже подключённой админки пользователей.
def build_admin_pack_cancel_keyboard_for_user(user_id: int, page: int) -> InlineKeyboardMarkup:
    return build_admin_pack_user_cancel_keyboard(user_id=user_id, page=page)


# Совместимость с прошлым этапом.
def build_admin_pack_cancel_keyboard(user_id: int | None = None, page: int = 1, pack_id: int | None = None) -> InlineKeyboardMarkup:  # type: ignore[no-redef]
    if user_id is not None and pack_id is None:
        return build_admin_pack_user_cancel_keyboard(user_id=user_id, page=page)

    callback_data = f"admin_packs:view:{pack_id}:{page}" if pack_id else "admin_packs:main"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)],
        ]
    )
