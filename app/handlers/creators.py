from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.creators import (
    AdminCreatorLevelStates,
    CreatorApplyStates,
    CreatorDistributeStates,
    build_admin_app_view_keyboard,
    build_admin_apps_keyboard,
    build_admin_creator_cancel_keyboard,
    build_admin_creator_manage_keyboard,
    build_admin_creators_list_keyboard,
    build_admin_creators_main_keyboard,
    build_admin_level_edit_keyboard,
    build_admin_levels_keyboard,
    build_admin_settings_cancel_keyboard,
    build_creator_apply_cancel_keyboard,
    build_creator_bank_add_keyboard,
    build_creator_bank_items_keyboard,
    build_creator_cancel_keyboard,
    build_creator_currency_pick_keyboard,
    build_creator_intro_keyboard,
    build_creator_pack_deposit_keyboard,
    build_creator_panel_keyboard,
)
from app.services.community import get_user_id_by_telegram_id
from app.services.creators import (
    add_card_to_bank,
    add_currency_to_bank,
    add_pack_to_bank,
    distribute_bank_item,
    get_application,
    get_bank_item,
    get_creator_detail,
    get_distribution_history,
    get_level_config,
    get_level_configs,
    get_panel,
    get_pending_applications,
    get_creator_chat_invite_link,
    is_creator,
    list_creators,
    list_currencies_for_bank,
    list_packs_for_bank,
    pay_weekly_rewards,
    resolve_application,
    revoke_creator,
    set_creator_author_code,
    set_creator_chat_invite_link,
    set_creator_level,
    set_creator_subscribers,
    submit_application,
    update_level_config_from_text,
    update_level_personal_rewards,
    format_int,
)
from app.texts.creators import (
    ADMIN_CREATORS_BUTTON_TEXT,
    ADMIN_CREATORS_MAIN_TEXT,
    CREATOR_APPLY_CHANNEL_TEXT,
    CREATOR_APPLY_DESC_TEXT,
    CREATOR_APPLY_SUBS_TEXT,
    CREATOR_BUTTON_TEXT,
    CREATOR_INTRO_TEXT,
    build_admin_application_text,
    build_admin_creator_detail_text,
    build_admin_creators_list_text,
    build_admin_level_config_text,
    build_admin_levels_text,
    build_creator_history_text,
    build_creator_panel_text,
)
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


# ---------------------------------------------------------------------------
# Игрок
# ---------------------------------------------------------------------------

@router.message(F.text == CREATOR_BUTTON_TEXT)
async def creator_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()
    await safe_delete_message(message)
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    if user_id is None:
        await message.answer("🏒 Открой игру через /start.")
        return
    creator = await is_creator(user_id)
    await message.answer(CREATOR_INTRO_TEXT, reply_markup=build_creator_intro_keyboard(creator))


