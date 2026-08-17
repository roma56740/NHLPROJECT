from __future__ import annotations

from html import escape
import asyncio

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.dna_event import (
    build_dna_choice_keyboard, build_dna_extraction_keyboard, build_dna_extraction_selection_keyboard,
    build_dna_main_keyboard, build_dna_recipe_keyboard, build_dna_result_keyboard, build_dna_tier_keyboard,
)
from app.services.dna_crafting import (
    DNA_STARTER_CHOICE_COST, DNA_TARGETS, DnaCraftError, claim_dna_welcome_collectible,
    craft_dna_card, craft_dna_choice_card, extract_dna_collectibles, get_dna_choice_page,
    get_dna_craft_preview, get_dna_extraction_candidates, get_dna_extraction_previews, get_dna_final_targets,
    get_dna_inventory_progress,
)
from app.services.dna_render import render_dna_event_image

router = Router()


class DnaExtractionState(StatesGroup):
    selecting = State()


async def _replace_with_photo(callback: CallbackQuery, caption: str, reply_markup) -> None:
    if not isinstance(callback.message, Message):
        return
    cards = await asyncio.to_thread(get_dna_final_targets)
    path = await asyncio.to_thread(render_dna_event_image, cards)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.bot.send_photo(chat_id=callback.message.chat.id, photo=FSInputFile(path), caption=caption, reply_markup=reply_markup)


def _main_caption(progress, welcome_granted: bool = False) -> str:
    welcome = "\n🎁 <b>Первый вход:</b> +1 DNA Collectible.\n" if welcome_granted else ""
    return (
        "<b>🧬 DNA — BREAK THE 99 OVR CEILING</b>\n\n"
        "🏛 <b>Исторический рубеж:</b> 99 OVR был потолком игры. DNA впервые выводит карты выше него — "
        "STONE / HUTSON / COOLEY / SCHAEFER 100 OVR становятся <b>первыми 100 OVR картами в истории игры</b>.\n"
        + welcome + "\n"
        "Каждый этап создаёт <b>новую карту</b>; OVR существующей карты никогда не меняется.\n\n"
        "<b>Путь:</b>\n"
        "3× NEXT GEN + 2× 92 + 5 🧬 → DNA 93\n"
        "2× DNA 93 + 2× 94 + 10 🧬 → DNA 95\n"
        "2× DNA 95 + 2× 97 + 20 🧬 → DNA 98\n"
        "1× DNA 98 + 3× 99 + 50 🧬 → <b>DNA 100</b>\n\n"
        f"🧬 Collectibles: <b>{progress.collectibles}</b> · NEXT GEN: <b>{progress.next_gen}</b> · "
        f"DNA 93: <b>{progress.dna_93}</b> · DNA 95: <b>{progress.dna_95}</b> · DNA 98: <b>{progress.dna_98}</b>"
    )


@router.callback_query(F.data == "dna:main")
async def dna_main(callback: CallbackQuery) -> None:
    try:
        granted, _ = await asyncio.to_thread(claim_dna_welcome_collectible, callback.from_user.id)
        progress = await asyncio.to_thread(get_dna_inventory_progress, callback.from_user.id)
    except DnaCraftError as error:
        await callback.answer(error.message, show_alert=True); return
    await _replace_with_photo(callback, _main_caption(progress, granted), build_dna_main_keyboard())
    try: await callback.answer()
    except TelegramBadRequest: pass


@router.callback_query(F.data.startswith("dna:tier:"))
async def dna_tier(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":"); overall = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    if overall not in DNA_TARGETS:
        await callback.answer("Неизвестный этап.", show_alert=True); return
    names = " / ".join(f"{name} {overall}" for name in DNA_TARGETS[overall])
    text = f"<b>🧬 DNA {overall} OVR</b>\n\nВыбери карту:\n<b>{escape(names)}</b>"
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_tier_keyboard(overall))
            else: await callback.message.edit_text(text, reply_markup=build_dna_tier_keyboard(overall))
        except TelegramBadRequest: pass
    await callback.answer()


