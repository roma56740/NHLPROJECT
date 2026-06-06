from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.chemistry import ChemistryRule, ChemistryRulesPage, RULE_TYPES

CHEMISTRY_RULES_PER_PAGE = 5


def build_admin_chemistry_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать бонус", callback_data="chemistry:create")],
            [InlineKeyboardButton(text="📋 Все бонусы", callback_data="chemistry:list:1")],
            [InlineKeyboardButton(text="🔎 Найти бонус", callback_data="chemistry:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_rule_type_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"{prefix}:{rule_type}")]
            for rule_type, title in RULE_TYPES.items()
        ] + [[InlineKeyboardButton(text="❌ Отмена", callback_data="chemistry:cancel")]]
    )


def build_required_cards_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="2 карты", callback_data=f"{prefix}:2"),
                InlineKeyboardButton(text="3 карты", callback_data=f"{prefix}:3"),
            ],
            [
                InlineKeyboardButton(text="4 карты", callback_data=f"{prefix}:4"),
                InlineKeyboardButton(text="5 карт", callback_data=f"{prefix}:5"),
            ],
            [InlineKeyboardButton(text="6 карт", callback_data=f"{prefix}:6")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="chemistry:cancel")],
        ]
    )


def build_bonus_ovr_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="+1 OVR", callback_data=f"{prefix}:1"),
                InlineKeyboardButton(text="+2 OVR", callback_data=f"{prefix}:2"),
            ],
            [
                InlineKeyboardButton(text="+3 OVR", callback_data=f"{prefix}:3"),
                InlineKeyboardButton(text="+4 OVR", callback_data=f"{prefix}:4"),
            ],
            [InlineKeyboardButton(text="+5 OVR", callback_data=f"{prefix}:5")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="chemistry:cancel")],
        ]
    )


def build_chemistry_rules_keyboard(page: ChemistryRulesPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for rule in page.rules:
        status = "✅" if rule.active else "🚫"
        rows.append([
            InlineKeyboardButton(
                text=f"{status} {rule.value} · +{rule.bonus_ovr}",
                callback_data=f"chemistry:view:{rule.id}:{page.page}",
            )
        ])

    navigation: list[InlineKeyboardButton] = []

    if page.page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"chemistry:list:{page.page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="chemistry:page_info"))

    if page.page < page.pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"chemistry:list:{page.page + 1}"))

    if navigation:
        rows.append(navigation)

    rows.append([InlineKeyboardButton(text="➕ Создать бонус", callback_data="chemistry:create")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="chemistry:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_chemistry_rule_profile_keyboard(rule: ChemistryRule, page: int = 1) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Отключить" if rule.active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Тип", callback_data=f"chemistry:edit_type:{rule.id}"),
                InlineKeyboardButton(text="✏️ Значение", callback_data=f"chemistry:edit_value:{rule.id}"),
            ],
            [
                InlineKeyboardButton(text="📌 Кол-во карт", callback_data=f"chemistry:edit_required:{rule.id}"),
                InlineKeyboardButton(text="⭐ Бонус", callback_data=f"chemistry:edit_bonus:{rule.id}"),
            ],
            [InlineKeyboardButton(text=toggle_text, callback_data=f"chemistry:toggle:{rule.id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"chemistry:delete_confirm:{rule.id}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"chemistry:list:{page}")],
        ]
    )


def build_chemistry_delete_confirm_keyboard(rule_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"chemistry:delete:{rule_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chemistry:view:{rule_id}:1")],
        ]
    )


def build_chemistry_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="chemistry:cancel")]]
    )
