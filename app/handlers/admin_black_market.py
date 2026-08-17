"""Административные экраны BLACK MARKET внутри Telegram admin-панели.

Доступ контролируется `PERMISSION_BLACK_MARKET` (см. app/services/admin_permissions.py),
проверяется в каждом хендлере (конвенция проекта, см. app/handlers/admin_stronghold.py —
разрешение проверяется per-handler, а не только через router middleware).

"Добавить предмет" — единый мастер (FSM) для всех 5 типов пула (CARD/FRAME/BACKGROUND/
PACK/CURRENCY, раздел 8 ТЗ аудита). Загрузка изображений для FRAME/BACKGROUND напрямую
переиспользует app.handlers.admin_war2._save_cosmetic_image и war2_cosmetics.
create_cosmetic_item — тот же каталог/хранилище, что и у CLAN WAR 2.0, никакого
второго движка косметики не заводится (раздел 3 ТЗ аудита).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.keyboards import black_market as keyboards
from app.services import black_market_admin
from app.services.admin_permissions import PERMISSION_BLACK_MARKET, has_admin_permission
from app.services.black_market_common import RARITIES, BlackMarketError
from app.services.black_market_items import get_preview_render_args
from app.services.renders import render_black_market_item_preview
from app.services.war2_cosmetics import War2Error, create_cosmetic_item
from app.texts import black_market as texts
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()

ADMIN_BLACK_MARKET_BUTTON_TEXT = "🕶 Чёрный рынок"

# Соответствие пользовательских типов из мастера "Добавить предмет" -> (item_type, cosmetic_type).
_ADD_ITEM_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "card": ("card", None),
    "frame": ("cosmetic", "CARD_FRAME"),
    "background": ("cosmetic", "PROFILE_BACKGROUND"),
    "prefix": ("cosmetic", "NICK_BADGE"),
    "pack": ("pack", None),
    "currency": ("currency", None),
}


class BlackMarketAdminStates(StatesGroup):
    find_user_query = State()
    edit_weights = State()

    add_item_card_id = State()
    add_item_currency_amount = State()
    add_item_cosmetic_new_title = State()
    add_item_cosmetic_badge_text = State()
    add_item_cosmetic_new_image = State()
    add_item_title = State()
    add_item_description = State()
    add_item_price_fixed_amount = State()
    add_item_price_min = State()
    add_item_price_max = State()
    add_item_stock = State()
    add_item_purchase_limit = State()
    add_item_selection_weight = State()
    add_item_available_from = State()
    add_item_available_until = State()


def _require_permission(user_id: int | None) -> bool:
    return is_admin(user_id) and has_admin_permission(user_id, PERMISSION_BLACK_MARKET)


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


async def _draft(state: FSMContext) -> dict:
    data = await state.get_data()
    return dict(data.get("bm_draft", {}))


async def _update_draft(state: FSMContext, **fields: object) -> dict:
    draft = await _draft(state)
    draft.update(fields)
    await state.update_data(bm_draft=draft)
    return draft


async def build_dashboard_text() -> str:
    weights = await black_market_admin.get_rarity_weights()
    settings_row = await black_market_admin.get_shop_settings()
    status = "🟢 включён" if bool(settings_row["shop_enabled"]) else "🔴 выключен"
    lines = ["🕶 <b>Чёрный рынок — Админ-панель</b>", "", f"Статус магазина: {status}", "", "Веса редкости:"]
    for rarity in RARITIES:
        lines.append(f"  {rarity}: {weights.get(rarity, 0)}")
    return "\n".join(lines)


async def show_admin_dashboard_message(message: Message) -> None:
    text = await build_dashboard_text()
    await message.answer(text, reply_markup=keyboards.build_admin_dashboard_keyboard())


@router.message(F.text == ADMIN_BLACK_MARKET_BUTTON_TEXT)
async def admin_black_market_button(message: Message) -> None:
    await safe_delete_message(message)
    if message.from_user is None or not _require_permission(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await show_admin_dashboard_message(message)


@router.callback_query(F.data == "bm_admin:main")
async def admin_dashboard_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    text = await build_dashboard_text()
    await edit_or_send(callback, text, keyboards.build_admin_dashboard_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# Настройки магазина (вкл/выкл + slots_count/stock_mode/allow_duplicate_slots)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:settings")
async def admin_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    settings_row = await black_market_admin.get_shop_settings()
    lines = [
        "⚙️ <b>Настройки ротации Чёрного рынка</b>",
        "",
        f"Слотов в витрине: {settings_row['slots_count']}",
        f"Режим стока: {settings_row['stock_mode']}",
        f"Повторы в витрине разрешены глобально: {'да' if settings_row['allow_duplicate_slots'] else 'нет'}",
        f"Текущая версия ротации: {settings_row['global_rotation_version']}",
        "",
        "Чтобы изменить slots_count/stock_mode/allow_duplicate_slots, обратитесь к",
        "разработчику или используйте /diagnostics — быстрый чат-редактор для этих",
        "полей не заведён намеренно (они меняются редко и ошибка в них дороже,",
        "чем в весах редкости).",
    ]
    await edit_or_send(callback, "\n".join(lines), keyboards.build_admin_settings_keyboard(bool(settings_row["shop_enabled"])))
    await callback.answer()


@router.callback_query(F.data == "bm_admin:toggle_shop")
async def admin_toggle_shop_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    settings_row = await black_market_admin.get_shop_settings()
    new_enabled = not bool(settings_row["shop_enabled"])
    await black_market_admin.set_shop_enabled(callback.from_user.id, new_enabled)
    await callback.answer("Магазин включён." if new_enabled else "Магазин выключен.", show_alert=True)
    settings_row = await black_market_admin.get_shop_settings()
    lines = [
        "⚙️ <b>Настройки ротации Чёрного рынка</b>",
        "",
        f"Слотов в витрине: {settings_row['slots_count']}",
        f"Режим стока: {settings_row['stock_mode']}",
        f"Повторы в витрине разрешены глобально: {'да' if settings_row['allow_duplicate_slots'] else 'нет'}",
    ]
    await edit_or_send(callback, "\n".join(lines), keyboards.build_admin_settings_keyboard(bool(settings_row["shop_enabled"])))


# ---------------------------------------------------------------------------
# Поиск игрока и просмотр/правка его витрины
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:find_user")
async def admin_find_user_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(BlackMarketAdminStates.find_user_query)
    await edit_or_send(
        callback,
        "Введите Telegram ID, никнейм или username игрока:",
        InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row("bm_admin:main")]),
    )
    await callback.answer()


@router.message(BlackMarketAdminStates.find_user_query)
async def admin_find_user_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return

    query = (message.text or "").strip()
    user_row = await black_market_admin.find_user(query)
    if user_row is None:
        await message.answer(texts.error_text("USER_NOT_FOUND", "Игрок не найден."))
        return

    await state.clear()
    target_user_id = int(user_row["id"])
    text, keyboard = await _render_user_panel(target_user_id)
    await message.answer(text, reply_markup=keyboard)


async def _render_user_panel(target_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    with get_connection() as connection:
        user_row = connection.execute(
            "SELECT nickname, telegram_id FROM users WHERE id = ?", (target_user_id,)
        ).fetchone()

    header = f"#{target_user_id}"
    if user_row is not None:
        header = f"{user_row['nickname']} (tg:{user_row['telegram_id']}, id:{target_user_id})"

    lines = [f"👤 <b>Витрина игрока — {header}</b>", ""]

    rotation = await black_market_admin.view_user_storefront(target_user_id)
    if rotation is None:
        lines.append("Ротация на сегодня ещё не сгенерирована — появится при первом открытии игроком.")
    else:
        lines.append(f"business_date: {rotation.business_date} · версия ротации: {rotation.rotation_version}")
        lines.append("")
        for item in rotation.items:
            icon = texts.RARITY_ICONS.get(item.rarity, "")
            status_label = texts.ITEM_STATUS_LABELS.get(item.item_status, item.item_status)
            lines.append(
                f"{icon} #{item.id} {item.name} — {item.price_amount} {item.price_currency_code} "
                f"({item.remaining_personal_stock}/{item.initial_personal_stock}) [{status_label}]"
            )

    return "\n".join(lines), keyboards.build_admin_user_panel_keyboard(target_user_id)


@router.callback_query(F.data.regexp(r"^bm_admin:user:\d+$"))
async def admin_user_panel_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        target_user_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Игрок не найден.", show_alert=True)
        return
    text, keyboard = await _render_user_panel(target_user_id)
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^bm_admin:user:\d+:refresh$"))
async def admin_user_refresh_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        target_user_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    await black_market_admin.refresh_one_user(callback.from_user.id, target_user_id)
    await callback.answer("Рынок игрока обновлён — новая витрина появится при следующем открытии.", show_alert=True)

    with get_connection() as connection:
        telegram_row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (target_user_id,)).fetchone()
    if telegram_row is not None:
        import asyncio

        from app.services.black_market_notifications import notify_single_user

        asyncio.create_task(notify_single_user(callback.bot, int(telegram_row["telegram_id"])))

    text, keyboard = await _render_user_panel(target_user_id)
    await edit_or_send(callback, text, keyboard)


@router.callback_query(F.data.regexp(r"^bm_admin:user:\d+:rotations$"))
async def admin_user_rotations_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        target_user_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    history = await black_market_admin.list_user_rotation_history(target_user_id, limit=10)
    lines = ["📜 <b>История ротаций игрока</b>", ""]
    if not history:
        lines.append("Пока пусто.")
    for row in history:
        lines.append(
            f"#{row['id']} {row['business_date']} v{row['rotation_version']} — {row['status']} "
            f"({row['items_count']} товаров, причина: {row['generation_reason']})"
        )
    await edit_or_send(
        callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row(f"bm_admin:user:{target_user_id}")])
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^bm_admin:user:\d+:purchases$"))
async def admin_user_purchases_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        target_user_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    history = await black_market_admin.list_user_purchase_history(target_user_id, limit=20)
    lines = ["🧾 <b>История покупок игрока</b>", ""]
    if not history:
        lines.append("Пока пусто.")
    for row in history:
        lines.append(f"#{row['id']} {row['item_name'] or '—'} — {row['price_amount']} {row['price_currency_code']} ({row['created_at']})")
    await edit_or_send(
        callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row(f"bm_admin:user:{target_user_id}")])
    )
    await callback.answer()


@router.callback_query(F.data == "bm_admin:purchases")
async def admin_recent_purchases_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rows = await black_market_admin.list_recent_purchases(limit=20)
    lines = ["🧾 <b>Последние покупки (все игроки)</b>", ""]
    if not rows:
        lines.append("Пока пусто.")
    for row in rows:
        lines.append(f"#{row['id']} {row['buyer_nickname'] or '—'}: {row['item_name'] or '—'} — {row['price_amount']} {row['price_currency_code']}")
    await edit_or_send(
        callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row("bm_admin:main")])
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Пул предметов (список + toggle active)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:pool")
async def admin_pool_list_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    items = await black_market_admin.list_pool_items()
    lines = ["📦 <b>Пул предметов</b>", ""]
    if not items:
        lines.append("Пул пуст.")
    await edit_or_send(callback, "\n".join(lines), keyboards.build_admin_pool_keyboard(items))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_admin:pool:toggle:"))
async def admin_pool_toggle_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    try:
        pool_item_id = int((callback.data or "").split(":")[3])
    except (IndexError, ValueError):
        await callback.answer("Предмет не найден.", show_alert=True)
        return

    items_before = await black_market_admin.list_pool_items()
    current = next((item for item in items_before if item.id == pool_item_id), None)
    if current is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return

    try:
        await black_market_admin.set_pool_item_active(callback.from_user.id, pool_item_id, not current.active)
    except BlackMarketError as error:
        await callback.answer(texts.error_text(error.code, error.message), show_alert=True)
        return

    items = await black_market_admin.list_pool_items()
    await edit_or_send(callback, "📦 <b>Пул предметов</b>", keyboards.build_admin_pool_keyboard(items))
    await callback.answer("Обновлено.")


# ---------------------------------------------------------------------------
# Веса редкости
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:weights")
async def admin_weights_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    weights = await black_market_admin.get_rarity_weights()
    lines = ["🎲 <b>Веса редкости</b>", ""]
    for rarity in RARITIES:
        lines.append(f"{rarity}: {weights.get(rarity, 0)}")
    lines.append("")
    lines.append("Сумма активных (>0) весов должна быть строго 100. Чтобы изменить,")
    lines.append("отправьте сообщение в формате:")
    lines.append("Common:50,Rare:25,Epic:15,Legendary:7,Event:2,Icon:1")

    await state.set_state(BlackMarketAdminStates.edit_weights)
    await edit_or_send(
        callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row("bm_admin:main")])
    )
    await callback.answer()


@router.message(BlackMarketAdminStates.edit_weights)
async def admin_weights_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return

    raw = (message.text or "").strip()
    weights: dict[str, int] = {}
    try:
        for pair in raw.split(","):
            rarity, _, value = pair.strip().partition(":")
            weights[rarity.strip()] = int(value.strip())
    except ValueError:
        await message.answer("Некорректный формат. Пример: Common:50,Rare:25")
        return

    try:
        await black_market_admin.update_rarity_weights(message.from_user.id, weights)
    except BlackMarketError as error:
        await message.answer(texts.error_text(error.code, error.message))
        return

    await state.clear()
    await message.answer("Веса редкости обновлены.")
    await show_admin_dashboard_message(message)


# ---------------------------------------------------------------------------
# Обновить рынок всем
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:refresh_all")
async def admin_refresh_all_prompt(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    text = (
        "⚠️ Это увеличит глобальную версию ротации. Каждый игрок получит новую "
        "персональную витрину при следующем открытии Чёрного рынка (не сразу и не "
        "всем одновременно). Подтвердить?"
    )
    await edit_or_send(callback, text, keyboards.build_admin_refresh_all_confirm_keyboard())
    await callback.answer()


@router.callback_query(F.data == "bm_admin:refresh_all:confirm")
async def admin_refresh_all_confirm(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    new_version = await black_market_admin.refresh_everyone(callback.from_user.id)
    await callback.answer(f"Готово. Новая версия ротации: {new_version}.", show_alert=True)

    import asyncio

    from app.services.black_market_notifications import notify_settings_driven

    asyncio.create_task(notify_settings_driven(callback.bot))

    text = await build_dashboard_text()
    await edit_or_send(callback, text, keyboards.build_admin_dashboard_keyboard())


# ---------------------------------------------------------------------------
# Аудит
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:audit")
async def admin_audit_callback(callback: CallbackQuery) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    entries = await black_market_admin.list_recent_audit(15)
    lines = ["📜 <b>Аудит Чёрного рынка</b>", ""]
    if not entries:
        lines.append("Пока пусто.")
    for entry in entries:
        lines.append(f"#{entry['id']} {entry['action']} — {entry['entity']} (admin {entry['admin_id']}) {entry['created_at']}")

    await edit_or_send(
        callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row("bm_admin:main")])
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# "Добавить предмет" — мастер CARD/FRAME/BACKGROUND/PACK/CURRENCY
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bm_admin:add_item:start")
async def admin_add_item_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await state.update_data(bm_draft={})
    await edit_or_send(callback, "➕ <b>Добавить предмет</b>\n\nВыберите тип товара:", keyboards.build_add_item_type_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("bm_admin:add_item:type:"))
async def admin_add_item_type_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    choice = (callback.data or "").split(":")[3]
    mapping = _ADD_ITEM_TYPE_MAP.get(choice)
    if mapping is None:
        await callback.answer("Неизвестный тип.", show_alert=True)
        return
    item_type, cosmetic_type = mapping
    await _update_draft(state, item_type=item_type, cosmetic_type=cosmetic_type)

    if item_type == "card":
        await state.set_state(BlackMarketAdminStates.add_item_card_id)
        await edit_or_send(callback, "Введите ID существующей карты:", InlineKeyboardMarkup(inline_keyboard=[keyboards.back_row("bm_admin:add_item:start")]))
    elif item_type == "cosmetic":
        await edit_or_send(callback, f"Тип косметики: {cosmetic_type}.\n\nВыберите источник:", keyboards.build_cosmetic_source_keyboard())
    elif item_type == "pack":
        packs = await black_market_admin.list_pack_choices()
        rows = [(f"{pack['name']} (#{pack['id']})", f"bm_admin:add_item:pack:{pack['id']}") for pack in packs]
        await edit_or_send(callback, "Выберите пак:", keyboards.build_choice_keyboard(rows, "bm_admin:add_item:start"))
    elif item_type == "currency":
        currencies = await black_market_admin.list_currency_choices()
        rows = [(f"{currency['icon']} {currency['name']} ({currency['code']})", f"bm_admin:add_item:currency:{currency['code']}") for currency in currencies]
        await edit_or_send(callback, "Выберите валюту награды:", keyboards.build_choice_keyboard(rows, "bm_admin:add_item:start"))
    await callback.answer()


@router.message(BlackMarketAdminStates.add_item_card_id)
async def admin_add_item_card_id_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите числовой ID карты.")
        return
    card_row = await black_market_admin.get_card_choice(int(raw))
    if card_row is None:
        await message.answer("Карта не найдена или неактивна. Введите другой ID.")
        return

    await _update_draft(state, card_id=int(raw), title=card_row["name"])
    preview_path = render_black_market_item_preview(
        cache_key=f"admin_preview_card_{raw}", item_type="card", image_path=card_row["image_path"], rarity=card_row["rarity"]
    )
    await message.answer_photo(FSInputFile(preview_path), caption=f"Карта: {card_row['name']} ({card_row['position']}, OVR {card_row['overall']})")
    await _ask_rarity(message, state)


@router.callback_query(F.data.startswith("bm_admin:add_item:pack:"))
async def admin_add_item_pack_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    pack_id = int((callback.data or "").split(":")[3])
    with get_connection() as connection:
        pack_row = connection.execute("SELECT id, name, image_path FROM packs WHERE id = ?", (pack_id,)).fetchone()
    if pack_row is None:
        await callback.answer("Пак не найден.", show_alert=True)
        return
    await _update_draft(state, pack_id=pack_id, title=pack_row["name"])
    await callback.answer()
    await _ask_rarity(callback.message, state)


@router.callback_query(F.data.startswith("bm_admin:add_item:currency:"))
async def admin_add_item_currency_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    code = (callback.data or "").split(":")[3]
    await _update_draft(state, currency_code=code, title="")
    await state.set_state(BlackMarketAdminStates.add_item_currency_amount)
    await edit_or_send(callback, "Сколько валюты выдавать за покупку? Введите число:")
    await callback.answer()


@router.message(BlackMarketAdminStates.add_item_currency_amount)
async def admin_add_item_currency_amount_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    await _update_draft(state, amount=int(raw))
    await _ask_rarity(message, state)


@router.callback_query(F.data == "bm_admin:add_item:cosmetic_existing")
async def admin_add_item_cosmetic_existing(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    draft = await _draft(state)
    cosmetic_type = draft.get("cosmetic_type", "FRAME")
    items = await black_market_admin.list_cosmetic_choices(cosmetic_type)
    rows = [(f"{item['title']} ({item['rarity']})", f"bm_admin:add_item:cosmetic_pick:{item['id']}") for item in items]
    if not rows:
        await callback.answer("Нет существующих предметов этого типа — загрузите новый.", show_alert=True)
        return
    await edit_or_send(callback, "Выберите существующий предмет:", keyboards.build_choice_keyboard(rows, "bm_admin:add_item:start"))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_admin:add_item:cosmetic_pick:"))
async def admin_add_item_cosmetic_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    cosmetic_item_id = int((callback.data or "").split(":")[3])
    with get_connection() as connection:
        cosmetic_row = connection.execute(
            "SELECT id, title, rarity, image_path, type FROM war2_cosmetic_items WHERE id = ?", (cosmetic_item_id,)
        ).fetchone()
    if cosmetic_row is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return
    await _update_draft(state, cosmetic_item_id=cosmetic_item_id, title=cosmetic_row["title"])
    preview_path = render_black_market_item_preview(
        cache_key=f"admin_preview_cosmetic_{cosmetic_item_id}",
        item_type="cosmetic",
        image_path=cosmetic_row["image_path"],
        rarity=cosmetic_row["rarity"],
        cosmetic_type=cosmetic_row["type"],
    )
    if isinstance(callback.message, Message):
        await callback.bot.send_photo(callback.message.chat.id, FSInputFile(preview_path), caption=f"Предмет: {cosmetic_row['title']}")
    await callback.answer()
    await _ask_rarity(callback.message, state)


@router.callback_query(F.data == "bm_admin:add_item:cosmetic_new")
async def admin_add_item_cosmetic_new(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(BlackMarketAdminStates.add_item_cosmetic_new_title)
    await edit_or_send(callback, "Введите название нового предмета:")
    await callback.answer()


@router.message(BlackMarketAdminStates.add_item_cosmetic_new_title)
async def admin_add_item_cosmetic_new_title_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await _update_draft(state, title=title, cosmetic_new_title=title)
    await message.answer("Выберите редкость нового предмета:", reply_markup=keyboards.build_rarity_choice_keyboard("bm_admin:add_item:cosmetic_new_rarity"))


@router.callback_query(F.data.startswith("bm_admin:add_item:cosmetic_new_rarity:"))
async def admin_add_item_cosmetic_new_rarity(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rarity = (callback.data or "").split(":")[3]
    await _update_draft(state, rarity=rarity, cosmetic_new_rarity=rarity)
    draft = await _draft(state)
    if draft.get("cosmetic_type") == "NICK_BADGE":
        await state.set_state(BlackMarketAdminStates.add_item_cosmetic_badge_text)
        await edit_or_send(callback, "Введите платную приписку, которая будет отображаться после ника игрока. Например: MVP или CHAMP.")
    else:
        await state.set_state(BlackMarketAdminStates.add_item_cosmetic_new_image)
        await edit_or_send(callback, "Пришлите PNG/JPG/WEBP изображение предмета (фото или документ):")
    await callback.answer()


@router.message(BlackMarketAdminStates.add_item_cosmetic_badge_text)
async def admin_add_item_cosmetic_badge_text_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    badge_text = (message.text or "").strip()
    if not badge_text or len(badge_text) > 24:
        await message.answer("Приписка должна содержать от 1 до 24 символов.")
        return
    draft = await _draft(state)
    code = f"bm_nick_badge_{message.from_user.id}_{int(message.date.timestamp())}"
    try:
        cosmetic_item_id = await create_cosmetic_item(
            type="NICK_BADGE", code=code,
            title=draft.get("cosmetic_new_title", draft.get("title", badge_text)),
            rarity=draft.get("cosmetic_new_rarity", "Common"), badge_text=badge_text,
        )
    except War2Error as error:
        await message.answer(error.message)
        return
    await _update_draft(state, cosmetic_item_id=cosmetic_item_id)
    await message.answer("Приписка создана и добавлена в общий каталог косметики.")
    await _ask_price_currency(message, state)


@router.message(BlackMarketAdminStates.add_item_cosmetic_new_image)
async def admin_add_item_cosmetic_new_image_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return

    from app.handlers.admin_war2 import BACKGROUND_IMAGES_DIR, FRAME_IMAGES_DIR, _save_cosmetic_image

    draft = await _draft(state)
    cosmetic_type = draft.get("cosmetic_type", "FRAME")
    directory = FRAME_IMAGES_DIR if cosmetic_type in ("FRAME", "CARD_FRAME") else BACKGROUND_IMAGES_DIR
    image_path = await _save_cosmetic_image(message, directory)
    if image_path is None:
        await message.answer(texts.error_text("IMAGE_UPLOAD_FAILED", "Не удалось загрузить изображение."))
        return

    code = f"bm_{cosmetic_type.lower()}_{message.from_user.id}_{int(message.date.timestamp())}"
    try:
        cosmetic_item_id = await create_cosmetic_item(
            type=cosmetic_type, code=code, title=draft.get("cosmetic_new_title", draft.get("title", "")), rarity=draft.get("cosmetic_new_rarity", "Common"), image_path=image_path,
        )
    except War2Error as error:
        await message.answer(error.message)
        return

    await _update_draft(state, cosmetic_item_id=cosmetic_item_id)
    await message.answer("Предмет косметики создан и добавлен в каталог.")
    await _ask_price_currency(message, state)


async def _ask_rarity(message: Message, state: FSMContext) -> None:
    await message.answer("Выберите редкость товара в Чёрном рынке:", reply_markup=keyboards.build_rarity_choice_keyboard("bm_admin:add_item:rarity"))


@router.callback_query(F.data.startswith("bm_admin:add_item:rarity:"))
async def admin_add_item_rarity_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rarity = (callback.data or "").split(":")[3]
    await _update_draft(state, rarity=rarity)
    await callback.answer()
    await _ask_price_currency(callback.message, state)


async def _ask_price_currency(message: Message, state: FSMContext) -> None:
    currencies = await black_market_admin.list_currency_choices()
    rows = [(f"{currency['icon']} {currency['name']} ({currency['code']})", f"bm_admin:add_item:price_currency:{currency['code']}") for currency in currencies]
    await message.answer("Какой валютой игрок будет платить за товар?", reply_markup=keyboards.build_choice_keyboard(rows, "bm_admin:main"))


@router.callback_query(F.data.startswith("bm_admin:add_item:price_currency:"))
async def admin_add_item_price_currency_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    code = (callback.data or "").split(":")[3]
    await _update_draft(state, price_currency_code=code)
    await edit_or_send(callback, "Режим цены:", keyboards.build_price_mode_keyboard())
    await callback.answer()


@router.callback_query(F.data == "bm_admin:add_item:price_mode:FIXED")
async def admin_add_item_price_mode_fixed(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await _update_draft(state, price_mode="FIXED")
    await state.set_state(BlackMarketAdminStates.add_item_price_fixed_amount)
    await edit_or_send(callback, "Введите цену (целое число ≥ 0):")
    await callback.answer()


@router.message(BlackMarketAdminStates.add_item_price_fixed_amount)
async def admin_add_item_price_fixed_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите неотрицательное целое число.")
        return
    await _update_draft(state, price_amount=int(raw))
    await _ask_stock(message, state)


@router.callback_query(F.data == "bm_admin:add_item:price_mode:RANDOM_RANGE")
async def admin_add_item_price_mode_range(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await _update_draft(state, price_mode="RANDOM_RANGE")
    await state.set_state(BlackMarketAdminStates.add_item_price_min)
    await edit_or_send(callback, "Введите минимальную цену:")
    await callback.answer()


@router.message(BlackMarketAdminStates.add_item_price_min)
async def admin_add_item_price_min_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите неотрицательное целое число.")
        return
    await _update_draft(state, price_min_amount=int(raw))
    await state.set_state(BlackMarketAdminStates.add_item_price_max)
    await message.answer("Введите максимальную цену:")


@router.message(BlackMarketAdminStates.add_item_price_max)
async def admin_add_item_price_max_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите неотрицательное целое число.")
        return
    draft = await _draft(state)
    if int(raw) < int(draft.get("price_min_amount", 0)):
        await message.answer("max должен быть ≥ min. Введите ещё раз:")
        return
    await _update_draft(state, price_max_amount=int(raw))
    await _ask_stock(message, state)


async def _ask_stock(message: Message, state: FSMContext) -> None:
    await state.set_state(BlackMarketAdminStates.add_item_stock)
    await message.answer("Личный сток на игрока — введите число (например 3) или диапазон min-max (например 2-5):")


@router.message(BlackMarketAdminStates.add_item_stock)
async def admin_add_item_stock_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if "-" in raw:
        low_text, _, high_text = raw.partition("-")
        if not (low_text.strip().isdigit() and high_text.strip().isdigit()):
            await message.answer("Некорректный диапазон. Пример: 2-5")
            return
        low, high = int(low_text.strip()), int(high_text.strip())
        if low <= 0 or high < low:
            await message.answer("min должен быть > 0 и <= max. Пример: 2-5")
            return
        await _update_draft(state, stock_min=low, stock_max=high, max_stock_per_rotation=high)
    else:
        if not raw.isdigit() or int(raw) <= 0:
            await message.answer("Введите положительное целое число или диапазон вида 2-5.")
            return
        await _update_draft(state, max_stock_per_rotation=int(raw))

    await state.set_state(BlackMarketAdminStates.add_item_purchase_limit)
    await message.answer("Личный лимит покупок на игрока (0 = по умолчанию, равен стоку):")


@router.message(BlackMarketAdminStates.add_item_purchase_limit)
async def admin_add_item_purchase_limit_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите неотрицательное целое число (0 = без явного лимита).")
        return
    await _update_draft(state, personal_purchase_limit=int(raw))
    await state.set_state(BlackMarketAdminStates.add_item_selection_weight)
    await message.answer("Вес выбора внутри редкости (обычно 1, чем больше — тем чаще выпадает):")


@router.message(BlackMarketAdminStates.add_item_selection_weight)
async def admin_add_item_selection_weight_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    await _update_draft(state, selection_weight=int(raw))
    await message.answer("Разрешить этому товару повторяться в одной и той же витрине игрока?", reply_markup=keyboards.build_yes_no_keyboard("bm_admin:add_item:repeat:yes", "bm_admin:add_item:repeat:no"))


@router.callback_query(F.data.startswith("bm_admin:add_item:repeat:"))
async def admin_add_item_repeat_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    answer = (callback.data or "").split(":")[3]
    await _update_draft(state, allow_repeat_in_rotation=(answer == "yes"))
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "Ограничить доступность товара датами (available_from/available_until)?",
            reply_markup=keyboards.build_yes_no_keyboard("bm_admin:add_item:dates:yes", "bm_admin:add_item:dates:no"),
        )


@router.callback_query(F.data == "bm_admin:add_item:dates:no")
async def admin_add_item_dates_no(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await _show_add_item_summary(callback.message, state)


@router.callback_query(F.data == "bm_admin:add_item:dates:yes")
async def admin_add_item_dates_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(BlackMarketAdminStates.add_item_available_from)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Доступен С какого момента? Формат ГГГГ-ММ-ДД ЧЧ:ММ:СС, или \"-\" чтобы пропустить:")


@router.message(BlackMarketAdminStates.add_item_available_from)
async def admin_add_item_available_from_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    await _update_draft(state, available_from=None if raw == "-" else raw)
    await state.set_state(BlackMarketAdminStates.add_item_available_until)
    await message.answer("Доступен ДО какого момента? Формат ГГГГ-ММ-ДД ЧЧ:ММ:СС, или \"-\" чтобы пропустить:")


@router.message(BlackMarketAdminStates.add_item_available_until)
async def admin_add_item_available_until_input(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not _require_permission(message.from_user.id):
        return
    raw = (message.text or "").strip()
    await _update_draft(state, available_until=None if raw == "-" else raw)
    await _show_add_item_summary(message, state)


async def _show_add_item_summary(message: Message, state: FSMContext) -> None:
    draft = await _draft(state)
    lines = [
        "📋 <b>Проверьте товар перед созданием:</b>",
        "",
        f"Тип: {draft.get('item_type')} ({draft.get('cosmetic_type') or '—'})",
        f"Название: {draft.get('title') or '(по умолчанию)'}",
        f"Редкость: {draft.get('rarity')}",
        f"Цена: {draft.get('price_amount', '—')} / диапазон {draft.get('price_min_amount', '—')}-{draft.get('price_max_amount', '—')} {draft.get('price_currency_code')}",
        f"Сток: {draft.get('max_stock_per_rotation', '—')} (диапазон {draft.get('stock_min', '—')}-{draft.get('stock_max', '—')})",
        f"Личный лимит покупок: {draft.get('personal_purchase_limit', 0)}",
        f"Вес выбора: {draft.get('selection_weight', 1)}",
        f"Повторы в витрине: {'да' if draft.get('allow_repeat_in_rotation') else 'нет'}",
    ]
    await message.answer("\n".join(lines), reply_markup=keyboards.build_add_item_confirm_keyboard())


@router.callback_query(F.data == "bm_admin:add_item:confirm")
async def admin_add_item_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_permission(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    draft = await _draft(state)
    await state.clear()

    try:
        await black_market_admin.create_pool_item(
            callback.from_user.id,
            item_type=draft["item_type"],
            rarity=draft["rarity"],
            price_currency_code=draft["price_currency_code"],
            title=draft.get("title", ""),
            currency_code=draft.get("currency_code"),
            amount=draft.get("amount", 1),
            pack_id=draft.get("pack_id"),
            card_id=draft.get("card_id"),
            cosmetic_item_id=draft.get("cosmetic_item_id"),
            price_mode=draft.get("price_mode", "FIXED"),
            price_amount=draft.get("price_amount", 0),
            price_min_amount=draft.get("price_min_amount"),
            price_max_amount=draft.get("price_max_amount"),
            max_stock_per_rotation=draft.get("max_stock_per_rotation", 1),
            stock_min=draft.get("stock_min"),
            stock_max=draft.get("stock_max"),
            personal_purchase_limit=draft.get("personal_purchase_limit", 0),
            available_from=draft.get("available_from"),
            available_until=draft.get("available_until"),
            allow_repeat_in_rotation=draft.get("allow_repeat_in_rotation", False),
            selection_weight=draft.get("selection_weight", 1),
        )
    except (BlackMarketError, KeyError) as error:
        message_text = error.message if isinstance(error, BlackMarketError) else f"Не хватает данных: {error}"
        await callback.answer(message_text, show_alert=True)
        return

    await callback.answer("Товар создан и добавлен в пул.", show_alert=True)
    text = await build_dashboard_text()
    await edit_or_send(callback, text, keyboards.build_admin_dashboard_keyboard())