@router.callback_query(F.data == "creator:intro")
async def creator_intro(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    creator = await is_creator(user_id) if user_id else False
    await edit_or_send(callback, CREATOR_INTRO_TEXT, reply_markup=build_creator_intro_keyboard(creator))
    await callback.answer()


@router.callback_query(F.data == "creator:apply")
async def creator_apply(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CreatorApplyStates.waiting_for_channel)
    await edit_or_send(callback, CREATOR_APPLY_CHANNEL_TEXT, reply_markup=build_creator_apply_cancel_keyboard())
    await callback.answer()


@router.message(CreatorApplyStates.waiting_for_channel)
async def creator_apply_channel(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    await state.update_data(channel=message.text or "")
    await state.set_state(CreatorApplyStates.waiting_for_subs)
    await message.answer(CREATOR_APPLY_SUBS_TEXT, reply_markup=build_creator_apply_cancel_keyboard())


@router.message(CreatorApplyStates.waiting_for_subs)
async def creator_apply_subs(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи число подписчиков.", reply_markup=build_creator_apply_cancel_keyboard())
        return
    await state.update_data(subscribers=int(raw))
    await state.set_state(CreatorApplyStates.waiting_for_description)
    await message.answer(CREATOR_APPLY_DESC_TEXT, reply_markup=build_creator_apply_cancel_keyboard())


@router.message(CreatorApplyStates.waiting_for_description)
async def creator_apply_desc(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    data = await state.get_data()
    await state.clear()
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    if user_id is None:
        await message.answer("🏒 Открой игру через /start.")
        return
    ok, msg = await submit_application(user_id, data.get("channel", ""), int(data.get("subscribers", 0)), message.text or "")

    if ok:
        for admin_id in _admin_ids():
            try:
                await message.bot.send_message(chat_id=admin_id, text="⭐ Новая заявка в программу креаторов. Открой раздел «Креаторы».")
            except Exception:
                pass

    creator = await is_creator(user_id)
    await message.answer(f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_intro_keyboard(creator))


@router.callback_query(F.data == "creator:panel")
async def creator_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None or not await is_creator(user_id):
        await callback.answer("Панель доступна только креаторам", show_alert=True)
        return
    panel = await get_panel(user_id)
    await edit_or_send(callback, build_creator_panel_text(panel), reply_markup=build_creator_panel_keyboard(panel))
    await callback.answer()


@router.callback_query(F.data == "creator:history")
async def creator_history(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None or not await is_creator(user_id):
        await callback.answer("Только для креаторов", show_alert=True)
        return
    history = await get_distribution_history(user_id)
    await edit_or_send(callback, build_creator_history_text(history), reply_markup=build_creator_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "creator:bank_add")
async def creator_bank_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None or not await is_creator(user_id):
        await callback.answer("Только для креаторов", show_alert=True)
        return
    currencies = await list_currencies_for_bank(user_id)
    packs = await list_packs_for_bank(user_id)
    text = (
        "<b>➕ Пополнение банка выдачи</b>\n\n"
        "Можно добавить валюту, пак или карту. После добавления вывести награду обратно нельзя. "
        "В статистику разыгранных монет это попадёт только после выдачи игроку."
    )
    await edit_or_send(callback, text, reply_markup=build_creator_bank_add_keyboard(bool(currencies), bool(packs)))
    await callback.answer()


@router.callback_query(F.data == "creator:add_currency")
async def creator_add_currency(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    currencies = await list_currencies_for_bank(user_id) if user_id else []
    if not currencies:
        await callback.answer("Нет валюты для добавления", show_alert=True)
        return
    await edit_or_send(callback, "<b>💱 Добавить валюту</b>\n\nВыбери валюту:", reply_markup=build_creator_currency_pick_keyboard(currencies))
    await callback.answer()


@router.callback_query(F.data.startswith("creator:add_currency_pick:"))
async def creator_add_currency_pick(callback: CallbackQuery, state: FSMContext) -> None:
    code = callback.data.split(":")[-1] if callback.data else ""
    await state.set_state(CreatorDistributeStates.waiting_for_currency_amount)
    await state.update_data(currency_code=code)
    await edit_or_send(callback, f"Сколько {code} добавить в банк выдачи?", reply_markup=build_creator_cancel_keyboard())
    await callback.answer()


@router.message(CreatorDistributeStates.waiting_for_currency_amount)
async def creator_add_currency_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введи число.", reply_markup=build_creator_cancel_keyboard())
        return
    data = await state.get_data()
    await state.clear()
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    ok, msg = await add_currency_to_bank(user_id, str(data.get("currency_code") or ""), int(raw))
    panel = await get_panel(user_id)
    await message.answer(f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_panel_keyboard(panel))


@router.callback_query(F.data == "creator:add_pack")
async def creator_add_pack(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    packs = await list_packs_for_bank(user_id) if user_id else []
    if not packs:
        await callback.answer("Нет паков для добавления", show_alert=True)
        return
    await edit_or_send(callback, "<b>🎁 Добавить пак</b>\n\nВыбери пак. Сейчас добавляется 1 штука.", reply_markup=build_creator_pack_deposit_keyboard(packs))
    await callback.answer()


@router.callback_query(F.data.startswith("creator:add_pack_pick:"))
async def creator_add_pack_pick(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    raw = callback.data.split(":")[-1] if callback.data else ""
    ok, msg = await add_pack_to_bank(user_id, int(raw) if raw.isdigit() else 0, 1)
    panel = await get_panel(user_id)
    await edit_or_send(callback, f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_panel_keyboard(panel))
    await callback.answer()


@router.callback_query(F.data == "creator:add_card")
async def creator_add_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreatorDistributeStates.waiting_for_card_id)
    await edit_or_send(callback, "<b>🃏 Добавить карту</b>\n\nОтправь ID экземпляра карты из своей коллекции.", reply_markup=build_creator_cancel_keyboard())
    await callback.answer()


@router.message(CreatorDistributeStates.waiting_for_card_id)
async def creator_add_card_id(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи числовой ID экземпляра карты.", reply_markup=build_creator_cancel_keyboard())
        return
    await state.clear()
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    ok, msg = await add_card_to_bank(user_id, int(raw))
    panel = await get_panel(user_id)
    await message.answer(f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_panel_keyboard(panel))


@router.callback_query(F.data.in_({"creator:bank_give", "creator:give_coins", "creator:give_pack"}))
async def creator_bank_give(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None or not await is_creator(user_id):
        await callback.answer("Только для креаторов", show_alert=True)
        return
    panel = await get_panel(user_id)
    if not panel.bank_items:
        await callback.answer("Банк выдачи пуст", show_alert=True)
        return
    await edit_or_send(callback, "<b>🎁 Выдача из банка</b>\n\nВыбери награду:", reply_markup=build_creator_bank_items_keyboard(panel.bank_items, "creator:bank_give_pick"))
    await callback.answer()


@router.callback_query(F.data.startswith("creator:bank_give_pick:"))
async def creator_bank_give_pick(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.split(":")[-1] if callback.data else ""
    item_id = int(raw) if raw.isdigit() else 0
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    item = await get_bank_item(user_id, item_id) if user_id else None
    if item is None:
        await callback.answer("Награда не найдена", show_alert=True)
        return
    await state.set_state(CreatorDistributeStates.waiting_for_bank_target)
    await state.update_data(item_id=item_id)
    await edit_or_send(callback, f"Кому выдать: {item.title}?\n\nОтправь Telegram ID игрока.", reply_markup=build_creator_cancel_keyboard())
    await callback.answer()


@router.message(CreatorDistributeStates.waiting_for_bank_target)
async def creator_bank_target(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи числовой Telegram ID игрока.", reply_markup=build_creator_cancel_keyboard())
        return

    user_id = get_user_id_by_telegram_id(message.from_user.id)
    data = await state.get_data()
    item = await get_bank_item(user_id, int(data.get("item_id", 0)))
    if item is None:
        await state.clear()
        await message.answer("Награда не найдена.")
        return

    await state.update_data(target=int(raw))
    if item.item_type == "card" or item.quantity == 1:
        await state.clear()
        ok, msg, _ = await distribute_bank_item(user_id, int(raw), item.id, 1)
        if ok:
            try:
                await message.bot.send_message(chat_id=int(raw), text=f"🎁 Ты получил награду от официального креатора: {item.title}!")
            except Exception:
                pass
        panel = await get_panel(user_id)
        await message.answer(f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_panel_keyboard(panel))
        return

    await state.set_state(CreatorDistributeStates.waiting_for_bank_amount)
    await message.answer(f"Сколько выдать? Доступно: {format_int(item.quantity)}", reply_markup=build_creator_cancel_keyboard())


@router.message(CreatorDistributeStates.waiting_for_bank_amount)
async def creator_bank_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введи число больше 0.", reply_markup=build_creator_cancel_keyboard())
        return
    data = await state.get_data()
    await state.clear()
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    target = int(data.get("target", 0))
    item_id = int(data.get("item_id", 0))
    item = await get_bank_item(user_id, item_id)
    ok, msg, _ = await distribute_bank_item(user_id, target, item_id, int(raw))
    if ok and item:
        try:
            await message.bot.send_message(chat_id=target, text=f"🎁 Ты получил награду от официального креатора: {item.title} ×{int(raw)}!")
        except Exception:
            pass
    panel = await get_panel(user_id)
    await message.answer(f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_panel_keyboard(panel))


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

def _admin_ids() -> list[int]:
    from config import settings
    return list(settings.admin_ids)


async def admin_guard(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True
    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def show_admin_main_msg(message: Message) -> None:
    apps = await get_pending_applications()
    creators = await list_creators()
    await message.answer(ADMIN_CREATORS_MAIN_TEXT, reply_markup=build_admin_creators_main_keyboard(len(apps), len(creators)))


async def show_admin_main_cb(callback: CallbackQuery) -> None:
    apps = await get_pending_applications()
    creators = await list_creators()
    await edit_or_send(callback, ADMIN_CREATORS_MAIN_TEXT, reply_markup=build_admin_creators_main_keyboard(len(apps), len(creators)))


@router.message(F.text == ADMIN_CREATORS_BUTTON_TEXT)
async def admin_creators_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await state.clear()
    await safe_delete_message(message)
    await show_admin_main_msg(message)


@router.callback_query(F.data == "admin_creators:main")
async def admin_creators_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    await show_admin_main_cb(callback)
    await callback.answer()


@router.callback_query(F.data == "admin_creators:apps")
async def admin_creators_apps(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    apps = await get_pending_applications()
    text = "<b>📥 Заявки</b>\n\nНовых заявок нет." if not apps else "<b>📥 Заявки креаторов</b>\n\nВыбери заявку:"
    await edit_or_send(callback, text, reply_markup=build_admin_apps_keyboard(apps))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:app:"))
async def admin_creators_app(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    app = await get_application(int(raw) if raw.isdigit() else 0)
    if app is None:
        await admin_creators_apps(callback, state)
        return
    await edit_or_send(callback, build_admin_application_text(app), reply_markup=build_admin_app_view_keyboard(app.id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:approve:"))
async def admin_creators_approve(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    ok, msg, tg, chat_link = await resolve_application(int(raw) if raw.isdigit() else 0, True)
    if ok and tg:
        try:
            link_line = f"\n\nЗакрытый чат креаторов: {chat_link}" if chat_link else ""
            await callback.bot.send_message(
                chat_id=tg,
                text=f"🎉 Твоя заявка одобрена! Теперь ты официальный креатор 1 уровня. Открой «Программа креаторов» → «Моя панель».{link_line}",
            )
        except Exception:
            pass
    await show_admin_main_cb(callback)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data.startswith("admin_creators:reject:"))
async def admin_creators_reject(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    ok, msg, tg, _ = await resolve_application(int(raw) if raw.isdigit() else 0, False)
    if ok and tg:
        try:
            await callback.bot.send_message(chat_id=tg, text="К сожалению, твоя заявка в программу креаторов отклонена.")
        except Exception:
            pass
    await show_admin_main_cb(callback)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data == "admin_creators:list")
async def admin_creators_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    creators = await list_creators()
    await edit_or_send(callback, build_admin_creators_list_text(creators), reply_markup=build_admin_creators_list_keyboard(creators))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:creator:"))
async def admin_creators_creator(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    user_id = int(raw) if raw.isdigit() else 0
    creator = await get_creator_detail(user_id)
    if creator is None:
        await admin_creators_list(callback, state)
        return
    await edit_or_send(callback, build_admin_creator_detail_text(creator), reply_markup=build_admin_creator_manage_keyboard(user_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:set_level:"))
async def admin_creators_set_level(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    await state.set_state(AdminCreatorLevelStates.waiting_for_level)
    await state.update_data(user_id=int(raw) if raw.isdigit() else 0)
    await edit_or_send(callback, "🎖 Введи новый уровень креатора (1–5).", reply_markup=build_admin_creator_cancel_keyboard())
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_level)
async def admin_creators_level_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()
    if not raw.isdigit() or int(raw) < 1 or int(raw) > 5:
        await message.answer("Введи число 1–5.")
        return
    ok, msg = await set_creator_level(int(data.get("user_id", 0)), int(raw))
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    await show_admin_main_msg(message)


@router.callback_query(F.data.startswith("admin_creators:set_subs:"))
async def admin_creators_set_subs(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    await state.set_state(AdminCreatorLevelStates.waiting_for_subscribers)
    await state.update_data(user_id=int(raw) if raw.isdigit() else 0)
    await edit_or_send(callback, "👥 Введи новое количество подписчиков.", reply_markup=build_admin_creator_cancel_keyboard())
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_subscribers)
async def admin_creators_subs_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip().replace(" ", "")
    data = await state.get_data()
    await state.clear()
    if not raw.isdigit():
        await message.answer("Введи число.")
        return
    ok, msg = await set_creator_subscribers(int(data.get("user_id", 0)), int(raw))
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    await show_admin_main_msg(message)


@router.callback_query(F.data.startswith("admin_creators:set_author:"))
async def admin_creators_set_author(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    await state.set_state(AdminCreatorLevelStates.waiting_for_author_code)
    await state.update_data(user_id=int(raw) if raw.isdigit() else 0)
    await edit_or_send(callback, "✍️ Введи код автора. Отправь '-' чтобы убрать код.", reply_markup=build_admin_creator_cancel_keyboard())
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_author_code)
async def admin_creators_author_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    data = await state.get_data()
    await state.clear()
    ok, msg = await set_creator_author_code(int(data.get("user_id", 0)), message.text or "")
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    await show_admin_main_msg(message)


@router.callback_query(F.data.startswith("admin_creators:revoke:"))
async def admin_creators_revoke(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    ok, msg = await revoke_creator(int(raw) if raw.isdigit() else 0)
    await admin_creators_list(callback, state)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data == "admin_creators:weekly")
async def admin_creators_weekly(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    result = await pay_weekly_rewards()
    await show_admin_main_cb(callback)
    await callback.answer(
        f"Начислено {result.creators_count} креаторам: {format_int(result.total_coins)} монет, {result.total_packs} паков",
        show_alert=True,
    )


@router.callback_query(F.data == "admin_creators:settings")
async def admin_creators_settings(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    await state.clear()
    configs = await get_level_configs()
    await edit_or_send(callback, build_admin_levels_text(configs), reply_markup=build_admin_levels_keyboard(configs))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:level_settings:"))
async def admin_creators_level_settings(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    cfg = await get_level_config(int(raw) if raw.isdigit() else 0)
    if cfg is None:
        await callback.answer("Уровень не найден", show_alert=True)
        return
    await edit_or_send(callback, build_admin_level_config_text(cfg), reply_markup=build_admin_level_edit_keyboard(cfg.level))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:level_edit:"))
async def admin_creators_level_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    level = int(raw) if raw.isdigit() else 0
    await state.set_state(AdminCreatorLevelStates.waiting_for_level_config)
    await state.update_data(level=level)
    await edit_or_send(
        callback,
        "Отправь 11 чисел через |:\n"
        "<code>подписчики|разыграно|вступительные|недельные_монеты|elite_qty|legendary_qty|elite_pack_id|legendary_pack_id|промокоды|код_автора_bp|экскл_карта</code>",
        reply_markup=build_admin_settings_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_level_config)
async def admin_creators_level_config_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    data = await state.get_data()
    await state.clear()
    ok, msg = await update_level_config_from_text(int(data.get("level", 0)), message.text or "")
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    await show_admin_main_msg(message)


@router.callback_query(F.data.startswith("admin_creators:personal:"))
async def admin_creators_personal(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    level = int(raw) if raw.isdigit() else 0
    await state.set_state(AdminCreatorLevelStates.waiting_for_personal_rewards)
    await state.update_data(level=level)
    await edit_or_send(callback, "🏅 Отправь текст личных наград для этого уровня.", reply_markup=build_admin_settings_cancel_keyboard())
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_personal_rewards)
async def admin_creators_personal_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    data = await state.get_data()
    await state.clear()
    ok, msg = await update_level_personal_rewards(int(data.get("level", 0)), message.text or "")
    await message.answer(f"{'✅' if ok else '❌'} {msg}")
    await show_admin_main_msg(message)


@router.callback_query(F.data == "admin_creators:chat_link")
async def admin_creators_chat_link(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    current = await get_creator_chat_invite_link()
    await state.set_state(AdminCreatorLevelStates.waiting_for_chat_link)
    await edit_or_send(callback, f"🔗 Текущая ссылка на чат:\n{current or 'не задана'}\n\nОтправь новую ссылку или '-' чтобы очистить.", reply_markup=build_admin_settings_cancel_keyboard())
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_chat_link)
async def admin_creators_chat_link_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    await state.clear()
    value = (message.text or "").strip()
    if value == "-":
        value = ""
    await set_creator_chat_invite_link(value)
    await message.answer("✅ Ссылка на закрытый чат креаторов обновлена.")
    await show_admin_main_msg(message)
