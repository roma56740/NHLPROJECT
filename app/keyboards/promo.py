from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.promo import PromoCodeInfo


def build_promo_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="profile:refresh")]]
    )


def build_promo_after_redeem_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎫 Ещё промокод", callback_data="promo:enter")],
            [InlineKeyboardButton(text="👤 К профилю", callback_data="profile:refresh")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

def build_admin_promo_list_keyboard(promos: list[PromoCodeInfo]) -> InlineKeyboardMarkup:
    keyboard = []
    for promo in promos:
        status = "🟢" if promo.active else "🔴"
        keyboard.append([InlineKeyboardButton(text=f"{status} {promo.code}", callback_data=f"admin_promo:view:{promo.id}")])
    keyboard.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_promo:create")])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_promo:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_promo_view_keyboard(promo: PromoCodeInfo) -> InlineKeyboardMarkup:
    toggle = "🔴 Отключить" if promo.active else "🟢 Включить"
    keyboard = [
        [InlineKeyboardButton(text="🪙 Coins", callback_data=f"admin_promo:edit_coins:{promo.id}")],
        [InlineKeyboardButton(text="💵 Рубли", callback_data=f"admin_promo:edit_rubles:{promo.id}")],
        [InlineKeyboardButton(text="🎟 BP Points", callback_data=f"admin_promo:edit_bp:{promo.id}")],
        [InlineKeyboardButton(text="🎁 Пак", callback_data=f"admin_promo:pack:{promo.id}")],
        [InlineKeyboardButton(text="🔢 Лимит активаций", callback_data=f"admin_promo:edit_max:{promo.id}")],
        [InlineKeyboardButton(text="👤 Лимит на игрока", callback_data=f"admin_promo:edit_per_user:{promo.id}")],
        [InlineKeyboardButton(text="📅 Срок действия", callback_data=f"admin_promo:edit_expires:{promo.id}")],
        [InlineKeyboardButton(text=toggle, callback_data=f"admin_promo:toggle:{promo.id}")],
    ]
    if promo.pack_id is not None:
        keyboard.append([InlineKeyboardButton(text="🚫 Убрать пак", callback_data=f"admin_promo:clear_pack:{promo.id}")])
    keyboard.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_promo:delete_confirm:{promo.id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_promo:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_promo_delete_keyboard(promo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin_promo:delete:{promo_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_promo:view:{promo_id}")],
        ]
    )


def build_admin_promo_pack_keyboard(promo_id: int, packs: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=f"🎁 {name}", callback_data=f"admin_promo:set_pack:{promo_id}:{pack_id}")]
        for pack_id, name in packs
    ]
    keyboard.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_promo:view:{promo_id}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_promo_edit_cancel_keyboard(promo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_promo:view:{promo_id}")]]
    )


def build_admin_promo_create_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_promo:main")]]
    )