@router.callback_query(F.data.startswith("dna:view:"))
async def dna_view(callback: CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); overall=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0; surname=parts[3].upper() if len(parts)>3 else ""
    try: preview=await asyncio.to_thread(get_dna_craft_preview, callback.from_user.id, overall, surname)
    except DnaCraftError as error: await callback.answer(error.message, show_alert=True); return
    status="✅ Можно крафтить" if preview.enough and preview.target.available else "❌ Пока недоступно"
    target_status="загружена" if preview.target.available else "НЕ загружена в каталог DNA"
    lines="\n".join(f"• {escape(line)}" for line in preview.ingredient_text)
    text=(f"<b>🧬 {escape(preview.target.surname)} {preview.target.overall} OVR</b>\n\nЦелевая карта: <b>{escape(target_status)}</b>\n\n<b>Нужно:</b>\n{lines}\n\n{status}\n\nИспользуются только свободные карты: не в составе, не Locked, не в обмене, без рамки и не Ranked Captain.")
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_recipe_keyboard(preview))
            else: await callback.message.edit_text(text, reply_markup=build_dna_recipe_keyboard(preview))
        except TelegramBadRequest: pass
    await callback.answer()


@router.callback_query(F.data.startswith("dna:craft:"))
async def dna_craft(callback: CallbackQuery) -> None:
    parts=(callback.data or "").split(":"); overall=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0; surname=parts[3].upper() if len(parts)>3 else ""
    try: result=await asyncio.to_thread(craft_dna_card, callback.from_user.id, overall, surname)
    except DnaCraftError as error: await callback.answer(error.message, show_alert=True); return
    except Exception: await callback.answer("Крафт не завершён. Ничего не списано.", show_alert=True); return
    consumed="\n".join(f"• {escape(label)}" for label in result.consumed_labels)
    text=(f"<b>✅ DNA CRAFT COMPLETE</b>\n\nПолучено: <b>{escape(result.target.name)} {result.target.overall} OVR</b>\nЭкземпляр: <code>#{result.user_card_id}</code>\n\n<b>Использовано:</b>\n{consumed}\n• 🧬 DNA Collectible ×{result.collectibles_spent}")
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_result_keyboard(overall))
            else: await callback.message.edit_text(text, reply_markup=build_dna_result_keyboard(overall))
        except TelegramBadRequest: pass
    await callback.answer("Карта скрафчена")


@router.callback_query(F.data == "dna:progression")
async def dna_progression(callback: CallbackQuery) -> None:
    text=("<b>🧬 DNA — ПРОГРЕССИЯ</b>\n\n"
          "<b>93 OVR</b> — YUROV / MICHKOV\n3× NEXT GEN + 2× 92 OVR + 5 🧬 → выбранная DNA 93\n\n"
          "<b>95 OVR</b> — CAUFIELD / EICHEL\n2× DNA 93 + 2× 94 OVR + 10 🧬 → выбранная DNA 95\n\n"
          "<b>98 OVR</b> — SCHEIFELE / NECAS\n2× DNA 95 + 2× 97 OVR + 20 🧬 → выбранная DNA 98\n\n"
          "<b>100 OVR</b> — STONE / HUTSON / COOLEY / SCHAEFER\n1× DNA 98 + 3× 99 OVR + 50 🧬 → выбранная DNA 100\n\n"
          "99 OVR был прежним техническим потолком. Финальные DNA 100 — первые карты выше этого рубежа.\n\nOVR старой карты не меняется: каждый крафт создаёт новую карту.")
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_main_keyboard())
            else: await callback.message.edit_text(text, reply_markup=build_dna_main_keyboard())
        except TelegramBadRequest: pass
    await callback.answer()


