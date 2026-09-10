from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.xfactors import InstalledXFactor, UserXFactorItem


def build_inventory_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Collectibles",callback_data="inventory:collectibles")],
        [InlineKeyboardButton(text="⚡ X-Factors",callback_data="inventory:xfactors:1")],
        [InlineKeyboardButton(text="⬅️ Главное меню",callback_data="menu:main")],
    ])


def build_xfactor_inventory_keyboard(items: list[UserXFactorItem], page:int, pages:int) -> InlineKeyboardMarkup:
    rows=[]
    for item in items:
        marker="👑" if item.xfactor.is_mastery else "⚡"
        rows.append([InlineKeyboardButton(text=f"{marker} {item.xfactor.name} ×{item.quantity}",callback_data=f"inventory:xf:{item.xfactor.code}:{page}")])
    nav=[]
    if page>1: nav.append(InlineKeyboardButton(text="⬅️",callback_data=f"inventory:xfactors:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}",callback_data="inventory:page"))
    if page<pages: nav.append(InlineKeyboardButton(text="➡️",callback_data=f"inventory:xfactors:{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Инвентарь",callback_data="inventory:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_xfactor_detail_keyboard(code:str,page:int,is_mastery:bool) -> InlineKeyboardMarkup:
    rows=[[InlineKeyboardButton(text="➕ Установить на карту",callback_data=f"inventory:xf_install:{code}:1:{page}")]]
    if not is_mastery:
        rows.append([InlineKeyboardButton(text="💰 Quick Sell · 20 000",callback_data=f"inventory:xf_sell_confirm:{code}:{page}")])
    rows.append([InlineKeyboardButton(text="⬅️ К X-Factors",callback_data=f"inventory:xfactors:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_xfactor_sell_confirm_keyboard(code:str,page:int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продать 1 за 20 000",callback_data=f"inventory:xf_sell:{code}:{page}")],
        [InlineKeyboardButton(text="❌ Отмена",callback_data=f"inventory:xf:{code}:{page}")],
    ])


def build_eligible_cards_keyboard(rows,page:int,pages:int,code:str,inventory_page:int) -> InlineKeyboardMarkup:
    kb=[]
    for row in rows:
        kb.append([InlineKeyboardButton(text=f"{row['name']} · {row['overall']} · {row['xfactor_count']}/3",callback_data=f"inventory:xf_card:{code}:{row['user_card_id']}:{page}:{inventory_page}")])
    nav=[]
    if page>1: nav.append(InlineKeyboardButton(text="⬅️",callback_data=f"inventory:xf_install:{code}:{page-1}:{inventory_page}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}",callback_data="inventory:page"))
    if page<pages: nav.append(InlineKeyboardButton(text="➡️",callback_data=f"inventory:xf_install:{code}:{page+1}:{inventory_page}"))
    kb.append(nav)
    kb.append([InlineKeyboardButton(text="⬅️ К фактору",callback_data=f"inventory:xf:{code}:{inventory_page}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def build_install_confirm_keyboard(code:str,user_card_id:int,return_page:int,inventory_page:int,installed:list[InstalledXFactor]) -> InlineKeyboardMarkup:
    rows=[]
    if len(installed)<3:
        rows.append([InlineKeyboardButton(text="✅ Установить",callback_data=f"inventory:xf_apply:{code}:{user_card_id}:0:{return_page}:{inventory_page}")])
    else:
        for item in installed:
            rows.append([InlineKeyboardButton(text=f"♻️ Заменить {item.slot_no}: {item.xfactor.name}",callback_data=f"inventory:xf_apply:{code}:{user_card_id}:{item.slot_no}:{return_page}:{inventory_page}")])
    rows.append([InlineKeyboardButton(text="❌ Отмена",callback_data=f"inventory:xf_install:{code}:{return_page}:{inventory_page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_card_xfactors_keyboard(user_card_id:int,page:int,installed:list[InstalledXFactor]) -> InlineKeyboardMarkup:
    rows=[]
    for item in installed:
        rows.append([InlineKeyboardButton(text=f"🗑 {item.slot_no}. {item.xfactor.name}",callback_data=f"cardxf:remove_confirm:{user_card_id}:{item.slot_no}:{page}")])
    rows.append([InlineKeyboardButton(text="⬅️ К карточке",callback_data=f"user_cards:view:{user_card_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_remove_confirm_keyboard(user_card_id:int,slot:int,page:int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Снять и уничтожить",callback_data=f"cardxf:remove:{user_card_id}:{slot}:{page}")],
        [InlineKeyboardButton(text="❌ Отмена",callback_data=f"cardxf:view:{user_card_id}:{page}")],
    ])
