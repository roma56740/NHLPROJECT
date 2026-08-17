from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_cards import CardListItem, CardOwnerCopiesPage, CardOwnersPage


ADMIN_CARDS_PER_PAGE = 5


def build_admin_cards_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить карточку", callback_data="admin_cards:add")],
            [InlineKeyboardButton(text="📥 Массовое добавление", callback_data="bulk_cards:start")],
            [InlineKeyboardButton(text="📋 Все карточки", callback_data="admin_cards:list:1")],
            [InlineKeyboardButton(text="🔎 Найти карточку", callback_data="admin_cards:search")],
            [InlineKeyboardButton(text="🗂 Коллекции", callback_data="admin_cards:collections")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_cards_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cards:cancel")],
        ]
    )


def build_admin_cards_positions_keyboard(prefix: str = "admin_cards:add_position") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🥅 G", callback_data=f"{prefix}:G"),
                InlineKeyboardButton(text="🛡 D", callback_data=f"{prefix}:D"),
                InlineKeyboardButton(text="🏒 F", callback_data=f"{prefix}:F"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cards:cancel")],
        ]
    )


def build_admin_cards_rarities_keyboard(prefix: str = "admin_cards:add_rarity") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Common", callback_data=f"{prefix}:Common"),
                InlineKeyboardButton(text="Rare", callback_data=f"{prefix}:Rare"),
            ],
            [
                InlineKeyboardButton(text="Epic", callback_data=f"{prefix}:Epic"),
                InlineKeyboardButton(text="Legendary", callback_data=f"{prefix}:Legendary"),
            ],
            [
                InlineKeyboardButton(text="Event", callback_data=f"{prefix}:Event"),
                InlineKeyboardButton(text="Icon", callback_data=f"{prefix}:Icon"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cards:cancel")],
        ]
    )


def build_admin_cards_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сохранить карточку", callback_data="admin_cards:save")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cards:cancel")],
        ]
    )


def build_admin_cards_list_keyboard(
    cards: list[CardListItem],
    page: int,
    pages_count: int,
    search: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for card in cards:
        status = "✅" if card.active else "⏸"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {card.name} • {card.overall} OVR",
                    callback_data=f"admin_cards:view:{card.id}:{page}",
                )
            ]
        )

    if search:
        prev_callback = f"admin_cards:search_list:{max(page - 1, 1)}"
        next_callback = f"admin_cards:search_list:{min(page + 1, pages_count)}"
    else:
        prev_callback = f"admin_cards:list:{max(page - 1, 1)}"
        next_callback = f"admin_cards:list:{min(page + 1, pages_count)}"

    rows.append(
        [
            InlineKeyboardButton(text="⬅️", callback_data=prev_callback),
            InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="admin_cards:page_info"),
            InlineKeyboardButton(text="➡️", callback_data=next_callback),
        ]
    )
    rows.append([InlineKeyboardButton(text="⬅️ В карточки", callback_data="admin_cards:main")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_card_profile_keyboard(card_id: int, page: int, active: bool) -> InlineKeyboardMarkup:
    active_text = "⏸ Отключить из игры" if active else "✅ Вернуть в игру"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Владельцы", callback_data=f"ac:o:{card_id}:1")],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_cards:edit:{card_id}:{page}")],
            [InlineKeyboardButton(text=active_text, callback_data=f"admin_cards:toggle:{card_id}:{page}")],
            [InlineKeyboardButton(text="📋 К списку", callback_data=f"admin_cards:list:{page}")],
            [InlineKeyboardButton(text="⬅️ В карточки", callback_data="admin_cards:main")],
        ]
    )