@router.callback_query(F.data == "dna:extract")
async def dna_extract_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        items=await asyncio.to_thread(get_dna_extraction_previews, callback.from_user.id)
        progress=await asyncio.to_thread(get_dna_inventory_progress, callback.from_user.id)
    except DnaCraftError as error:
        await callback.answer(error.message, show_alert=True); return
    lines=[
        "<b>⚗️ DNA EXTRACTION</b>", "", f"Баланс: <b>{progress.collectibles} 🧬</b>", "",
        "Выбери рецепт, затем <b>сам выбери конкретные экземпляры карт</b>, которые хочешь сжечь:",
    ]
    for item in items:
        lines.append(f"• {item.cards_required}× {item.ovr_label} OVR → <b>+{item.collectibles_reward} 🧬</b> · есть {item.available_cards}")
    lines += ["", "DNA-карты автоматически исключены из Extraction.", "Карты в составе, обмене, с рамкой, Locked или Ranked Captain выбрать нельзя."]
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption="\n".join(lines), reply_markup=build_dna_extraction_keyboard(items))
            else: await callback.message.edit_text("\n".join(lines), reply_markup=build_dna_extraction_keyboard(items))
        except TelegramBadRequest: pass
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass


async def _show_extraction_selector(callback: CallbackQuery, state: FSMContext, page_number: int = 1) -> None:
    data = await state.get_data()
    recipe_code = str(data.get("dna_extraction_recipe") or "")
    selected_ids = tuple(int(value) for value in data.get("dna_extraction_selected", []))
    if not recipe_code:
        await callback.answer("Выбор устарел. Открой DNA Extraction заново.", show_alert=True)
        return
    try:
        page = await asyncio.to_thread(
            get_dna_extraction_candidates, callback.from_user.id, recipe_code, page_number
        )
    except DnaCraftError as error:
        await callback.answer(error.message, show_alert=True)
        return

    selected_count = len(selected_ids)
    ready = selected_count == page.recipe.cards_required
    status = "✅ Можно переработать" if ready else f"Выбери ещё {page.recipe.cards_required - selected_count}"
    text = (
        f"<b>⚗️ DNA EXTRACTION · {page.recipe.ovr_label} OVR</b>\n\n"
        f"Нужно выбрать: <b>{page.recipe.cards_required}</b>\n"
        f"Награда: <b>+{page.recipe.collectibles_reward} 🧬</b>\n"
        f"Выбрано: <b>{selected_count}/{page.recipe.cards_required}</b>\n\n"
        "Нажимай на <b>конкретные карты</b> ниже. Повторное нажатие снимает выбор.\n"
        f"{status}\n\nСтраница {page.page}/{page.pages_count} · доступно карт: {page.total_count}"
    )
    if isinstance(callback.message, Message):
        try:
            markup = build_dna_extraction_selection_keyboard(page, selected_ids)
            if callback.message.photo:
                await callback.message.edit_caption(caption=text, reply_markup=markup)
            else:
                await callback.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data.startswith("dna:extract:"))
async def dna_extract_select_recipe(callback: CallbackQuery, state: FSMContext) -> None:
    code=(callback.data or "").split(":",2)[2]
    try:
        page = await asyncio.to_thread(get_dna_extraction_candidates, callback.from_user.id, code, 1)
    except DnaCraftError as error:
        await callback.answer(error.message, show_alert=True); return
    if page.total_count < page.recipe.cards_required:
        await callback.answer("Не хватает свободных карт для этого рецепта.", show_alert=True)
        return
    await state.set_state(DnaExtractionState.selecting)
    await state.update_data(dna_extraction_recipe=code, dna_extraction_selected=[])
    await _show_extraction_selector(callback, state, 1)
    await callback.answer("Выбери конкретные карты")


@router.callback_query(F.data.startswith("dna:expage:"))
async def dna_extract_page(callback: CallbackQuery, state: FSMContext) -> None:
    raw=(callback.data or "").split(":")
    page=int(raw[2]) if len(raw) > 2 and raw[2].isdigit() else 1
    await _show_extraction_selector(callback, state, page)
    await callback.answer()


