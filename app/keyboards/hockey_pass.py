from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.hockey_pass import (
    AdminRewardsPage,
    ChoicePage,
    HockeyPassPage,
    HockeyPassProfile,
    HockeyPassRewardItem,
    TRACK_TITLES,
    UserHockeyPassInfo,
    UserRewardsPage,
)


HPASS_PER_PAGE = 5


def build_user_hockey_pass_keyboard(info: UserHockeyPassInfo) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎁 Награды", callback_data="hpass:rewards:1")],
    ]

    if info.pass_id is not None and not info.premium_unlocked and not info.is_finished:
        rows.append([InlineKeyboardButton(text="👑 Купить Premium", callback_data="hpass:buy_ask")])

    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="hpass:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_user_rewards_keyboard(page: UserRewardsPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for reward in page.items:
        status = "🎁" if reward.available else "✅" if reward.claimed else "🔒"
        track = "👑" if reward.track == "premium" else "🎟"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {track} Ур. {reward.level} · {reward.title}",
                    callback_data=f"hpass:reward:{reward.id}:{page.page}",
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"hpass:rewards:{page.page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="hpass:page_info"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"hpass:rewards:{page.page + 1}"))
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="hpass:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_reward_keyboard(reward: HockeyPassRewardItem, page: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if reward.available:
        rows.append([InlineKeyboardButton(text="🎁 Получить награду", callback_data=f"hpass:claim:{reward.id}:{page}")])
    rows.append([InlineKeyboardButton(text="⬅️ К наградам", callback_data=f"hpass:rewards:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_premium_buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Открыть Premium", callback_data="hpass:buy")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="hpass:main")],
        ]
    )


def build_admin_hockey_pass_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать Pass", callback_data="admin_hpass:create")],
            [InlineKeyboardButton(text="📋 Все Pass", callback_data="admin_hpass:list:1")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_passes_list_keyboard(page: HockeyPassPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for item in page.items:
        status = "✅" if item.active else "⏸"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {item.title}",
                    callback_data=f"admin_hpass:view:{item.id}:{page.page}",
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_hpass:list:{page.page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_hpass:page_info"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_hpass:list:{page.page + 1}"))
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="➕ Создать Pass", callback_data="admin_hpass:create")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_hpass:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_pass_profile_keyboard(profile: HockeyPassProfile, page: int) -> InlineKeyboardMarkup:
    active_text = "⏸ Отключить" if profile.active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Награды", callback_data=f"admin_hpass:rewards:{profile.id}:1")],
            [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_hpass:edit:title:{profile.id}:{page}")],
            [InlineKeyboardButton(text="📝 Описание", callback_data=f"admin_hpass:edit:description:{profile.id}:{page}")],
            [InlineKeyboardButton(text="⏰ Дата окончания", callback_data=f"admin_hpass:edit:end_at:{profile.id}:{page}")],
            [InlineKeyboardButton(text="👑 Цена Premium", callback_data=f"admin_hpass:price_currency:{profile.id}:{page}")],
            [InlineKeyboardButton(text=active_text, callback_data=f"admin_hpass:toggle:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_hpass:delete_ask:{profile.id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"admin_hpass:list:{page}")],
        ]
    )


def build_admin_pass_delete_keyboard(pass_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin_hpass:delete:{pass_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ Оставить", callback_data=f"admin_hpass:view:{pass_id}:{page}")],
        ]
    )


def build_admin_cancel_keyboard(callback_data: str = "admin_hpass:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)]])


def build_track_keyboard(callback_prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟 Free", callback_data=f"{callback_prefix}:free")],
            [InlineKeyboardButton(text="👑 Premium", callback_data=f"{callback_prefix}:premium")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def build_reward_type_keyboard(callback_prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💱 Валюта", callback_data=f"{callback_prefix}:currency")],
            [InlineKeyboardButton(text="🎁 Пак", callback_data=f"{callback_prefix}:pack")],
            [InlineKeyboardButton(text="🃏 Карточка", callback_data=f"{callback_prefix}:card")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def build_currency_choice_keyboard(choices, callback_prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=item.title, callback_data=f"{callback_prefix}:{item.id}")] for item in choices]
    rows.append([InlineKeyboardButton(text="🎟 Бесплатно", callback_data=f"{callback_prefix}:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_rewards_list_keyboard(page: AdminRewardsPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        status = "✅" if item.active else "⏸"
        track = "👑" if item.track == "premium" else "🎟"
        keyboard.append(
            [InlineKeyboardButton(text=f"{status} {track} Ур. {item.level} · {item.title}", callback_data=f"admin_hpass:reward:{item.id}:{page.page}")]
        )

    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_hpass:rewards:{page.pass_id}:{page.page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_hpass:page_info"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_hpass:rewards:{page.pass_id}:{page.page + 1}"))
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="➕ Добавить награду", callback_data=f"admin_hpass:add_reward:{page.pass_id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К Pass", callback_data=f"admin_hpass:view:{page.pass_id}:1")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_reward_profile_keyboard(reward: HockeyPassRewardItem, page: int) -> InlineKeyboardMarkup:
    active_text = "⏸ Отключить" if reward.active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔢 Уровень", callback_data=f"admin_hpass:reward_edit:level:{reward.id}:{page}")],
            [InlineKeyboardButton(text="🎟 Ветка", callback_data=f"admin_hpass:reward_track:{reward.id}:{page}")],
            [InlineKeyboardButton(text="🎁 Заменить награду", callback_data=f"admin_hpass:reward_replace:{reward.id}:{page}")],
            [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_hpass:reward_edit:title:{reward.id}:{page}")],
            [InlineKeyboardButton(text="🔢 Количество", callback_data=f"admin_hpass:reward_edit:amount:{reward.id}:{page}")],
            [InlineKeyboardButton(text=active_text, callback_data=f"admin_hpass:reward_toggle:{reward.id}:{page}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_hpass:reward_delete_ask:{reward.id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К наградам", callback_data=f"admin_hpass:rewards:{reward.pass_id}:{page}")],
        ]
    )


def build_admin_reward_delete_keyboard(reward: HockeyPassRewardItem, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin_hpass:reward_delete:{reward.id}:{page}")],
            [InlineKeyboardButton(text="⬅️ Оставить", callback_data=f"admin_hpass:reward:{reward.id}:{page}")],
        ]
    )


def build_choice_page_keyboard(page: ChoicePage, callback_prefix: str, search_callback: str, back_callback: str) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        keyboard.append([InlineKeyboardButton(text=item.title, callback_data=f"{callback_prefix}:{item.id}")])

    nav: list[InlineKeyboardButton] = []
    if page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{callback_prefix}_page:{page.page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_hpass:page_info"))
    if page.page < page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{callback_prefix}_page:{page.page + 1}"))
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data=search_callback)])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_confirm_pass_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать Pass", callback_data="admin_hpass:create_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_hpass:main")],
        ]
    )


def build_confirm_reward_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сохранить награду", callback_data="admin_hpass:reward_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_hpass:main")],
        ]
    )
