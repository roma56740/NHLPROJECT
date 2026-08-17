"""Клавиатуры BLACK MARKET — построение InlineKeyboardMarkup по данным сервисного
слоя (конвенция проекта, см. app/keyboards/stronghold.py)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.black_market_common import RARITIES
from app.services.black_market_generation import RotationInfo
from app.texts import black_market as texts

STOREFRONT_PAGE_SIZE = 4
ITEM_TYPE_CHOICES = ("card", "frame", "background", "prefix", "pack", "currency")


def back_row(callback_data: str = "bm:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)]


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    pages_count = max(1, (len(items) + page_size - 1) // page_size)
    safe_page = min(max(page, 1), pages_count)
    start = (safe_page - 1) * page_size
    return items[start : start + page_size], safe_page, pages_count


def build_storefront_keyboard(rotation: RotationInfo, page: int = 1) -> InlineKeyboardMarkup:
    page_items, safe_page, pages_count = _paginate(rotation.items, page, STOREFRONT_PAGE_SIZE)

    keyboard: list[list[InlineKeyboardButton]] = []
    for item in page_items:
        icon = texts.RARITY_ICONS.get(item.rarity, "")
        status_icon = texts.STATUS_ICONS.get(item.item_status, "")
        label = f"{icon}{status_icon} {item.name} — {item.price_amount} {item.price_currency_code}"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"bm:item:{item.id}:{safe_page}")])

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"bm:page:{safe_page - 1}"))
    if pages_count > 1:
        nav_row.append(InlineKeyboardButton(text=f"{safe_page}/{pages_count}", callback_data="bm:noop"))
    if safe_page < pages_count:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"bm:page:{safe_page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_item_detail_keyboard(item, return_page: int) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    if item.item_status == "AVAILABLE" and item.remaining_personal_stock > 0:
        keyboard.append([InlineKeyboardButton(text="✅ Купить", callback_data=f"bm:confirm:{item.id}:{return_page}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"bm:page:{return_page}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🔍 Найти игрока / ассортимент", callback_data="bm_admin:find_user")],
        [InlineKeyboardButton(text="📦 Пул предметов", callback_data="bm_admin:pool")],
        [InlineKeyboardButton(text="➕ Добавить предмет", callback_data="bm_admin:add_item:start")],
        [InlineKeyboardButton(text="🎲 Веса редкости", callback_data="bm_admin:weights")],
        [InlineKeyboardButton(text="⚙️ Настройки ротации", callback_data="bm_admin:settings")],
        [InlineKeyboardButton(text="🔄 Обновить рынок всем", callback_data="bm_admin:refresh_all")],
        [InlineKeyboardButton(text="🧾 Последние покупки", callback_data="bm_admin:purchases")],
        [InlineKeyboardButton(text="📜 Аудит", callback_data="bm_admin:audit")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_shop_toggle_button(shop_enabled: bool) -> InlineKeyboardButton:
    label = "🔴 Выключить магазин" if shop_enabled else "🟢 Включить магазин"
    return InlineKeyboardButton(text=label, callback_data="bm_admin:toggle_shop")


def build_admin_settings_keyboard(shop_enabled: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [build_admin_shop_toggle_button(shop_enabled)],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="bm_admin:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_user_panel_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🔄 Обновить рынок этого игрока", callback_data=f"bm_admin:user:{target_user_id}:refresh")],
        [InlineKeyboardButton(text="📜 История ротаций", callback_data=f"bm_admin:user:{target_user_id}:rotations")],
        [InlineKeyboardButton(text="🧾 История покупок", callback_data=f"bm_admin:user:{target_user_id}:purchases")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="bm_admin:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_pool_keyboard(items) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for item in items:
        state_icon = "✅" if item.active else "🚫"
        label = f"{state_icon} #{item.id} {item.title or texts.ITEM_TYPE_LABELS.get(item.item_type, item.item_type)} ({item.rarity})"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"bm_admin:pool:toggle:{item.id}")])
    keyboard.append(back_row("bm_admin:main"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_admin_refresh_all_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚠️ Подтвердить обновление всем", callback_data="bm_admin:refresh_all:confirm")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="bm_admin:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ---------------------------------------------------------------------------
# "Добавить предмет" — FSM
# ---------------------------------------------------------------------------

def build_add_item_type_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "card": "🃏 CARD",
        "frame": "🖼 FRAME",
        "background": "🌆 BACKGROUND",
        "prefix": "🏷 ПРИПИСКА К НИКУ",
        "pack": "🎁 PACK",
        "currency": "🪙 CURRENCY",
    }
    keyboard = [[InlineKeyboardButton(text=labels[choice], callback_data=f"bm_admin:add_item:type:{choice}")] for choice in ITEM_TYPE_CHOICES]
    keyboard.append(back_row("bm_admin:main"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_cosmetic_source_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="📂 Выбрать существующий", callback_data="bm_admin:add_item:cosmetic_existing")],
        [InlineKeyboardButton(text="🆕 Загрузить новый", callback_data="bm_admin:add_item:cosmetic_new")],
        back_row("bm_admin:add_item:start"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_choice_keyboard(rows: list[tuple[str, str]], back_callback: str) -> InlineKeyboardMarkup:
    """`rows` — список (label, callback_data). Общий билдер для выбора карты/пака/
    валюты/косметики из уже существующих сущностей."""
    keyboard = [[InlineKeyboardButton(text=label, callback_data=callback_data)] for label, callback_data in rows]
    keyboard.append(back_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_rarity_choice_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=f"{texts.RARITY_ICONS.get(rarity, '')} {rarity}", callback_data=f"{callback_prefix}:{rarity}")]
        for rarity in RARITIES
    ]
    keyboard.append(back_row("bm_admin:add_item:start"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_price_mode_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="💰 Фиксированная цена", callback_data="bm_admin:add_item:price_mode:FIXED")],
        [InlineKeyboardButton(text="🎲 Случайный диапазон", callback_data="bm_admin:add_item:price_mode:RANDOM_RANGE")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_yes_no_keyboard(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="✅ Да", callback_data=yes_callback), InlineKeyboardButton(text="❌ Нет", callback_data=no_callback)]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_add_item_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="✅ Создать предмет", callback_data="bm_admin:add_item:confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="bm_admin:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