@router.callback_query(F.data.startswith("dna:extoggle:"))
async def dna_extract_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    raw=(callback.data or "").split(":")
    if len(raw) < 4 or not raw[2].isdigit():
        await callback.answer("Некорректная карта.", show_alert=True); return
    user_card_id=int(raw[2])
    page=int(raw[3]) if raw[3].isdigit() else 1
    data=await state.get_data()
    recipe_code=str(data.get("dna_extraction_recipe") or "")
    selected=[int(value) for value in data.get("dna_extraction_selected", [])]
    if not recipe_code:
        await callback.answer("Выбор устарел. Открой Extraction заново.", show_alert=True); return
    try:
        current_page=await asyncio.to_thread(get_dna_extraction_candidates, callback.from_user.id, recipe_code, page)
    except DnaCraftError as error:
        await callback.answer(error.message, show_alert=True); return
    visible_ids={card.user_card_id for card in current_page.items}
    if user_card_id not in visible_ids:
        await callback.answer("Эта карта больше недоступна.", show_alert=True); return
    if user_card_id in selected:
        selected.remove(user_card_id)
    else:
        if len(selected) >= current_page.recipe.cards_required:
            await callback.answer(f"Можно выбрать только {current_page.recipe.cards_required} карт(ы). Сними одну из выбранных.", show_alert=True)
            return
        selected.append(user_card_id)
    await state.update_data(dna_extraction_selected=selected)
    await _show_extraction_selector(callback, state, page)
    await callback.answer(f"Выбрано {len(selected)}/{current_page.recipe.cards_required}")


@router.callback_query(F.data == "dna:exreset")
async def dna_extract_reset(callback: CallbackQuery, state: FSMContext) -> None:
    data=await state.get_data()
    if not data.get("dna_extraction_recipe"):
        await callback.answer("Выбор уже сброшен."); return
    await state.update_data(dna_extraction_selected=[])
    await _show_extraction_selector(callback, state, 1)
    await callback.answer("Выбор сброшен")


@router.callback_query(F.data == "dna:exconfirm")
async def dna_extract_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data=await state.get_data()
    recipe_code=str(data.get("dna_extraction_recipe") or "")
    selected_ids=tuple(int(value) for value in data.get("dna_extraction_selected", []))
    if not recipe_code:
        await callback.answer("Выбор устарел. Открой Extraction заново.", show_alert=True); return
    try:
        result=await asyncio.to_thread(
            extract_dna_collectibles, callback.from_user.id, recipe_code, selected_ids
        )
    except DnaCraftError as error:
        await callback.answer(error.message, show_alert=True)
        await state.update_data(dna_extraction_selected=[])
        await _show_extraction_selector(callback, state, 1)
        return
    except Exception:
        await callback.answer("Переработка не завершена. Карты не списаны.", show_alert=True)
        return

    await state.clear()
    consumed="\n".join(f"• {escape(label)}" for label in result.consumed_labels)
    text=(
        f"<b>✅ DNA EXTRACTION COMPLETE</b>\n\n"
        f"Получено: <b>+{result.recipe.collectibles_reward} 🧬 DNA Collectible</b>\n"
        f"Баланс: <b>{result.collectible_balance} 🧬</b>\n\n"
        f"<b>Переработаны именно выбранные карты:</b>\n{consumed}"
    )
    try:
        items=await asyncio.to_thread(get_dna_extraction_previews, callback.from_user.id)
        markup=build_dna_extraction_keyboard(items)
        if isinstance(callback.message, Message):
            if callback.message.photo:
                await callback.message.edit_caption(caption=text, reply_markup=markup)
            else:
                await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    await callback.answer(f"+{result.recipe.collectibles_reward} 🧬")


