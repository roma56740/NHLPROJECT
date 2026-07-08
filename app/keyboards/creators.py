from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.creators import CreatorApplication, CreatorPanel


class CreatorApplyStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_subs = State()
    waiting_for_description = State()


class CreatorDistributeStates(StatesGroup):
    waiting_for_coins_target = State()
    waiting_for_coins_amount = State()
    waiting_for_pack_target = State()


class AdminCreatorLevelStates(StatesGroup):
    waiting_for_level = State()


def build_creator_intro_keyboard(is_creator: bool) -> InlineKeyboardMarkup:
    if is_creator:
        rows = [[InlineKeyboardButton(text="⭐ Моя панель", callback_data="creator:panel")]]
    else:
        rows = [[InlineKeyboardButton(text="📝 Подать заявку", callback_data="creator:apply")]]
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_creator_panel_keyboard(panel: CreatorPanel) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🪙 Выдать Coins", callback_data="creator:give_coins")],
    ]
    if panel.packs:
        rows.append([InlineKeyboardButton(text="🎁 Выдать пак", callback_data="creator:give_pack")])
    rows.append([InlineKeyboardButton(text="📜 История выдач", callback_data="creator:history")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="creator:panel")])
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_creators:approve:{app_id}")],
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
            [InlineKeyboardButton(text="🚫 Снять статус", callback_data=f"admin_creators:revoke:{user_id}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_creators:list")],
        ]
    )


def build_admin_creator_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_creators:list")]])
