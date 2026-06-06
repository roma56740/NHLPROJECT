from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.events import (
    AdminEventPage,
    AdminEventProfile,
    ChoicePage,
    EVENT_REWARD_TITLES,
    EVENT_TARGET_TITLES,
    UserEventPage,
    UserEventProfile,
)


EVENTS_PER_PAGE = 5
ADMIN_EVENTS_PER_PAGE = 5


def build_user_events_keyboard(page: UserEventPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for event in page.items:
        status = "✅" if event.reward_claimed else "🎁" if event.completed else "🔥"
        keyboard.append([InlineKeyboardButton(text=f"{status} {event.title}", callback_data=f"events:user_view:{event.id}:{page.page}")])

    navigation: list[InlineKeyboardButton] = []
    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"events:user_list:{page.page - 1}"))
    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="events:page_info"))
    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"events:user_list:{page.page + 1}"))
    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"events:user_list:{page.page}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К заданиям", callback_data="quests:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_event_profile_keyboard(profile: UserEventProfile, page: int) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    if profile.completed and not profile.reward_claimed:
        keyboard.append([InlineKeyboardButton(text="🎁 Получить награду", callback_data=f"events:claim:{profile.progress_id}:{page}")])

    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"events:user_view:{profile.id}:{page}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К событиям", callback_data=f"events:user_list:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_events_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать событие", callback_data="admin_events:create")],
            [InlineKeyboardButton(text="📋 Все события", callback_data="admin_events:list:1")],
            [InlineKeyboardButton(text="🔎 Найти событие", callback_data="admin_events:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_event_cancel_keyboard(callback_data: str = "admin_events:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)]])


def build_event_image_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Без обложки", callback_data="admin_events:create_no_image")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_events:main")],
        ]
    )


def build_event_target_keyboard(prefix: str, back_callback: str = "admin_events:main") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏒 Сыграть матчи", callback_data=f"{prefix}:matches_played")],
        [InlineKeyboardButton(text="✅ Выиграть матчи", callback_data=f"{prefix}:matches_won")],
        [InlineKeyboardButton(text="🥅 Забить голы", callback_data=f"{prefix}:goals_scored")],
        [InlineKeyboardButton(text="🧤 Сухие победы", callback_data=f"{prefix}:shutout_wins")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_event_reward_type_keyboard(prefix: str, back_callback: str = "admin_events:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💱 Валюта", callback_data=f"{prefix}:currency")],
            [InlineKeyboardButton(text="🎁 Пак", callback_data=f"{prefix}:pack")],
            [InlineKeyboardButton(text="🃏 Карточка", callback_data=f"{prefix}:card")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def build_currency_keyboard(prefix: str, back_callback: str = "admin_events:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Coins", callback_data=f"{prefix}:coins")],
            [InlineKeyboardButton(text="⚡ Energy", callback_data=f"{prefix}:energy")],
            [InlineKeyboardButton(text="🏅 Rank-point", callback_data=f"{prefix}:rank_point")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def build_choice_page_keyboard(page: ChoicePage, prefix: str, back_callback: str, search_callback: str | None = None) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for item in page.items:
        keyboard.append([InlineKeyboardButton(text=item.title, callback_data=f"{prefix}:{item.id}")])

    navigation: list[InlineKeyboardButton] = []
    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_page:{page.page - 1}"))
    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="events:page_info"))
    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_page:{page.page + 1}"))
    if navigation:
        keyboard.append(navigation)

    if search_callback:
        keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data=search_callback)])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_events_list_keyboard(page: AdminEventPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for event in page.items:
        status = "✅" if event.active else "⏸"
        announce = "📢" if event.announcement_sent else "▫️"
        keyboard.append([InlineKeyboardButton(text=f"{status} {announce} {event.title}", callback_data=f"admin_events:view:{event.id}:{page.page}")])

    navigation: list[InlineKeyboardButton] = []
    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=(f"admin_events:search_list:{page.page - 1}" if page.search else f"admin_events:list:{page.page - 1}")))
    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="events:page_info"))
    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=(f"admin_events:search_list:{page.page + 1}" if page.search else f"admin_events:list:{page.page + 1}")))
    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="➕ Создать событие", callback_data="admin_events:create")])
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="admin_events:search")])
    if page.search:
        keyboard.append([InlineKeyboardButton(text="📋 Все события", callback_data="admin_events:list:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_events:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_event_profile_keyboard(profile: AdminEventProfile, page: int) -> InlineKeyboardMarkup:
    active_text = "⏸ Отключить" if profile.active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Объявить игрокам", callback_data=f"admin_events:announce:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🖼 Обложка", callback_data=f"admin_events:edit_image:{profile.id}:{page}")],
            [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_events:edit:title:{profile.id}:{page}")],
            [InlineKeyboardButton(text="📝 Описание", callback_data=f"admin_events:edit:description:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🎯 Цель", callback_data=f"admin_events:edit_target:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🔢 Количество", callback_data=f"admin_events:edit_number:target_value:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🎁 Награда", callback_data=f"admin_events:edit_reward:{profile.id}:{page}")],
            [InlineKeyboardButton(text="📦 Количество награды", callback_data=f"admin_events:edit_number:reward_amount:{profile.id}:{page}")],
            [InlineKeyboardButton(text="📅 Дата окончания", callback_data=f"admin_events:edit_end:{profile.id}:{page}")],
            [InlineKeyboardButton(text=active_text, callback_data=f"admin_events:toggle:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_events:delete_ask:{profile.id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К событиям", callback_data=f"admin_events:list:{page}")],
        ]
    )


def build_event_delete_keyboard(event_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin_events:delete:{event_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ Оставить", callback_data=f"admin_events:view:{event_id}:{page}")],
        ]
    )


def build_event_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать событие", callback_data="admin_events:create_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_events:main")],
        ]
    )
