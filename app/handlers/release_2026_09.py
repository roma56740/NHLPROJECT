from __future__ import annotations

from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.services import release_2026_09 as release
from app.utils.users import is_admin

router = Router()


def kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows if row
        ]
    )


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        if message.photo or message.video or message.animation or message.document:
            await message.delete()
            await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            try:
                await message.edit_reply_markup(reply_markup=reply_markup)
            except TelegramBadRequest:
                pass
            return
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


def _format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _balance(telegram_id: int, code: str) -> int:
    with get_connection() as connection:
        uid = release.get_user_id_by_telegram(connection, telegram_id)
        return release.currency_balance(connection, uid, code) if uid is not None else 0


def _box_rows(telegram_id: int) -> list:
    return release.get_box_inventory(telegram_id)


async def show_boxes(callback: CallbackQuery) -> None:
    boxes = _box_rows(callback.from_user.id)
    coins = _balance(callback.from_user.id, "coins")
    lines = ["<b>📦 Боксы</b>", "", f"🪙 Coins: <b>{_format_int(coins)}</b>", ""]
    rows: list[list[tuple[str, str]]] = []
    for box in boxes:
        qty = int(box["quantity"] or 0)
        if not int(box["is_shop_available"]) and qty <= 0:
            continue
        suffix = f" · ×{qty}" if qty else ""
        lines.append(f"• <b>{escape(str(box['name']))}</b>{suffix}")
        if int(box["is_shop_available"]):
            lines.append(f"  {_format_int(int(box['price_amount']))} Coins")
        rows.append([(f"{box['name']}{suffix}", f"release:box:{box['code']}")])
    if len(lines) == 4:
        lines.append("Пока нет доступных боксов.")
    rows.append([("🛒 Магазин", "release:shop"), ("🏠 Главное меню", "menu:main")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_box(callback: CallbackQuery, code: str) -> None:
    boxes = {str(row["code"]): row for row in _box_rows(callback.from_user.id)}
    box = boxes.get(code)
    if box is None:
        await callback.answer("Бокс не найден.", show_alert=True)
        return
    qty = int(box["quantity"] or 0)
    lines = [f"<b>📦 {escape(str(box['name']))}</b>", "", escape(str(box["description"] or "Nexcore reward box"))]
    if int(box["is_shop_available"]):
        lines += ["", f"Цена: <b>{_format_int(int(box['price_amount']))} Coins</b>"]
    lines += [f"В инвентаре: <b>×{qty}</b>"]
    if code == "fireside_box":
        with get_connection() as connection:
            uid = release.get_user_id_by_telegram(connection, callback.from_user.id)
            state = connection.execute("SELECT first_guarantee_used FROM fireside_box_state WHERE user_id=?", (uid or -1,)).fetchone()
        first = not state or not int(state[0])
        lines += ["", "🔥 <b>Fireside Box</b>", "Первое открытие аккаунта гарантирует Fireside-карту." if first else "Гарантия первого открытия уже использована.", "Cole Caufield 100 в пул не входит.", "После первого открытия: карта 25% · Last Spark 5% · обычный X-Factor 15% · Rank Coins 20% · Coins 25% · Fireside Collectible 10%."]
    elif code == "dead_mans_chest":
        state = release.cursed_state(callback.from_user.id)
        pity = int(state["pity"]) if state else 0
        lines += ["", "🏴‍☠️ <b>Dead Man's Chest</b>", f"Pity: <b>{pity}/6</b>. Если первые 5 боксов без event-карты, 6-й гарантирует карту."]
    actions: list[list[tuple[str, str]]] = []
    if qty > 0:
        actions.append([("🎁 Открыть", f"release:box_open:{code}")])
    if int(box["is_shop_available"]):
        actions.append([("🛒 Купить", f"release:box_buy:{code}")])
    actions.append([("⬅️ Боксы", "release:boxes")])
    await edit_or_send(callback, "\n".join(lines), kb(*actions))


async def show_shop(callback: CallbackQuery) -> None:
    energy = _balance(callback.from_user.id, "energy")
    coins = _balance(callback.from_user.id, "coins")
    text = (
        "<b>🛒 Магазин Nexcore</b>\n\n"
        f"🪙 Coins: <b>{_format_int(coins)}</b>\n"
        f"⚡ Energy: <b>{_format_int(energy)}</b>\n\n"
        "Игровые награды и покупки используют систему Boxes."
    )
    await edit_or_send(callback, text, kb(
        [("📦 Боксы", "release:boxes"), ("⚡ Купить Energy", "release:energy")],
        [("🏠 Главное меню", "menu:main")],
    ))


async def show_energy(callback: CallbackQuery) -> None:
    balance = _balance(callback.from_user.id, "energy")
    lines = [
        "<b>⚡ Energy Store</b>", "",
        f"Баланс: <b>{_format_int(balance)} Energy</b>", "",
        "Базовый курс: 1 Energy = 1 ₽ до скидки.",
        "Минимальная покупка — 50 Energy. Чем больше объём, тем выше скидка; после 10 000 Energy максимальная скидка остаётся 50%.",
        "До подключения платёжного провайдера покупка оформляется через @teyld. Energy начисляется только администрацией после подтверждения оплаты.", "",
        "Выбери объём:",
    ]
    rows: list[list[tuple[str, str]]] = []
    pair: list[tuple[str, str]] = []
    for quantity, discount in release.ENERGY_TIERS:
        price = release.energy_price_rub(quantity)
        lines.append(f"• {_format_int(quantity)} Energy → {_format_int(price)} ₽" + (f" (−{discount}%)" if discount else ""))
        pair.append((f"{_format_int(quantity)} E · {_format_int(price)} ₽", f"release:energy_order:{quantity}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([("⬅️ Магазин", "release:shop")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_pass(callback: CallbackQuery, page: int = 1) -> None:
    status = release.pass_status(callback.from_user.id)
    if status is None:
        await callback.answer("Открой игру через /start", show_alert=True)
        return
    pages = 6
    page = min(max(1, page), pages)
    start = (page - 1) * 5 + 1
    end = min(30, start + 4)
    premium = bool(status["premium"])
    claims = status["claims"]
    lines = [
        "<b>🔥 FIRESIDE SEASON PASS</b>", "",
        f"Уровень: <b>{status['level']}/30</b> · BP: <b>{status['bp_points']}</b>",
        f"⚡ Energy: <b>{_format_int(status['energy'])}</b>",
        f"Premium: <b>{'активен' if premium else 'не активен · 400 Energy'}</b>", "",
        f"Уровни {start}–{end}:",
    ]
    rows: list[list[tuple[str, str]]] = []
    for lvl in range(start, end + 1):
        free_label = release.reward_label(lvl, "free")
        prem_label = release.reward_label(lvl, "premium")
        free_state = "✅" if (lvl, "free") in claims else ("🟢" if lvl <= status["level"] else "🔒")
        prem_state = "✅" if (lvl, "premium") in claims else ("🟢" if premium and lvl <= status["level"] else "🔒")
        lines += ["", f"<b>{lvl}.</b> FREE {free_state} {escape(free_label)}", f"   PREMIUM {prem_state} {escape(prem_label)}"]
        claim_row: list[tuple[str, str]] = []
        if lvl <= status["level"] and (lvl, "free") not in claims:
            claim_row.append((f"🎁 Free {lvl}", f"release:pass_claim:{lvl}:free"))
        if premium and lvl <= status["level"] and (lvl, "premium") not in claims:
            claim_row.append((f"🔥 Premium {lvl}", f"release:pass_claim:{lvl}:premium"))
        if claim_row:
            rows.append(claim_row)
    if not premium:
        rows.append([("⚡ Купить Premium · 400 Energy", "release:pass_buy")])
    nav: list[tuple[str, str]] = []
    if page > 1: nav.append(("◀️", f"release:pass:{page-1}"))
    nav.append((f"{page}/{pages}", f"release:pass:{page}"))
    if page < pages: nav.append(("▶️", f"release:pass:{page+1}"))
    rows.append(nav)
    rows.append([("🔥 Fireside Craft", "release:craft"), ("📦 Боксы", "release:boxes")])
    rows.append([("⬅️ Прогресс", "menu:user:progress")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_heroes(callback: CallbackQuery) -> None:
    paths = release.hero_paths(callback.from_user.id)
    lines = [
        "<b>🏆 HEROES</b>", "",
        "Открой путь героя за 100 000 Coins, получи 94 OVR и пройди 6 последовательных глав в обычных матчах. Финал эволюционирует тот же экземпляр карты до 100 OVR.", "",
        "PART 1 · 10.09.2026 12:00 МСК", "PART 2 · 17.09.2026 12:00 МСК", "",
    ]
    rows: list[list[tuple[str, str]]] = []
    for item in paths:
        hero = item["hero"]; path = item["path"]; available = item["available"]
        if path:
            status = "100 ✅" if int(path["claimed_100"]) else f"глава {int(path['current_chapter'])}/6"
        else:
            status = "доступен" if available else "скоро"
        lines.append(f"• <b>{escape(str(hero['name']))}</b> · {status}")
        rows.append([(f"{hero['name']} · {status}", f"release:hero:{hero['key']}")])
    rows.append([("⬅️ События", "release:events")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_hero_detail(callback: CallbackQuery, hero_key: str) -> None:
    item = next((x for x in release.hero_paths(callback.from_user.id) if x["hero"]["key"] == hero_key), None)
    if item is None:
        await callback.answer("Герой не найден", show_alert=True); return
    hero = item["hero"]; path = item["path"]; chapter_row = item["chapter"]
    lines = [f"<b>🏆 {escape(str(hero['name']))}</b>", f"PART {hero['part']} · 94 → 100 OVR", ""]
    actions: list[list[tuple[str, str]]] = []
    if not item["available"]:
        release_at = "10 сентября · 12:00 МСК" if int(hero["part"]) == 1 else "17 сентября · 12:00 МСК"
        lines += ["🔒 <b>COMING SOON</b>", release_at]
    elif path is None:
        lines += ["Путь ещё не открыт.", "Цена: <b>100 000 Coins</b>. После покупки выдаётся HEROES 94 OVR и открывается глава I."]
        actions.append([("Открыть путь · 100 000 Coins", f"release:hero_unlock:{hero_key}")])
    elif int(path["claimed_100"]):
        lines += ["✅ <b>LEGACY COMPLETE</b>", "Тот же экземпляр HEROES-карты эволюционировал до 100 OVR."]
    else:
        chapter = int(path["current_chapter"])
        definition = release.HERO_CHAPTERS[hero_key][chapter - 1]
        progress = int(chapter_row["progress"] or 0) if chapter_row else 0
        target = int(definition["target"])
        done = int(chapter_row["completed"] or 0) if chapter_row else 0
        lines += [f"Глава <b>{chapter}/6 · {escape(str(definition['title']))}</b>", f"Прогресс: <b>{progress}/{target}</b>"]
        if int(definition["reward"]):
            lines.append(f"Награда главы: {_format_int(int(definition['reward']))} Coins")
        lines += ["", "Прогресс идёт только в обычных матчах, когда именно выданный HEROES 94 стоит в активном составе."]
        complete_count = 0
        with get_connection() as connection:
            uid = release.get_user_id_by_telegram(connection, callback.from_user.id)
            if uid is not None:
                complete_count = int(connection.execute("SELECT COUNT(*) FROM heroes_chapter_progress WHERE user_id=? AND hero_key=? AND completed=1", (uid, hero_key)).fetchone()[0])
        if complete_count >= 6:
            actions.append([("🏆 Получить HEROES 100", f"release:hero_claim:{hero_key}")])
        elif done and chapter == 6:
            actions.append([("🏆 Получить HEROES 100", f"release:hero_claim:{hero_key}")])
    actions.append([("⬅️ HEROES", "release:heroes")])
    await edit_or_send(callback, "\n".join(lines), kb(*actions))


async def show_events(callback: CallbackQuery) -> None:
    phase = release.pirates_phase()
    pirate_label = "СКОРО · 23 сентября" if phase == "coming" else ("ЗАВЕРШЁН" if phase == "ended" else "LIVE · до 30 сентября 23:59 МСК")
    text = (
        "<b>🎪 События Nexcore</b>\n\n"
        "🏆 <b>HEROES</b> — карьерные пути 94 → 100 OVR.\n"
        f"🏴‍☠️ <b>Cursed Mirror</b> — {pirate_label}.\n"
        "🔥 <b>Fireside Craft</b> — крафт карт Fireside через карту на 2 OVR ниже + Fireside Collectibles."
    )
    await edit_or_send(callback, text, kb(
        [("🏆 HEROES", "release:heroes")],
        [("🏴‍☠️ Cursed Mirror", "release:cursed")],
        [("🔥 Fireside Craft", "release:craft")],
        [("🏠 Главное меню", "menu:main")],
    ))


async def show_achievements(callback: CallbackQuery) -> None:
    items = release.achievement_status(callback.from_user.id)
    lines = ["<b>🏅 Достижения</b>", "", "Награды одноразовые. Прогресс по картам lifetime: продажа или обмен не откатывают его."]
    rows: list[list[tuple[str, str]]] = []
    for item in items:
        progress = min(int(item["progress"]), int(item["target"]))
        reward = f"{_format_int(item['coins'])} Coins"
        if int(item["rank"]): reward += f" + {item['rank']} Rank Coins"
        state = "✅ получено" if item["claimed"] else ("🎁 готово" if progress >= item["target"] else f"{progress}/{item['target']}")
        lines += ["", f"<b>{escape(item['title'])}</b> · {state}", escape(item["description"]), f"Награда: {reward}"]
        if not item["claimed"] and progress >= int(item["target"]):
            rows.append([(f"🎁 {item['title']}", f"release:achievement_claim:{item['code']}")])
    rows.append([("⬅️ Прогресс", "menu:user:progress")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_craft(callback: CallbackQuery) -> None:
    recipes = release.fireside_recipes(callback.from_user.id)
    if not recipes:
        await callback.answer("Профиль не найден", show_alert=True); return
    balance = int(recipes[0]["collectible_balance"]) if recipes else 0
    lines = ["<b>🔥 Fireside Craft</b>", "", f"Fireside Collectibles: <b>×{balance}</b>", "", "Рецепт всегда: <b>одна твоя карта ровно на 2 OVR ниже + N Fireside Collectibles</b>. Материальная карта сгорает. Cole Caufield 100 не крафтится.", ""]
    rows: list[list[tuple[str, str]]] = []
    for recipe in recipes:
        can = recipe["owned_material_cards"] > 0 and balance >= recipe["collectibles"]
        lines.append(f"• {recipe['name']} {recipe['overall']} → {recipe['required_ovr']} OVR + ×{recipe['collectibles']} · {'✅' if can else '🔒'}")
        rows.append([(f"{'✅' if can else '🔒'} {recipe['name']} {recipe['overall']}", f"release:craft_target:{recipe['card_id']}")])
    rows.append([("⬅️ События", "release:events")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_craft_target(callback: CallbackQuery, target_card_id: int) -> None:
    recipe = next((x for x in release.fireside_recipes(callback.from_user.id) if int(x["card_id"] or 0) == target_card_id), None)
    if recipe is None:
        await callback.answer("Рецепт не найден", show_alert=True); return
    cards = release.fireside_material_cards(callback.from_user.id, target_card_id)
    text = (
        f"<b>🔥 Крафт {escape(str(recipe['name']))} · {recipe['overall']} OVR</b>\n\n"
        f"Нужно: <b>1 карта {recipe['required_ovr']} OVR + {recipe['collectibles']} Fireside Collectibles</b>.\n"
        f"Collectibles сейчас: ×{recipe['collectible_balance']}\n\n"
        "Выбери конкретный экземпляр карты для сжигания:"
    )
    rows: list[list[tuple[str, str]]] = []
    for card in cards[:20]:
        rows.append([(f"🔥 {card['name']} · {card['overall']} · #{card['user_card_id']}", f"release:craft_do:{target_card_id}:{card['user_card_id']}")])
    if not cards:
        text += "\n\nПодходящих карт нет."
    rows.append([("⬅️ Крафты", "release:craft")])
    await edit_or_send(callback, text, kb(*rows))


async def show_cursed(callback: CallbackQuery) -> None:
    state = release.cursed_state(callback.from_user.id)
    if state is None:
        await callback.answer("Открой игру через /start", show_alert=True); return
    phase = state["phase"]
    status_text = "COMING SOON · 23 сентября 00:00 МСК" if phase == "coming" else ("EVENT ENDED · 30 сентября 23:59 МСК" if phase == "ended" else "LIVE · до 30 сентября 23:59 МСК")
    boxes = {str(row["code"]): int(row["quantity"] or 0) for row in _box_rows(callback.from_user.id)}
    chest = boxes.get("dead_mans_chest", 0)
    lines = [
        "<b>🏴‍☠️ CURSED MIRROR</b>", f"<b>{status_text}</b>", "",
        f"Победы сегодня: <b>{state['wins']}/6</b>",
        f"Cursed Collectibles: <b>×{state['collectibles']}</b>",
        f"Dead Man's Chest: <b>×{chest}</b>",
        f"Pity: <b>{state['pity']}/6</b>", "",
        "После победы выбери 1 карту соперника: Mirror-копия получает +1 OVR, работает только в ивенте 3 матча, максимум 3 активных.", "",
        "<b>Mirror Crew:</b>",
    ]
    if state["mirrors"]:
        for mirror in state["mirrors"]:
            lines.append(f"• {escape(str(mirror['name']))} · {mirror['mirrored_ovr']} OVR · {mirror['matches_left']} матч.")
    else:
        lines.append("• пусто")
    rows: list[list[tuple[str, str]]] = []
    if phase == "active":
        rows.append([("🏒 Сыграть event-матч", "release:cursed_play")])
        if chest > 0:
            rows.append([("📦 Открыть Dead Man's Chest", "release:box_open:dead_mans_chest")])
        if int(state["collectibles"]) >= 4:
            rows.append([("101 Joe Sakic", "release:cursed_exchange:sakic"), ("101 Henrik Lundqvist", "release:cursed_exchange:lundqvist")])
    rows.append([("⬅️ События", "release:events")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_boxes_admin(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows_db = release.admin_list_boxes()
    lines = ["<b>📦 Управление Boxes</b>", "", "Legacy Packs отключены; здесь управляются только новые Boxes."]
    rows: list[list[tuple[str, str]]] = []
    for box in rows_db:
        active = bool(box["active"]); shop = bool(box["is_shop_available"])
        price = f" · {_format_int(box['price_amount'])} {box['price_currency_code'] or '—'}" if int(box['price_amount'] or 0) else ""
        lines.append(f"\n{'✅' if active else '🚫'} <b>{escape(str(box['name']))}</b>{price} · shop {'ON' if shop else 'OFF'}")
        rows.append([(f"{'✅' if active else '🚫'} {box['name']}", f"release:box_admin_toggle_active:{box['code']}"), (f"🛒 {'ON' if shop else 'OFF'}", f"release:box_admin_toggle_shop:{box['code']}")])
    rows.append([("⬅️ Админка", "menu:admin:content")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


async def show_energy_admin(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    orders = release.list_pending_energy_orders(30)
    lines = ["<b>⚡ Заявки Energy</b>", "", f"Ожидают подтверждения: <b>{len(orders)}</b>"]
    rows: list[list[tuple[str, str]]] = [
        [("⚡ Ручная выдача Energy", "admin_wallets:main")],
    ]
    for order in orders:
        nickname = escape(str(order["nickname"] or order["telegram_id"]))
        lines.append(f"\n#{order['id']} · {nickname}\n{_format_int(order['energy_amount'])} Energy · {_format_int(order['rub_price'])} ₽ · −{order['discount_percent']}%")
        rows.append([(f"#{order['id']} · {order['energy_amount']} Energy", f"release:energy_admin_view:{order['id']}")])
    rows.append([("⬅️ Админка", "menu:admin:economy")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows))


@router.callback_query(F.data == "release:boxes_admin")
async def boxes_admin(callback: CallbackQuery) -> None:
    await show_boxes_admin(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("release:box_admin_toggle_active:"))
async def box_admin_toggle_active(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    code = (callback.data or "").split(":")[-1]
    ok, msg = release.admin_toggle_box(code, "active")
    await callback.answer(msg, show_alert=not ok)
    await show_boxes_admin(callback)


@router.callback_query(F.data.startswith("release:box_admin_toggle_shop:"))
async def box_admin_toggle_shop(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    code = (callback.data or "").split(":")[-1]
    ok, msg = release.admin_toggle_box(code, "is_shop_available")
    await callback.answer(msg, show_alert=not ok)
    await show_boxes_admin(callback)


@router.callback_query(F.data == "release:shop")
async def shop_main(callback: CallbackQuery) -> None:
    await show_shop(callback); await callback.answer()


@router.callback_query(F.data == "release:boxes")
async def boxes_main(callback: CallbackQuery) -> None:
    await show_boxes(callback); await callback.answer()


@router.callback_query(F.data.startswith("release:box:"))
async def box_detail(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":", 2)[2]
    await show_box(callback, code); await callback.answer()


@router.callback_query(F.data.startswith("release:box_buy:"))
async def box_buy(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":", 2)[2]
    ok, msg = release.buy_box(callback.from_user.id, code)
    await callback.answer(msg, show_alert=not ok)
    await show_box(callback, code)


@router.callback_query(F.data.startswith("release:box_open:"))
async def box_open(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":", 2)[2]
    ok, msg, rewards = release.open_box(callback.from_user.id, code)
    if not ok:
        await callback.answer(msg, show_alert=True); return
    reward_text = "\n".join(f"• {escape(str(r.get('label', 'Reward')))}" for r in rewards) or "• Награда выдана"
    await edit_or_send(callback, f"<b>🎁 {escape(msg)}</b>\n\n{reward_text}", kb([("⬅️ К боксам", "release:boxes")]))
    await callback.answer()


@router.callback_query(F.data == "release:energy")
async def energy_main(callback: CallbackQuery) -> None:
    await show_energy(callback); await callback.answer()


@router.callback_query(F.data.startswith("release:energy_order:"))
async def energy_order(callback: CallbackQuery) -> None:
    quantity = int((callback.data or "").split(":")[-1])
    ok, msg, order_id = release.create_energy_order(callback.from_user.id, quantity)
    text = f"<b>⚡ Energy</b>\n\n{escape(msg)}"
    if ok:
        text += "\n\nЗаявка создана. После подтверждения оплаты администрацией Energy начислится на баланс автоматически и только один раз."
    await edit_or_send(callback, text, kb([("⬅️ Energy Store", "release:energy"), ("🏠 Главное меню", "menu:main")]))
    await callback.answer("Заявка создана" if ok else msg, show_alert=not ok)


@router.callback_query(F.data.startswith("release:pass:"))
async def pass_page(callback: CallbackQuery) -> None:
    page = int((callback.data or "").split(":")[-1])
    await show_pass(callback, page); await callback.answer()


@router.callback_query(F.data == "release:pass")
async def pass_main(callback: CallbackQuery) -> None:
    await show_pass(callback, 1); await callback.answer()


@router.callback_query(F.data == "release:pass_buy")
async def pass_buy(callback: CallbackQuery) -> None:
    ok, msg = release.purchase_fireside_pass(callback.from_user.id)
    await callback.answer(msg, show_alert=not ok)
    await show_pass(callback, 1)


@router.callback_query(F.data.startswith("release:pass_claim:"))
async def pass_claim(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    level = int(parts[2]); track = parts[3]
    ok, msg = release.claim_pass_reward(callback.from_user.id, level, track)
    await callback.answer(msg, show_alert=not ok)
    await show_pass(callback, min(6, max(1, ceil(level / 5))))


@router.callback_query(F.data == "release:events")
async def events_main(callback: CallbackQuery) -> None:
    await show_events(callback); await callback.answer()


@router.callback_query(F.data == "release:heroes")
async def heroes_main(callback: CallbackQuery) -> None:
    await show_heroes(callback); await callback.answer()


@router.callback_query(F.data.startswith("release:hero:"))
async def hero_detail(callback: CallbackQuery) -> None:
    key = (callback.data or "").split(":")[-1]
    await show_hero_detail(callback, key); await callback.answer()


@router.callback_query(F.data.startswith("release:hero_unlock:"))
async def hero_unlock(callback: CallbackQuery) -> None:
    key = (callback.data or "").split(":")[-1]
    ok, msg = release.unlock_hero(callback.from_user.id, key)
    await callback.answer(msg, show_alert=not ok)
    await show_hero_detail(callback, key)


@router.callback_query(F.data.startswith("release:hero_claim:"))
async def hero_claim(callback: CallbackQuery) -> None:
    key = (callback.data or "").split(":")[-1]
    ok, msg = release.claim_hero_100(callback.from_user.id, key)
    await callback.answer(msg, show_alert=not ok)
    await show_hero_detail(callback, key)


@router.callback_query(F.data == "release:achievements")
async def achievements_main(callback: CallbackQuery) -> None:
    await show_achievements(callback); await callback.answer()


@router.callback_query(F.data.startswith("release:achievement_claim:"))
async def achievement_claim(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":")[-1]
    ok, msg = release.claim_achievement(callback.from_user.id, code)
    await callback.answer(msg, show_alert=not ok)
    await show_achievements(callback)


@router.callback_query(F.data == "release:craft")
async def craft_main(callback: CallbackQuery) -> None:
    await show_craft(callback); await callback.answer()


@router.callback_query(F.data.startswith("release:craft_target:"))
async def craft_target(callback: CallbackQuery) -> None:
    target = int((callback.data or "").split(":")[-1])
    await show_craft_target(callback, target); await callback.answer()


@router.callback_query(F.data.startswith("release:craft_do:"))
async def craft_do(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    target = int(parts[2]); material = int(parts[3])
    ok, msg = release.craft_fireside(callback.from_user.id, target, material)
    await callback.answer(msg, show_alert=not ok)
    await show_craft(callback)


@router.callback_query(F.data == "release:cursed")
async def cursed_main(callback: CallbackQuery) -> None:
    await show_cursed(callback); await callback.answer()


@router.callback_query(F.data == "release:cursed_play")
async def cursed_play(callback: CallbackQuery) -> None:
    ok, msg, result = await release.play_cursed_match(callback.from_user.id)
    if not ok or not result:
        await callback.answer(msg, show_alert=True); return
    lines = ["<b>🏴‍☠️ Cursed Mirror · матч завершён</b>", "", f"Счёт: <b>{result['score']}:{result['opponent_score']}</b>", f"{msg}", f"Победы сегодня: <b>{result['wins']}/6</b>"]
    if result["collectible_drop"]: lines.append("🔥 Выпал Cursed Collectible ×1")
    if result["box_granted"]: lines.append("📦 За 6/6 побед выдан Dead Man's Chest ×1")
    rows: list[list[tuple[str, str]]] = []
    if result["win"]:
        lines += ["", "Выбери одну карту соперника для Mirror-копии (+1 OVR, 3 event-матча):"]
        for card in result["opponent_cards"]:
            rows.append([(f"{card['name']} · {card['overall']}→{min(110, card['overall']+1)}", f"release:mirror:{result['match_id']}:{card['card_id']}")])
    rows.append([("⬅️ Cursed Mirror", "release:cursed")])
    await edit_or_send(callback, "\n".join(lines), kb(*rows)); await callback.answer()


@router.callback_query(F.data.startswith("release:mirror:"))
async def mirror_pick(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    match_id = int(parts[2]); source_card_id = int(parts[3])
    ok, msg = release.add_mirror_card(callback.from_user.id, match_id, source_card_id)
    if not ok and msg == "replace_required":
        state = release.cursed_state(callback.from_user.id)
        rows = [[(f"♻️ {m['name']} · {m['mirrored_ovr']} · {m['matches_left']} матч.", f"release:mirror_replace:{match_id}:{source_card_id}:{m['id']}")] for m in (state["mirrors"] if state else [])]
        rows.append([("Отмена", "release:cursed")])
        await edit_or_send(callback, "<b>Mirror Crew заполнен 3/3</b>\n\nВыбери старую Mirror-карту, которую нужно уничтожить и заменить новой.", kb(*rows))
        await callback.answer(); return
    await callback.answer(msg, show_alert=not ok)
    await show_cursed(callback)


@router.callback_query(F.data.startswith("release:mirror_replace:"))
async def mirror_replace(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    match_id = int(parts[2]); source_card_id = int(parts[3]); replace_id = int(parts[4])
    ok, msg = release.add_mirror_card(callback.from_user.id, match_id, source_card_id, replace_id)
    await callback.answer(msg, show_alert=not ok)
    await show_cursed(callback)


@router.callback_query(F.data.startswith("release:cursed_exchange:"))
async def cursed_exchange(callback: CallbackQuery) -> None:
    choice = (callback.data or "").split(":")[-1]
    key = "joe sakic" if choice == "sakic" else "henrik lundqvist"
    ok, msg = release.exchange_cursed_collectibles(callback.from_user.id, key)
    await callback.answer(msg, show_alert=not ok)
    await show_cursed(callback)


@router.callback_query(F.data == "release:energy_admin")
async def energy_admin(callback: CallbackQuery) -> None:
    await show_energy_admin(callback); await callback.answer()


@router.callback_query(F.data.startswith("release:energy_admin_view:"))
async def energy_admin_view(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    order_id = int((callback.data or "").split(":")[-1])
    row = next((r for r in release.list_pending_energy_orders(100) if int(r["id"]) == order_id), None)
    if row is None:
        await callback.answer("Заявка уже обработана или не найдена", show_alert=True); await show_energy_admin(callback); return
    text = (f"<b>⚡ Energy Order #{order_id}</b>\n\n"
            f"Игрок: <b>{escape(str(row['nickname'] or row['telegram_id']))}</b>\n"
            f"Telegram ID: <code>{row['telegram_id']}</code>\n"
            f"Energy: <b>{_format_int(row['energy_amount'])}</b>\n"
            f"Скидка: <b>{row['discount_percent']}%</b>\n"
            f"Оплата: <b>{_format_int(row['rub_price'])} ₽</b>\n\n"
            "Подтверждай только после фактической оплаты. Повторное начисление одной заявки технически блокируется статусом заказа.")
    await edit_or_send(callback, text, kb(
        [("✅ Подтвердить и начислить", f"release:energy_confirm:{order_id}")],
        [("❌ Отменить", f"release:energy_cancel:{order_id}")],
        [("⬅️ Заявки", "release:energy_admin")],
    )); await callback.answer()


@router.callback_query(F.data.startswith("release:energy_confirm:"))
async def energy_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    order_id = int((callback.data or "").split(":")[-1])
    ok, msg = release.confirm_energy_order(order_id, callback.from_user.id, True)
    await callback.answer(msg, show_alert=not ok); await show_energy_admin(callback)


@router.callback_query(F.data.startswith("release:energy_cancel:"))
async def energy_cancel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    order_id = int((callback.data or "").split(":")[-1])
    ok, msg = release.confirm_energy_order(order_id, callback.from_user.id, False)
    await callback.answer(msg, show_alert=not ok); await show_energy_admin(callback)