@router.callback_query(F.data.startswith("dna:choice:"))
async def dna_choice_menu(callback: CallbackQuery) -> None:
    raw=(callback.data or "").split(":"); page=int(raw[2]) if len(raw)>2 and raw[2].isdigit() else 1
    try: choice=await asyncio.to_thread(get_dna_choice_page, callback.from_user.id, page)
    except DnaCraftError as error: await callback.answer(error.message, show_alert=True); return
    if choice.claimed:
        text="<b>🎁 95–96 CHOICE CRAFT</b>\n\n✅ Этот крафт уже использован на аккаунте.\nЛимит: 1 раз."
    else:
        text=(f"<b>🎁 95–96 CHOICE CRAFT</b>\n\nЦена: <b>{DNA_STARTER_CHOICE_COST} 🧬 DNA Collectibles</b>\nБаланс: <b>{choice.collectibles} 🧬</b>\n\nВыбери одну активную 95–96 OVR карту из доступного пула. Эксклюзивные коллекции и DNA сюда не входят.\nСтраница {choice.page}/{choice.pages_count} · карт {choice.total_count}")
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_choice_keyboard(choice))
            else: await callback.message.edit_text(text, reply_markup=build_dna_choice_keyboard(choice))
        except TelegramBadRequest: pass
    await callback.answer()


@router.callback_query(F.data.startswith("dna:choice_craft:"))
async def dna_choice_craft(callback: CallbackQuery) -> None:
    raw=(callback.data or "").split(":"); card_id=int(raw[2]) if len(raw)>2 and raw[2].isdigit() else 0
    try: result=await asyncio.to_thread(craft_dna_choice_card, callback.from_user.id, card_id)
    except DnaCraftError as error: await callback.answer(error.message, show_alert=True); return
    await callback.answer(f"Получено: {result.card.name} {result.card.overall} OVR", show_alert=True)
    if isinstance(callback.message, Message):
        text=(f"<b>✅ 95–96 CHOICE COMPLETE</b>\n\nПолучено: <b>{escape(result.card.name)} {result.card.overall} OVR</b>\nЭкземпляр: <code>#{result.user_card_id}</code>\nОсталось: <b>{result.collectible_balance} 🧬</b>\n\nЭтот Choice Craft доступен один раз на аккаунт.")
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_main_keyboard())
            else: await callback.message.edit_text(text, reply_markup=build_dna_main_keyboard())
        except TelegramBadRequest: pass


@router.callback_query(F.data == "dna:inventory")
async def dna_inventory(callback: CallbackQuery) -> None:
    try: progress=await asyncio.to_thread(get_dna_inventory_progress, callback.from_user.id)
    except DnaCraftError as error: await callback.answer(error.message, show_alert=True); return
    choice="использован ✅" if progress.starter_choice_claimed else "доступен"
    text=(f"<b>🎒 DNA ПРЕДМЕТЫ</b>\n\n🧬 DNA Collectible: <b>{progress.collectibles}</b>\n🎁 95–96 Choice Craft: <b>{choice}</b>\n\nCollectible — отдельный stackable item, это не карточка игрока.")
    if isinstance(callback.message, Message):
        try:
            if callback.message.photo: await callback.message.edit_caption(caption=text, reply_markup=build_dna_main_keyboard())
            else: await callback.message.edit_text(text, reply_markup=build_dna_main_keyboard())
        except TelegramBadRequest: pass
    await callback.answer()


@router.callback_query(F.data == "dna:no_target")
async def dna_no_target(callback: CallbackQuery) -> None: await callback.answer("Сначала загрузи эту карту в коллекцию DNA через админку.", show_alert=True)

@router.callback_query(F.data == "dna:not_enough")
async def dna_not_enough(callback: CallbackQuery) -> None: await callback.answer("Не хватает свободных карт или DNA Collectibles.", show_alert=True)

@router.callback_query(F.data == "dna:noop")
async def dna_noop(callback: CallbackQuery) -> None: await callback.answer()
