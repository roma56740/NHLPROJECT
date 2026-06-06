from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.quests import (
    AdminQuestPage,
    AdminQuestProfile,
    QuestList,
    TARGET_TYPE_TITLES,
)


ADMIN_QUESTS_PER_PAGE = 5


def build_quests_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Ежедневные задания", callback_data="quests:daily")],
            [InlineKeyboardButton(text="🏆 Сезонные задания", callback_data="quests:seasonal")],
            [InlineKeyboardButton(text="🎪 События", callback_data="events:user_list:1")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="quests:main")],
        ]
    )


def build_quest_list_keyboard(quest_list: QuestList) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for item in quest_list.items:
        if item.completed and not item.reward_claimed:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🎁 Получить: {item.title}",
                        callback_data=f"quests:claim:{item.progress_id}:{quest_list.period_type}",
                    )
                ]
            )

    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"quests:{quest_list.period_type}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="quests:main")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_quests_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать задание", callback_data="admin_quests:create")],
            [InlineKeyboardButton(text="📋 Все задания", callback_data="admin_quests:list:1")],
            [InlineKeyboardButton(text="🔎 Найти задание", callback_data="admin_quests:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_admin_quest_period_keyboard(back_callback: str = "admin_quests:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Ежедневное", callback_data="admin_quests:create_period:daily")],
            [InlineKeyboardButton(text="🏆 Сезонное", callback_data="admin_quests:create_period:seasonal")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def build_admin_quest_target_keyboard(prefix: str = "admin_quests:create_target", back_callback: str = "admin_quests:main") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏒 Сыграть матчи", callback_data=f"{prefix}:matches_played")],
        [InlineKeyboardButton(text="✅ Выиграть матчи", callback_data=f"{prefix}:matches_won")],
        [InlineKeyboardButton(text="🥅 Забить голы", callback_data=f"{prefix}:goals_scored")],
        [InlineKeyboardButton(text="🧤 Сухие победы", callback_data=f"{prefix}:shutout_wins")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_quests_cancel_keyboard(callback_data: str = "admin_quests:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)],
        ]
    )


def build_admin_quest_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать задание", callback_data="admin_quests:create_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_quests:main")],
        ]
    )


def build_admin_quests_list_keyboard(page: AdminQuestPage) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for quest in page.items:
        status = "✅" if quest.active else "⏸"
        period = "📅" if quest.period_type == "daily" else "🏆"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {period} {quest.title}",
                    callback_data=f"admin_quests:view:{quest.id}:{page.page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=(f"admin_quests:search_list:{page.page - 1}" if page.search else f"admin_quests:list:{page.page - 1}"),
            )
        )

    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_quests:page_info"))

    if page.page < page.pages_count:
        navigation.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(f"admin_quests:search_list:{page.page + 1}" if page.search else f"admin_quests:list:{page.page + 1}"),
            )
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="➕ Создать задание", callback_data="admin_quests:create")])
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="admin_quests:search")])

    if page.search:
        keyboard.append([InlineKeyboardButton(text="📋 Все задания", callback_data="admin_quests:list:1")])

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_quests:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_quest_profile_keyboard(profile: AdminQuestProfile, page: int) -> InlineKeyboardMarkup:
    active_text = "⏸ Отключить" if profile.active else "✅ Включить"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_quests:edit:title:{profile.id}:{page}")],
            [InlineKeyboardButton(text="📝 Описание", callback_data=f"admin_quests:edit:description:{profile.id}:{page}")],
            [InlineKeyboardButton(text="📅 Тип задания", callback_data=f"admin_quests:edit_period:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🎯 Цель", callback_data=f"admin_quests:edit_target:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🔢 Количество", callback_data=f"admin_quests:edit:target_value:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🎟 BP Points", callback_data=f"admin_quests:edit:bp_reward:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🪙 Coins", callback_data=f"admin_quests:edit:coins_reward:{profile.id}:{page}")],
            [InlineKeyboardButton(text=active_text, callback_data=f"admin_quests:toggle:{profile.id}:{page}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_quests:delete_ask:{profile.id}:{page}")],
            [InlineKeyboardButton(text="⬅️ К заданиям", callback_data=f"admin_quests:list:{page}")],
        ]
    )


def build_admin_quest_edit_period_keyboard(quest_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Ежедневное", callback_data=f"admin_quests:set_period:{quest_id}:daily:{page}")],
            [InlineKeyboardButton(text="🏆 Сезонное", callback_data=f"admin_quests:set_period:{quest_id}:seasonal:{page}")],
            [InlineKeyboardButton(text="⬅️ К заданию", callback_data=f"admin_quests:view:{quest_id}:{page}")],
        ]
    )


def build_admin_quest_edit_target_keyboard(quest_id: int, page: int) -> InlineKeyboardMarkup:
    rows = []

    for target_type, title in TARGET_TYPE_TITLES.items():
        rows.append(
            [InlineKeyboardButton(text=f"🎯 {title}", callback_data=f"admin_quests:set_target:{quest_id}:{target_type}:{page}")]
        )

    rows.append([InlineKeyboardButton(text="⬅️ К заданию", callback_data=f"admin_quests:view:{quest_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_quest_delete_keyboard(quest_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin_quests:delete:{quest_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ Оставить", callback_data=f"admin_quests:view:{quest_id}:{page}")],
        ]
    )
