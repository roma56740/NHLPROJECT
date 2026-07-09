from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_salaries import SalaryCardsPage, SalaryCollectionItem

SALARY_PER_PAGE = 8


def build_admin_salaries_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Показать всех с 0", callback_data="admin_salaries:list:zero:1")],
        [InlineKeyboardButton(text="💰 Самые дорогие", callback_data="admin_salaries:list:highest:1")],
        [InlineKeyboardButton(text="🗂 Поставить всей коллекции", callback_data="admin_salaries:collections")],
        [InlineKeyboardButton(text="🧩 Заполнить все нули", callback_data="admin_salaries:set_zero")],
        [InlineKeyboardButton(text="⭐ Зарплата по OVR", callback_data="admin_salaries:ovr_range")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_salaries:main")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
    ])


def build_salary_cards_keyboard(page: SalaryCardsPage) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"admin_salaries:list:{page.mode}:{max(page.page-1,1)}"),
            InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_salaries:noop"),
            InlineKeyboardButton(text="➡️", callback_data=f"admin_salaries:list:{page.mode}:{min(page.page+1,page.pages_count)}"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_salaries:main")],
    ])


def build_salary_collections_keyboard(collections: list[SalaryCollectionItem]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🗂 {c.name}", callback_data=f"admin_salaries:collection:{c.id}")] for c in collections]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_salaries:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_collection_salary_mode_keyboard(collection_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поставить всем", callback_data=f"admin_salaries:collection_mode:{collection_id}:all")],
        [InlineKeyboardButton(text="Только тем, у кого 0", callback_data=f"admin_salaries:collection_mode:{collection_id}:zero")],
        [InlineKeyboardButton(text="⬅️ К коллекциям", callback_data="admin_salaries:collections")],
    ])


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_salaries:main")]])
