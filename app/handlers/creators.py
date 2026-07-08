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
    build_creator_apply_cancel_keyboard,
    build_creator_cancel_keyboard,
    build_creator_intro_keyboard,
    build_creator_pack_pick_keyboard,
    build_creator_panel_keyboard,
)
from app.services.community import get_user_id_by_telegram_id
from app.services.creators import (
    distribute_coins,
    distribute_pack,
    get_application,
    get_distribution_history,
    get_panel,
    get_pending_applications,
    is_creator,
    list_creators,
    pay_weekly_rewards,
    resolve_application,
    revoke_creator,
    set_creator_level,
    submit_application,
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
    build_admin_creators_list_text,
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

    # уведомляем админов
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


@router.callback_query(F.data == "creator:give_coins")
async def creator_give_coins(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None or not await is_creator(user_id):
        await callback.answer("Только для креаторов", show_alert=True)
        return
    await state.set_state(CreatorDistributeStates.waiting_for_coins_target)
    await edit_or_send(callback, "<b>🪙 Выдача Coins</b>\n\nОтправь ID игрока (его Telegram ID).", reply_markup=build_creator_cancel_keyboard())
    await callback.answer()


@router.message(CreatorDistributeStates.waiting_for_coins_target)
async def creator_coins_target(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи числовой ID игрока.", reply_markup=build_creator_cancel_keyboard())
        return
    await state.update_data(target=int(raw))
    await state.set_state(CreatorDistributeStates.waiting_for_coins_amount)
    await message.answer("Сколько Coins выдать? (число)", reply_markup=build_creator_cancel_keyboard())


@router.message(CreatorDistributeStates.waiting_for_coins_amount)
async def creator_coins_amount(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи число.", reply_markup=build_creator_cancel_keyboard())
        return
    data = await state.get_data()
    await state.clear()
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    target = int(data.get("target", 0))
    ok, msg = await distribute_coins(user_id, target, int(raw))

    if ok:
        try:
            await message.bot.send_message(chat_id=target, text=f"🎁 Ты получил награду от официального креатора: 🪙 {int(raw)} Coins!")
        except Exception:
            pass

    panel = await get_panel(user_id)
    await message.answer(f"{'✅' if ok else '❌'} {msg}", reply_markup=build_creator_panel_keyboard(panel))


@router.callback_query(F.data == "creator:give_pack")
async def creator_give_pack(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None or not await is_creator(user_id):
        await callback.answer("Только для креаторов", show_alert=True)
        return
    panel = await get_panel(user_id)
    if not panel.packs:
        await callback.answer("В панели нет паков", show_alert=True)
        return
    await edit_or_send(callback, "<b>🎁 Выдача пака</b>\n\nВыбери пак для выдачи:", reply_markup=build_creator_pack_pick_keyboard(panel.packs))
    await callback.answer()


@router.callback_query(F.data.startswith("creator:pack_pick:"))
async def creator_pack_pick(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.split(":")[-1] if callback.data else ""
    pack_id = int(raw) if raw.isdigit() else 0
    await state.update_data(pack_id=pack_id)
    await state.set_state(CreatorDistributeStates.waiting_for_pack_target)
    await edit_or_send(callback, "Отправь ID игрока, которому выдать пак.", reply_markup=build_creator_cancel_keyboard())
    await callback.answer()


@router.message(CreatorDistributeStates.waiting_for_pack_target)
async def creator_pack_target(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введи числовой ID игрока.", reply_markup=build_creator_cancel_keyboard())
        return
    data = await state.get_data()
    await state.clear()
    user_id = get_user_id_by_telegram_id(message.from_user.id)
    target = int(raw)
    pack_id = int(data.get("pack_id", 0))
    ok, msg = await distribute_pack(user_id, target, pack_id)

    if ok:
        try:
            await message.bot.send_message(chat_id=target, text="🎁 Ты получил пак от официального креатора! Загляни в «Мои паки».")
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
    if not apps:
        await edit_or_send(callback, "<b>📥 Заявки</b>\n\nНовых заявок нет.", reply_markup=build_admin_apps_keyboard([]))
    else:
        await edit_or_send(callback, "<b>📥 Заявки креаторов</b>\n\nВыбери заявку:", reply_markup=build_admin_apps_keyboard(apps))
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
    ok, msg, tg = await resolve_application(int(raw) if raw.isdigit() else 0, True)
    if ok and tg:
        try:
            await callback.bot.send_message(chat_id=tg, text="🎉 Твоя заявка одобрена! Теперь ты официальный креатор. Открой «Программа креаторов» → «Моя панель».")
        except Exception:
            pass
    await show_admin_main_cb(callback)
    await callback.answer(msg, show_alert=not ok)


@router.callback_query(F.data.startswith("admin_creators:reject:"))
async def admin_creators_reject(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    ok, msg, tg = await resolve_application(int(raw) if raw.isdigit() else 0, False)
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
    creators = await list_creators()
    creator = next((c for c in creators if c["id"] == user_id), None)
    if creator is None:
        await admin_creators_list(callback, state)
        return
    text = f"<b>⭐ {creator['nickname']}</b>\n\nУровень: <b>{creator['creator_level']}</b>\nID: <b>{creator['telegram_id']}</b>\nКанал: {creator['creator_channel'] or '—'}"
    await edit_or_send(callback, text, reply_markup=build_admin_creator_manage_keyboard(user_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_creators:set_level:"))
async def admin_creators_set_level(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_guard(callback):
        return
    raw = callback.data.split(":")[-1] if callback.data else ""
    await state.set_state(AdminCreatorLevelStates.waiting_for_level)
    await state.update_data(user_id=int(raw) if raw.isdigit() else 0)
    await edit_or_send(callback, "🎖 Введи новый уровень креатора (0–5, 0 — снять статус).", reply_markup=build_admin_creator_cancel_keyboard())
    await callback.answer()


@router.message(AdminCreatorLevelStates.waiting_for_level)
async def admin_creators_level_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)
    raw = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()
    if not raw.isdigit() or int(raw) > 5:
        await message.answer("Введи число 0–5.")
        return
    ok, msg = await set_creator_level(int(data.get("user_id", 0)), int(raw))
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
    count, coins, packs = await pay_weekly_rewards()
    await show_admin_main_cb(callback)
    await callback.answer(f"Начислено {count} креаторам: {coins} Coins, {packs} паков", show_alert=True)
