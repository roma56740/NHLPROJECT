from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

SECURITY_USERS_PER_PAGE = 5
SECURITY_CARDS_PER_PAGE = 5
SECURITY_LOGS_PER_PAGE = 5


def build_admin_security_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Игроки", callback_data="admin_security:users:1")],
            [InlineKeyboardButton(text="🔎 Найти игрока", callback_data="admin_security:search_users:1")],
            [InlineKeyboardButton(text="📜 Журнал", callback_data="admin_security:logs:1")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_security:main")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_security_users_keyboard(users, page: int, pages_count: int, search: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for user in users:
        status = "🚫" if user.is_banned else "✅"
        rows.append([
            InlineKeyboardButton(
                text=f"{status} {user.nickname}",
                callback_data=f"admin_security:user:{user.id}:{page}",
            )
        ])

    nav = []
    prefix = "admin_security:users_search_page" if search else "admin_security:users"
    search_part = f":{search}" if search else ""

    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page - 1}{search_part}"))
    if page < pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page + 1}{search_part}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔎 Найти игрока", callback_data="admin_security:search_users:1")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_security:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_security_user_keyboard(user_id: int, page: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_text = "✅ Разблокировать" if is_banned else "🚫 Заблокировать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ban_text, callback_data=f"admin_security:toggle_ban:{user_id}:{page}")],
            [InlineKeyboardButton(text="🔒 Trade Lock карточек", callback_data=f"admin_security:cards:{user_id}:1")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"admin_security:users:{page}")],
        ]
    )


def build_security_cards_keyboard(cards, user_id: int, page: int, pages_count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for card in cards:
        icon = "🔓 Снять" if card.trade_locked else "🔒 Закрыть"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} · {card.name} {card.overall}",
                callback_data=f"admin_security:card:{user_id}:{card.user_card_id}:{page}",
            )
        ])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_security:cards:{user_id}:{page - 1}"))
    if page < pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_security:cards:{user_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="⬅️ К игроку", callback_data=f"admin_security:user:{user_id}:1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_security_logs_keyboard(page: int, pages_count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav = []

    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_security:logs:{page - 1}"))
    if page < pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_security:logs:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_security:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_security_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_security:main")],
        ]
    )
