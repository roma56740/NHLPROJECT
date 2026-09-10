from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.database.db import get_connection
from app.keyboards.inventory import (
    build_card_xfactors_keyboard, build_eligible_cards_keyboard, build_install_confirm_keyboard,
    build_inventory_main_keyboard, build_remove_confirm_keyboard, build_xfactor_detail_keyboard,
    build_xfactor_inventory_keyboard, build_xfactor_sell_confirm_keyboard,
)
from app.services.mastery import get_mastery_player
from app.services.users import get_player_profile_by_telegram_id
from app.services.xfactors import (
    get_eligible_cards_for_xfactor, get_installed_xfactors, get_user_xfactor_inventory,
    get_user_xfactor_quantity, get_xfactor_by_code, install_xfactor, quicksell_xfactor,
    remove_installed_xfactor,
)

router=Router()


async def _edit(callback:CallbackQuery,text:str,keyboard) -> None:
    if isinstance(callback.message,Message):
        try: await callback.message.edit_text(text,reply_markup=keyboard)
        except Exception:
            try: await callback.message.delete()
            except Exception: pass
            await callback.bot.send_message(callback.message.chat.id,text,reply_markup=keyboard)


@router.callback_query(F.data=="inventory:main")
async def inventory_main(callback:CallbackQuery) -> None:
    await _edit(callback,"<b>🎒 Инвентарь</b>\n\nCollectibles и X-Factors хранятся отдельно от карточек.",build_inventory_main_keyboard())
    await callback.answer()


@router.callback_query(F.data=="inventory:collectibles")
async def inventory_collectibles(callback:CallbackQuery) -> None:
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None: await callback.answer("Открой игру через /start",show_alert=True); return
    with get_connection() as connection:
        rows=connection.execute("""SELECT i.title,u.quantity FROM user_items u JOIN inventory_items i ON i.id=u.item_id
                                   WHERE u.user_id=? AND u.quantity>0 ORDER BY i.title COLLATE NOCASE""",(profile.id,)).fetchall()
    lines=["<b>🧩 Collectibles</b>",""]
    lines.extend(f"• {escape(str(row['title']))}: <b>×{int(row['quantity'])}</b>" for row in rows)
    if not rows: lines.append("Пока пусто.")
    await _edit(callback,"\n".join(lines),build_inventory_main_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("inventory:xfactors:"))
async def inventory_xfactors(callback:CallbackQuery) -> None:
    page=int((callback.data or "").split(":")[-1])
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None: await callback.answer("Открой игру через /start",show_alert=True); return
    items,page,pages,total=get_user_xfactor_inventory(profile.id,page)
    text=f"<b>⚡ X-Factors</b>\n\nПредметов в инвентаре: <b>{sum(i.quantity for i in items) if pages==1 else total}</b>\nВыбери фактор для установки на карту."
    if not items: text+="\n\nПока пусто."
    await _edit(callback,text,build_xfactor_inventory_keyboard(items,page,pages))
    await callback.answer()


@router.callback_query(F.data.startswith("inventory:xf:"))
async def inventory_xfactor_detail(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); code=parts[2]; page=int(parts[3]) if len(parts)>3 else 1
    profile=await get_player_profile_by_telegram_id(callback.from_user.id); xf=get_xfactor_by_code(code)
    if profile is None or xf is None: await callback.answer("X-Factor не найден",show_alert=True); return
    qty=get_user_xfactor_quantity(profile.id,code)
    restriction=f"\n👑 Только для: <b>{escape(xf.mastery_player_key or '')}</b>" if xf.is_mastery else ""
    text=(f"<b>{'👑' if xf.is_mastery else '⚡'} {escape(xf.name)}</b>\n\n{escape(xf.description)}\n\n"
          f"Позиция: <b>{xf.role}</b>\nВ инвентаре: <b>×{qty}</b>{restriction}")
    await _edit(callback,text,build_xfactor_detail_keyboard(code,page,xf.is_mastery)); await callback.answer()


@router.callback_query(F.data.startswith("inventory:xf_sell_confirm:"))
async def inventory_xf_sell_confirm(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); code=parts[2]; page=int(parts[3])
    xf=get_xfactor_by_code(code)
    if xf is None or xf.is_mastery: await callback.answer("Продажа недоступна",show_alert=True); return
    await _edit(callback,f"<b>Quick Sell</b>\n\nПродать <b>{escape(xf.name)}</b> ×1 за <b>20 000 Coins</b>?\nБудет продан только один предмет.",build_xfactor_sell_confirm_keyboard(code,page)); await callback.answer()


@router.callback_query(F.data.startswith("inventory:xf_sell:"))
async def inventory_xf_sell(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); code=parts[2]; page=int(parts[3])
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    result=quicksell_xfactor(profile.id,code) if profile else None
    if result is None: await callback.answer("Профиль не найден",show_alert=True); return
    await callback.answer(result.message,show_alert=not result.success)
    callback.data=f"inventory:xfactors:{page}"; await inventory_xfactors(callback)


