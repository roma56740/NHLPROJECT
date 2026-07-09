from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.admin_divisions import AnimationAssetsPage, DivisionItem, TeamAssignmentsPage

ADMIN_DIVISIONS_PER_PAGE = 8


def build_admin_divisions_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать дивизион", callback_data="admin_divisions:create")],
        [InlineKeyboardButton(text="🏒 Список дивизионов", callback_data="admin_divisions:list")],
        [InlineKeyboardButton(text="🛡 Картинки команд", callback_data="admin_divisions:assets:team:1")],
        [InlineKeyboardButton(text="🌍 Картинки стран", callback_data="admin_divisions:assets:country:1")],
        [InlineKeyboardButton(text="⚠️ Проверить недостающее", callback_data="admin_divisions:missing")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
    ])


def build_admin_divisions_list_keyboard(divisions: list[DivisionItem]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{'✅' if d.active else '⏸'} {d.name} · {d.teams_count}", callback_data=f"admin_divisions:view:{d.id}")] for d in divisions]
    rows.append([InlineKeyboardButton(text="➕ Создать дивизион", callback_data="admin_divisions:create")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_divisions:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_division_profile_keyboard(division: DivisionItem) -> InlineKeyboardMarkup:
    active_text = "⏸ Выключить" if division.active else "✅ Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить/убрать команды", callback_data=f"admin_divisions:teams:{division.id}:1")],
        [InlineKeyboardButton(text="🖼 Загрузить картинку дивизиона", callback_data=f"admin_divisions:image:{division.id}")],
        [InlineKeyboardButton(text=active_text, callback_data=f"admin_divisions:toggle:{division.id}")],
        [InlineKeyboardButton(text="⬅️ К дивизионам", callback_data="admin_divisions:list")],
    ])


def build_team_assignments_keyboard(division_id: int, page: TeamAssignmentsPage) -> InlineKeyboardMarkup:
    rows = []
    for item in page.teams:
        if item.selected:
            mark = "✅"
        elif item.division_id is not None:
            mark = "↪️"
        else:
            mark = "➕"
        rows.append([InlineKeyboardButton(text=f"{mark} {item.team_name}", callback_data=f"admin_divisions:toggle_team:{division_id}:{page.page}:{item.team_name}")])
    rows.append([
        InlineKeyboardButton(text="⬅️", callback_data=f"admin_divisions:teams:{division_id}:{max(page.page-1,1)}"),
        InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_divisions:noop"),
        InlineKeyboardButton(text="➡️", callback_data=f"admin_divisions:teams:{division_id}:{min(page.page+1,page.pages_count)}"),
    ])
    rows.append([InlineKeyboardButton(text="⬅️ К дивизиону", callback_data=f"admin_divisions:view:{division_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_assets_keyboard(page: AnimationAssetsPage) -> InlineKeyboardMarkup:
    rows = []
    for item in page.assets:
        mark = "✅" if item.exists else "⚠️"
        rows.append([InlineKeyboardButton(text=f"{mark} {item.asset_key}", callback_data=f"admin_divisions:asset_upload:{page.asset_type}:{page.page}:{item.asset_key}")])
    rows.append([
        InlineKeyboardButton(text="⬅️", callback_data=f"admin_divisions:assets:{page.asset_type}:{max(page.page-1,1)}"),
        InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="admin_divisions:noop"),
        InlineKeyboardButton(text="➡️", callback_data=f"admin_divisions:assets:{page.asset_type}:{min(page.page+1,page.pages_count)}"),
    ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_divisions:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_divisions:main")]])


def build_missing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏒 Дивизионы", callback_data="admin_divisions:list")],
        [InlineKeyboardButton(text="🛡 Картинки команд", callback_data="admin_divisions:assets:team:1")],
        [InlineKeyboardButton(text="🌍 Картинки стран", callback_data="admin_divisions:assets:country:1")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_divisions:missing")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_divisions:main")],
    ])