def build_admin_card_edit_keyboard(card_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏒 Имя", callback_data=f"admin_cards:edit_text:{card_id}:{page}:name")],
            [InlineKeyboardButton(text="🥅 Позиция", callback_data=f"admin_cards:edit_position:{card_id}:{page}")],
            [InlineKeyboardButton(text="⭐ OVR", callback_data=f"admin_cards:edit_text:{card_id}:{page}:overall")],
            [InlineKeyboardButton(text="🛡 Команда", callback_data=f"admin_cards:edit_text:{card_id}:{page}:team")],
            [InlineKeyboardButton(text="🌍 Страна", callback_data=f"admin_cards:edit_text:{card_id}:{page}:country")],
            [InlineKeyboardButton(text="🗂 Коллекция", callback_data=f"admin_cards:edit_text:{card_id}:{page}:collection")],
            [InlineKeyboardButton(text="💎 Редкость", callback_data=f"admin_cards:edit_rarity:{card_id}:{page}")],
            [InlineKeyboardButton(text="💵 Зарплата", callback_data=f"admin_cards:edit_text:{card_id}:{page}:salary")],
            [InlineKeyboardButton(text="🖼 Заменить фото", callback_data=f"admin_cards:edit_image:{card_id}:{page}")],
            [InlineKeyboardButton(text="👁 К карточке", callback_data=f"admin_cards:view:{card_id}:{page}")],
        ]
    )


def build_admin_card_back_keyboard(card_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 К карточке", callback_data=f"admin_cards:view:{card_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ В карточки", callback_data="admin_cards:main")],
        ]
    )


def build_admin_collections_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В карточки", callback_data="admin_cards:main")],
        ]
    )


def build_admin_card_owners_keyboard(page: CardOwnersPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for owner in page.owners:
        username = f"@{owner.username}" if owner.username else owner.nickname
        rows.append([InlineKeyboardButton(
            text=f"👤 {username} · ×{owner.quantity}",
            callback_data=f"ac:u:{page.card_id}:{owner.user_id}:{page.page}:1",
        )])
    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"ac:o:{page.card_id}:{page.page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_cards:page_info"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"ac:o:{page.card_id}:{page.page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К карточке", callback_data=f"admin_cards:view:{page.card_id}:1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_card_owner_copies_keyboard(page: CardOwnerCopiesPage, owners_page: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for copy in page.copies:
        flags = []
        if copy.is_in_lineup:
            flags.append(copy.lineup_slot or "состав")
        if copy.has_frame:
            flags.append("рамка")
        if copy.is_ranked_captain:
            flags.append("капитан")
        if copy.in_open_trade:
            flags.append("обмен")
        suffix = f" · {', '.join(flags)}" if flags else ""
        rows.append([InlineKeyboardButton(
            text=f"🃏 #{copy.user_card_id}{suffix}",
            callback_data=f"ac:c:{page.card_id}:{page.owner_user_id}:{owners_page}:{copy.user_card_id}:{page.page}",
        )])
    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"ac:u:{page.card_id}:{page.owner_user_id}:{owners_page}:{page.page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_cards:page_info"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"ac:u:{page.card_id}:{page.owner_user_id}:{owners_page}:{page.page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Ко всем владельцам", callback_data=f"ac:o:{page.card_id}:{owners_page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_card_copy_keyboard(card_id: int, owner_user_id: int, owners_page: int, user_card_id: int, copies_page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 Забрать у владельца", callback_data=f"ac:rc:{card_id}:{owner_user_id}:{owners_page}:{user_card_id}:{copies_page}")],
        [InlineKeyboardButton(text="⬅️ К экземплярам", callback_data=f"ac:u:{card_id}:{owner_user_id}:{owners_page}:{copies_page}")],
    ])


def build_admin_card_revoke_confirm_keyboard(card_id: int, owner_user_id: int, owners_page: int, user_card_id: int, copies_page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Забрать карточку", callback_data=f"ac:rd:{card_id}:{owner_user_id}:{owners_page}:{user_card_id}:{copies_page}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"ac:c:{card_id}:{owner_user_id}:{owners_page}:{user_card_id}:{copies_page}")],
    ])