@router.callback_query(F.data.startswith("inventory:xf_install:"))
async def inventory_xf_install(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); code=parts[2]; page=int(parts[3]); inventory_page=int(parts[4]) if len(parts)>4 else 1
    profile=await get_player_profile_by_telegram_id(callback.from_user.id); xf=get_xfactor_by_code(code)
    if profile is None or xf is None: await callback.answer("X-Factor не найден",show_alert=True); return
    all_rows=get_eligible_cards_for_xfactor(profile.id,code,limit=200)
    per=7; pages=max(1,ceil(len(all_rows)/per)); page=min(max(1,page),pages); rows=all_rows[(page-1)*per:page*per]
    text=f"<b>➕ Установить {escape(xf.name)}</b>\n\nВыбери подходящий экземпляр карты. На одной карте максимум 3 X-Factors."
    if not rows: text+="\n\nПодходящих карт нет."
    await _edit(callback,text,build_eligible_cards_keyboard(rows,page,pages,code,inventory_page)); await callback.answer()


@router.callback_query(F.data.startswith("inventory:xf_card:"))
async def inventory_xf_card(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); code=parts[2]; user_card_id=int(parts[3]); return_page=int(parts[4]); inventory_page=int(parts[5])
    installed=get_installed_xfactors(user_card_id); xf=get_xfactor_by_code(code)
    if xf is None: await callback.answer("X-Factor не найден",show_alert=True); return
    if len(installed)>=3:
        details="\n".join(f"• слот {item.slot_no}: <b>{escape(item.xfactor.name)}</b>" for item in installed)
        text=f"<b>⚠️ На карте уже 3 X-Factors</b>\n\n{details}\n\nВыбери фактор для замены. Старый фактор будет <b>уничтожен</b>, новый предмет будет израсходован."
    else:
        text=f"Установить <b>{escape(xf.name)}</b> на карту?\n\nПредмет будет израсходован из инвентаря."
    await _edit(callback,text,build_install_confirm_keyboard(code,user_card_id,return_page,inventory_page,installed)); await callback.answer()


@router.callback_query(F.data.startswith("inventory:xf_apply:"))
async def inventory_xf_apply(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); code=parts[2]; user_card_id=int(parts[3]); slot=int(parts[4]); return_page=int(parts[5]); inventory_page=int(parts[6])
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    result=install_xfactor(profile.id,user_card_id,code,replace_slot=(slot or None)) if profile else None
    if result is None: await callback.answer("Профиль не найден",show_alert=True); return
    await callback.answer(result.message,show_alert=not result.success)
    if result.success:
        callback.data=f"inventory:xf:{code}:{inventory_page}"; await inventory_xfactor_detail(callback)
    else:
        callback.data=f"inventory:xf_install:{code}:{return_page}:{inventory_page}"; await inventory_xf_install(callback)


@router.callback_query(F.data.startswith("cardxf:view:"))
async def card_xfactors_view(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); user_card_id=int(parts[2]); page=int(parts[3])
    installed=get_installed_xfactors(user_card_id)
    lines=["<b>⚡ X-Factors карты</b>",""]
    if installed:
        lines.extend(f"<b>{item.slot_no}. {escape(item.xfactor.name)}</b>\n{escape(item.xfactor.description)}" for item in installed)
        lines.append("\nЧтобы снять фактор, выбери его ниже. Снятый фактор уничтожается.")
    else: lines.append("На этой карте пока нет X-Factors.")
    await _edit(callback,"\n\n".join(lines),build_card_xfactors_keyboard(user_card_id,page,installed)); await callback.answer()


@router.callback_query(F.data.startswith("cardxf:remove_confirm:"))
async def card_xfactor_remove_confirm(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); user_card_id=int(parts[2]); slot=int(parts[3]); page=int(parts[4])
    installed={item.slot_no:item for item in get_installed_xfactors(user_card_id)}; item=installed.get(slot)
    if item is None: await callback.answer("X-Factor не найден",show_alert=True); return
    await _edit(callback,f"<b>⚠️ Уничтожить X-Factor?</b>\n\n{escape(item.xfactor.name)} будет снят с карты и <b>не вернётся в инвентарь</b>.",build_remove_confirm_keyboard(user_card_id,slot,page)); await callback.answer()


@router.callback_query(F.data.startswith("cardxf:remove:"))
async def card_xfactor_remove(callback:CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); user_card_id=int(parts[2]); slot=int(parts[3]); page=int(parts[4])
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    result=remove_installed_xfactor(profile.id,user_card_id,slot) if profile else None
    if result is None: await callback.answer("Профиль не найден",show_alert=True); return
    await callback.answer(result.message,show_alert=not result.success)
    callback.data=f"cardxf:view:{user_card_id}:{page}"; await card_xfactors_view(callback)


@router.callback_query(F.data=="inventory:page")
async def inventory_page_info(callback:CallbackQuery) -> None:
    await callback.answer()
