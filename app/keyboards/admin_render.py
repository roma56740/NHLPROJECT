from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


ASSET_BUTTONS = [
    ("render_menu_background_path", "🏠 Фон меню"),
    ("render_menu_video_path", "🎬 Видео меню"),
    ("render_lineup_background_path", "🧊 Дефолтный фон состава"),
]

TEXT_BUTTONS = [
    ("render_menu_title", "✏️ Заголовок меню"),
    ("render_menu_subtitle", "✏️ Подзаголовок меню"),
    ("render_menu_accent", "🎨 Цвет меню"),
    ("render_lineup_accent", "🎨 Цвет состава"),
]


def build_admin_render_keyboard(chemistry_enabled: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, title in ASSET_BUTTONS:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"admin_render:asset:{key}")])
    for key, title in TEXT_BUTTONS:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"admin_render:text:{key}")])
    rows.append([
        InlineKeyboardButton(
            text=f"🧪 Химия: {'ВКЛ' if chemistry_enabled else 'ВЫКЛ'}",
            callback_data="admin_render:toggle_chemistry",
        )
    ])
    rows.append([
        InlineKeyboardButton(text="👁 Превью меню", callback_data="admin_render:preview:menu"),
        InlineKeyboardButton(text="👁 Превью состава", callback_data="admin_render:preview:lineup"),
    ])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-меню", callback_data="menu:admin:content")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_render_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_render:main")]]
    )
