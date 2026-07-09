from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.creators import CreatorApplication, CreatorBankItem, CreatorPanel, CreatorLevelConfig, format_int


class CreatorApplyStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_subs = State()
    waiting_for_description = State()


class CreatorDistributeStates(StatesGroup):
    waiting_for_bank_target = State()
    waiting_for_bank_amount = State()
    waiting_for_card_id = State()
    waiting_for_currency_amount = State()


class AdminCreatorLevelStates(StatesGroup):
    waiting_for_level = State()
    waiting_for_subscribers = State()
    waiting_for_author_code = State()
    waiting_for_level_config = State()
    waiting_for_personal_rewards = State()
    waiting_for_chat_link = State()


def build_creator_intro_keyboard(is_creator: bool) -> InlineKeyboardMarkup:
    if is_creator:
        rows = [[InlineKeyboardButton(text="⭐ Моя панель", callback_data="creator:panel")]]
    else:
        rows = [[InlineKeyboardButton(text="📝 Подать заявку", callback_data="creator:apply")]]
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_panel_keyboard(panel: CreatorPanel) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ Пополнить банк", callback_data="creator:bank_add")],
    ]
    if panel.bank_items:
        rows.append([InlineKeyboardButton(text="🎁 Выдать из банка", callback_data="creator:bank_give")])
    rows.append([InlineKeyboardButton(text="📜 История выдач", callback_data="creator:history")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="creator:panel")])
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_bank_add_keyboard(has_currencies: bool, has_packs: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_currencies:
        rows.append([InlineKeyboardButton(text="💱 Добавить валюту", callback_data="creator:add_currency")])
    if has_packs:
        rows.append([InlineKeyboardButton(text="🎁 Добавить пак", callback_data="creator:add_pack")])
    rows.append([InlineKeyboardButton(text="🃏 Добавить карту по ID", callback_data="creator:add_card")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="creator:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_currency_pick_keyboard(currencies: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for item in currencies:
        rows.append([
            InlineKeyboardButton(
                text=f"{item['icon']} {item['name']} · {format_int(item['amount'])}",
                callback_data=f"creator:add_currency_pick:{item['currency_code']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="creator:bank_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_pack_deposit_keyboard(packs: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for item in packs:
        rows.append([
            InlineKeyboardButton(
                text=f"🎁 {item['name']} ×{item['quantity']}",
                callback_data=f"creator:add_pack_pick:{item['pack_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="creator:bank_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_bank_items_keyboard(items: list[CreatorBankItem], prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        rows.append([
            InlineKeyboardButton(
                text=f"{item.title} ×{item.quantity} · {format_int(item.total_value)}",
                callback_data=f"{prefix}:{item.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="creator:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Старое имя оставлено для совместимости.
def build_creator_pack_pick_keyboard(packs: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🎁 {name} ×{qty}", callback_data=f"creator:pack_pick:{pack_id}")] for pack_id, name, qty in packs]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="creator:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="creator:panel")]])


def build_creator_apply_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="creator:intro")]])


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

def build_admin_creators_main_keyboard(pending_count: int, creators_count: int) -> InlineKeyboardMarkup:
    apps_label = f"📥 Заявки ({pending_count})" if pending_count else "📥 Заявки"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=apps_label, callback_data="admin_creators:apps")],
            [InlineKeyboardButton(text=f"⭐ Креаторы ({creators_count})", callback_data="admin_creators:list")],
            [InlineKeyboardButton(text="⚙️ Настройки уровней", callback_data="admin_creators:settings")],
            [InlineKeyboardButton(text="🔗 Ссылка на чат", callback_data="admin_creators:chat_link")],
            [InlineKeyboardButton(text="💸 Начислить недельные награды", callback_data="admin_creators:weekly")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_creators:main")],
        ]
    )


def build_admin_apps_keyboard(apps: list[CreatorApplication]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"👤 {a.nickname} · {a.subscribers} подп.", callback_data=f"admin_creators:app:{a.id}")] for a in apps]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_creators:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_app_view_keyboard(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Назначить креатором", callback_data=f"admin_creators:approve:{app_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_creators:reject:{app_id}")],
            [InlineKeyboardButton(text="⬅️ К заявкам", callback_data="admin_creators:apps")],
        ]
    )


def build_admin_creators_list_keyboard(creators: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"👤 {c['nickname']} ({c['creator_level']} ур.)", callback_data=f"admin_creators:creator:{c['id']}")] for c in creators]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_creators:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_creator_manage_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎖 Изменить уровень", callback_data=f"admin_creators:set_level:{user_id}")],
            [InlineKeyboardButton(text="👥 Изменить подписчиков", callback_data=f"admin_creators:set_subs:{user_id}")],
            [InlineKeyboardButton(text="✍️ Код автора", callback_data=f"admin_creators:set_author:{user_id}")],
            [InlineKeyboardButton(text="🚫 Снять статус", callback_data=f"admin_creators:revoke:{user_id}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_creators:list")],
        ]
    )


def build_admin_levels_keyboard(configs: list[CreatorLevelConfig]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{cfg.level} уровень", callback_data=f"admin_creators:level_settings:{cfg.level}")] for cfg in configs]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_creators:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_level_edit_keyboard(level: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔢 Изменить цифры", callback_data=f"admin_creators:level_edit:{level}")],
            [InlineKeyboardButton(text="🏅 Личные награды", callback_data=f"admin_creators:personal:{level}")],
            [InlineKeyboardButton(text="⬅️ К уровням", callback_data="admin_creators:settings")],
        ]
    )


def build_admin_creator_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_creators:list")]])


def build_admin_settings_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_creators:settings")]])
