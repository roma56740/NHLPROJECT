"""CLAN WAR 2.0 — игровой флоу: билет -> соперник -> War Roulette -> режим -> (Draft
или Clone War) -> Wild Card (если разрешён) -> подтверждение -> матч -> результат.

Тексты/клавиатуры оставлены инлайн в этом файле (как admin_stronghold.py — самый
новый прецедент в проекте), а не вынесены в отдельные app/keyboards/app/texts —
осознанное упрощение ради единого обзора всего флоу в одном месте при таком объёме
экранов; см. отчёт об изменениях.

Прогресс матча полностью в БД (war2_matches/war2_draft_picks) — match_id передаётся
через callback_data, а не через FSMContext, поэтому старые сообщения с кнопками
остаются рабочими и после перезапуска бота (в кнопке, а не в памяти процесса)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services import war2_core, war2_cosmetics, war2_draft, war2_modes
from app.services.card_sorting import set_user_card_sort_order
from app.services.renders import render_war2_lineup_image
from app.services.user_cards import get_player_cards_page
from app.services.users import get_player_profile_by_telegram_id
from app.services.war2_common import War2Error
from app.utils.messages import safe_delete_message, safe_edit_message
from app.utils.users import is_admin

router = Router()


async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(callback.message, Message):
        ok = await safe_edit_message(callback, text, reply_markup)
        if not ok:
            return
    else:
        await callback.answer()


def _back_row(callback_data: str = "war2:main") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]


def _card_label(row) -> str:
    name = row["name"] if hasattr(row, "keys") else row.name
    position = row["position"] if hasattr(row, "keys") else row.position
    overall = row["overall"] if hasattr(row, "keys") else row.overall
    return f"{name} · {position} {overall}"


async def _build_war2_main_screen(telegram_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    profile = await get_player_profile_by_telegram_id(telegram_id)
    if profile is None:
        return None

    remaining = await war2_core.get_remaining_tickets(profile.id)
    season = await war2_core.get_active_season()
    season_line = f"Сезон #{season.season_number}, до {season.ends_at}" if season else "Сезон не запущен."
    text = (
        "<b>⚔️ CLAN WAR 2.0</b>\n\n"
        f"{season_line}\n"
        f"Билетов сегодня: {remaining}/5\n\n"
        "Найди соперника, дождись War Roulette и собери состав в выбранном режиме."
    )
    keyboard = [
        [InlineKeyboardButton(text="🎲 Найти матч", callback_data="war2:start")],
        [InlineKeyboardButton(text="👥 Ростер клана", callback_data="war2:roster")],
        [InlineKeyboardButton(text="🎨 Косметика", callback_data="cosmetics:main")],
    ]
    if is_admin(telegram_id):
        keyboard.append([InlineKeyboardButton(text="🛠 Админка CLAN WAR 2.0", callback_data="admin_war2:main")])
    keyboard.append(_back_row("community:main"))
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "⚔️ CLAN WAR 2.0")
async def war2_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()
    await safe_delete_message(message)
    screen = await _build_war2_main_screen(message.from_user.id)
    if screen is None:
        await message.answer("Открой игру через /start.")
        return
    text, keyboard = screen
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "war2:main")
async def war2_main(callback: CallbackQuery) -> None:
    screen = await _build_war2_main_screen(callback.from_user.id)
    if screen is None:
        await callback.answer("Открой игру через /start.", show_alert=True)
        return
    text, keyboard = screen
    await _edit_or_send(callback, text, keyboard)


@router.callback_query(F.data == "war2:start")
async def war2_start(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer("Открой игру через /start.", show_alert=True)
        return

    try:
        start = await war2_core.start_war2_match(profile.id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return

    opponent_line = f"Соперник: {start.opponent.name}" + (" (бот)" if start.opponent.type == "bot" else "")
    text = (
        "<b>🎲 War Roulette</b>\n\n"
        f"{opponent_line}\n"
        f"Режим: <b>{start.mode.title}</b>\n\n"
    )

    if not start.mode.uses_draft:
        text += "Clone War: одинаковый состав для обеих сторон, без выбора карт."
        keyboard = [
            [InlineKeyboardButton(text="▶️ Собрать состав", callback_data=f"war2:clone:{start.match_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"war2:cancel:{start.match_id}")],
        ]
    else:
        # Пул уже сгенерирован внутри war2_core.start_war2_match() (сервисный слой) —
        # см. докстринг там про баг с пустым пулом, пойманный tests/test_war2_handlers_smoke.py.
        text += "Собери состав через Draft: 6 раундов — 3 FWD, 2 DEF и 1 GK."
        keyboard = [
            [InlineKeyboardButton(text="🎯 Начать Draft", callback_data=f"war2:pool:{start.match_id}:1")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"war2:cancel:{start.match_id}")],
        ]

    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:cancel:"))
async def war2_cancel(callback: CallbackQuery) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    match_id = int(callback.data.split(":")[2])
    await war2_core.cancel_war2_match(match_id, profile.id)
    await callback.answer("Матч отменён. Билет не списан.")
    await war2_main(callback)


@router.callback_query(F.data.startswith("war2:clone:"))
async def war2_clone(callback: CallbackQuery) -> None:
    match_id = int(callback.data.split(":")[2])
    try:
        card_ids = await war2_modes.build_clone_war_lineup()
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return

    # Сохраняем сгенерированный ростер сразу — иначе war2_confirm() позже сгенерировал
    # бы ДРУГОЙ случайный набор, отличный от показанного игроку на этом экране.
    import json as _json
    from app.database.db import get_connection
    with get_connection() as connection:
        payload = _json.dumps(card_ids)
        connection.execute(
            "UPDATE war2_matches SET user_lineup_json = ?, opponent_lineup_json = ? WHERE id = ?",
            (payload, payload, match_id),
        )
        connection.commit()

    await _show_confirm_screen(callback, match_id, card_ids)


PICKS_PER_PAGE = 6


@router.callback_query(F.data.startswith("war2:pool:"))
async def war2_pool(callback: CallbackQuery) -> None:
    _, _, match_id_text, page_text = callback.data.split(":")
    match_id, page = int(match_id_text), int(page_text)
    await _render_draft_screen(callback, match_id, page)


async def _advance_opponent_picks(match_id: int) -> None:
    for _ in range(10):
        state = await war2_draft.get_draft_state(match_id)
        if state["is_complete"] or state["current_picker"] != "opponent":
            return
        await war2_draft.auto_pick_for_opponent(match_id)


async def _render_draft_screen(callback: CallbackQuery, match_id: int, page: int) -> None:
    await _advance_opponent_picks(match_id)
    state = await war2_draft.get_draft_state(match_id)

    if state["is_complete"]:
        await _after_draft_complete(callback, match_id)
        return

    remaining = war2_draft.allowed_remaining_for_picker(state, "user")
    pages_count = max(1, (len(remaining) + PICKS_PER_PAGE - 1) // PICKS_PER_PAGE)
    page = min(max(page, 1), pages_count)
    page_rows = remaining[(page - 1) * PICKS_PER_PAGE : page * PICKS_PER_PAGE]

    picks_done = len(state["user_picks"]) + len(state["opponent_picks"])
    text = (
        f"<b>🎯 Draft — раунд {state['current_round']}/{war2_draft.PICKS_PER_SIDE}</b>\n\n"
        f"Твой пик ({picks_done + 1}/{war2_draft.PICKS_PER_SIDE * 2}). Доступно: {len(remaining)}.\n"
        "Состав: 3 FWD · 2 DEF · 1 GK"
    )
    keyboard = [
        [InlineKeyboardButton(text=_card_label(row), callback_data=f"war2:pick:{match_id}:{int(row['id'])}")]
        for row in page_rows
    ]
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"war2:pool:{match_id}:{page - 1}"))
    if page < pages_count:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"war2:pool:{match_id}:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton(text="❌ Отменить матч", callback_data=f"war2:cancel:{match_id}")])

    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:pick:"))
async def war2_pick(callback: CallbackQuery) -> None:
    _, _, match_id_text, card_id_text = callback.data.split(":")
    match_id, card_id = int(match_id_text), int(card_id_text)
    try:
        await war2_draft.record_pick(match_id, "user", card_id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await _render_draft_screen(callback, match_id, 1)


async def _after_draft_complete(callback: CallbackQuery, match_id: int) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    with_wild_card = await _match_mode_allows_wild_card(match_id)
    picks = await war2_draft.finalize_lineup_for(match_id, "user")
    text = "<b>✅ Draft завершён</b>\n\nТвой состав:\n" + "\n".join(f"• {_card_label_for_lineup(card)}" for card in picks)

    keyboard = []
    if with_wild_card:
        keyboard.append([InlineKeyboardButton(text="🃏 Wild Card: заменить карту", callback_data=f"war2:wc:{match_id}")])
    keyboard.append([InlineKeyboardButton(text="✅ Подтвердить состав", callback_data=f"war2:confirm:{match_id}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отменить матч", callback_data=f"war2:cancel:{match_id}")])

    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


def _card_label_for_lineup(card) -> str:
    return f"{card.name} · {card.position} {card.overall} OVR"


async def _match_mode_allows_wild_card(match_id: int) -> bool:
    with_wild_card = False
    from app.database.db import get_connection

    with get_connection() as connection:
        row = connection.execute("SELECT mode_code, used_wild_card FROM war2_matches WHERE id = ?", (match_id,)).fetchone()
    if row is not None:
        mode = war2_modes.WAR2_MODE_REGISTRY.get(row["mode_code"])
        with_wild_card = bool(mode and mode.allow_wild_card and not row["used_wild_card"])
    return with_wild_card


@router.callback_query(F.data.startswith("war2:wc:"))
async def war2_wildcard_choose_target(callback: CallbackQuery) -> None:
    match_id = int(callback.data.split(":")[2])
    picks = await war2_draft.finalize_lineup_for(match_id, "user")
    text = "<b>🃏 Wild Card</b>\n\nКакую карту заменить?"
    keyboard = [
        [InlineKeyboardButton(text=_card_label_for_lineup(card), callback_data=f"war2:wcr:{match_id}:{card.card_id}")]
        for card in picks
    ]
    keyboard.append(_back_row(f"war2:pool:{match_id}:1"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:wcr:"))
async def war2_wildcard_choose_replacement(callback: CallbackQuery) -> None:
    _, _, match_id_text, replace_card_id_text = callback.data.split(":")
    await _render_own_cards_page(callback, int(match_id_text), int(replace_card_id_text), 1)


async def _render_own_cards_page(callback: CallbackQuery, match_id: int, replace_card_id: int, page: int) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    own_page = await get_player_cards_page(profile.id, page=page, per_page=5)
    sort_label = "слабые → сильные" if own_page.sort_order == "ovr_asc" else "сильные → слабые"
    text = (
        f"<b>🃏 Wild Card</b>\n\n"
        f"Выбери карту из своей коллекции (стр. {own_page.page}/{own_page.pages_count}).\n"
        f"Сортировка: <b>{sort_label}</b>"
    )
    keyboard = [
        [InlineKeyboardButton(
            text=f"{card.name} · {card.position} {card.overall}",
            callback_data=f"war2:wcp:{match_id}:{replace_card_id}:{card.id}",
        )]
        for card in own_page.cards
    ]
    nav_row = []
    if own_page.page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"war2:wco:{match_id}:{replace_card_id}:{own_page.page - 1}"))
    if own_page.page < own_page.pages_count:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"war2:wco:{match_id}:{replace_card_id}:{own_page.page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    next_sort = "ovr_desc" if own_page.sort_order == "ovr_asc" else "ovr_asc"
    keyboard.append([InlineKeyboardButton(
        text="⬆️ Слабые → сильные" if own_page.sort_order == "ovr_asc" else "⬇️ Сильные → слабые",
        callback_data=f"war2:wcsort:{match_id}:{replace_card_id}:{next_sort}",
    )])
    keyboard.append(_back_row(f"war2:wc:{match_id}"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:wco:"))
async def war2_wildcard_own_page(callback: CallbackQuery) -> None:
    _, _, match_id_text, replace_card_id_text, page_text = callback.data.split(":")
    await _render_own_cards_page(callback, int(match_id_text), int(replace_card_id_text), int(page_text))


@router.callback_query(F.data.startswith("war2:wcsort:"))
async def war2_wildcard_sort(callback: CallbackQuery) -> None:
    _, _, match_id_text, replace_card_id_text, sort_order = callback.data.split(":")
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    await set_user_card_sort_order(profile.id, sort_order)
    await _render_own_cards_page(callback, int(match_id_text), int(replace_card_id_text), 1)
    await callback.answer("Сортировка изменена")


@router.callback_query(F.data.startswith("war2:wcp:"))
async def war2_wildcard_apply(callback: CallbackQuery) -> None:
    _, _, match_id_text, replace_card_id_text, user_card_id_text = callback.data.split(":")
    match_id, replace_card_id, user_card_id = int(match_id_text), int(replace_card_id_text), int(user_card_id_text)
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        new_roster, _replaced = await war2_modes.apply_wild_card_replacement(match_id, profile.id, replace_card_id, user_card_id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await _show_confirm_screen(callback, match_id, [card.card_id for card in new_roster], is_wild_card=True)


async def _show_confirm_screen(callback: CallbackQuery, match_id: int, card_ids: list[int], is_wild_card: bool = False) -> None:
    roster = await war2_draft.build_ephemeral_lineup(card_ids)

    from app.database.db import get_connection
    with get_connection() as connection:
        mode_code = connection.execute("SELECT mode_code FROM war2_matches WHERE id = ?", (match_id,)).fetchone()["mode_code"]

    if mode_code == "SALARY_WAR":
        try:
            await war2_modes.validate_salary_cap(card_ids)
        except War2Error as error:
            text = f"<b>🚫 {error.message}</b>\n\nМожно пересдать последний раунд драфта и выбрать карту дешевле."
            keyboard = [
                [InlineKeyboardButton(text="🔄 Пересдать последний раунд", callback_data=f"war2:redo:{match_id}")],
                [InlineKeyboardButton(text="❌ Отменить матч", callback_data=f"war2:cancel:{match_id}")],
            ]
            await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))
            return

    ovr = war2_draft.compute_war2_lineup_ovr(roster)
    text = (
        ("<b>🃏 Карта заменена</b>\n\n" if is_wild_card else "<b>✅ Состав готов</b>\n\n")
        + f"Средний OVR: {ovr}\n\n"
        + "\n".join(f"• {_card_label_for_lineup(card)}" for card in roster)
    )
    keyboard = [
        [InlineKeyboardButton(text="🏒 Играть матч", callback_data=f"war2:confirm:{match_id}")],
        [InlineKeyboardButton(text="❌ Отменить матч", callback_data=f"war2:cancel:{match_id}")],
    ]
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:redo:"))
async def war2_redo_last_round(callback: CallbackQuery) -> None:
    match_id = int(callback.data.split(":")[2])
    try:
        round_number = await war2_draft.redo_last_round(match_id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer(f"Раунд {round_number} пересдан.")
    await _render_draft_screen(callback, match_id, 1)


@router.callback_query(F.data.startswith("war2:confirm:"))
async def war2_confirm(callback: CallbackQuery) -> None:
    match_id = int(callback.data.split(":")[2])
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    from app.database.db import get_connection
    with get_connection() as connection:
        match_row = connection.execute(
            "SELECT mode_code, user_clan_id, opponent_clan_id, opponent_name, used_wild_card, wild_card_replaced_card_id, wild_card_user_card_id "
            "FROM war2_matches WHERE id = ? AND user_id = ?",
            (match_id, profile.id),
        ).fetchone()
    if match_row is None:
        await callback.answer("Матч не найден.", show_alert=True)
        return

    mode = war2_modes.WAR2_MODE_REGISTRY.get(match_row["mode_code"])
    # состав пользователя: драфт-пики (+ возможная Wild Card замена) либо Clone War —
    # оба случая уже выражаются текущими war2_draft_picks/сохранённой заменой.
    if mode is not None and mode.uses_draft:
        user_roster = await war2_draft.finalize_lineup_for(match_id, "user")
        opponent_roster = await war2_draft.finalize_lineup_for(match_id, "opponent")
        if match_row["used_wild_card"]:
            from app.services.lineup import row_to_lineup_card
            with get_connection() as connection:
                owned_row = connection.execute(
                    """
                    SELECT user_cards.id AS user_card_id, user_cards.card_id, user_cards.lineup_slot,
                           cards.name, cards.player_key, cards.position, cards.overall, cards.team,
                           cards.country, cards.rarity, cards.image_path, cards.salary,
                           collections.name AS collection_name, collections.code AS collection_code
                    FROM user_cards JOIN cards ON cards.id = user_cards.card_id
                    JOIN collections ON collections.id = cards.collection_id
                    WHERE user_cards.id = ?
                    """,
                    (match_row["wild_card_user_card_id"],),
                ).fetchone()
            replacement = row_to_lineup_card(owned_row)
            replaced_id = match_row["wild_card_replaced_card_id"]
            user_roster = [replacement if card.card_id == replaced_id else card for card in user_roster]
    else:
        with get_connection() as connection:
            row = connection.execute("SELECT user_lineup_json FROM war2_matches WHERE id = ?", (match_id,)).fetchone()
        import json as _json
        stored = _json.loads(row["user_lineup_json"]) if row and row["user_lineup_json"] and row["user_lineup_json"] != "[]" else None
        if stored:
            card_ids = stored
        else:
            card_ids = await war2_modes.build_clone_war_lineup()
        user_roster = await war2_draft.build_ephemeral_lineup(card_ids)
        opponent_roster = await war2_draft.build_ephemeral_lineup(card_ids)

    try:
        result = await war2_core.record_war2_match_result(
            match_id=match_id,
            user_id=profile.id,
            user_clan_id=match_row["user_clan_id"],
            opponent_clan_id=match_row["opponent_clan_id"],
            user_cards=user_roster,
            opponent_cards=opponent_roster,
            opponent_name=match_row["opponent_name"],
        )
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return

    icon = "🏆" if result.result == "win" else "💔"
    text = (
        f"<b>{icon} {result.user_score}:{result.opponent_score}</b>\n\n"
        f"Результат: {'Победа' if result.result == 'win' else 'Поражение'}\n"
        f"Рейтинг: {'+' if result.rating_delta >= 0 else ''}{result.rating_delta}\n"
        f"MVP: {result.mvp_title}"
    )
    keyboard = [[InlineKeyboardButton(text="⬅️ В меню CLAN WAR 2.0", callback_data="war2:main")]]

    try:
        badge_text = await war2_cosmetics.get_equipped_badge_text(profile.id)
        background_path = await war2_cosmetics.get_equipped_background_path(profile.id)
        frame_path = await war2_cosmetics.get_equipped_frame_path(profile.id)
        image_path = render_war2_lineup_image(
            user_roster,
            user_id=profile.id,
            average_overall=war2_draft.compute_war2_lineup_ovr(user_roster),
            title="CLAN WAR 2.0",
            background_override_path=background_path,
            frame_override_path=frame_path,
            nickname=profile.nickname,
            badge_text=badge_text,
        )
        if isinstance(callback.message, Message):
            await callback.message.answer_photo(
                photo=image_path.open("rb"),
                caption=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            )
            await callback.answer()
            return
    except Exception:
        pass

    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


# ---------------------------------------------------------------------------
# Ростер клана (раздел ТЗ "Clan size: 5 игроков") — управляют лидер/офицер
# ---------------------------------------------------------------------------

async def _viewer_clan_id(telegram_id: int) -> tuple[int | None, int | None]:
    """(user_id, clan_id) для текущего игрока, либо (user_id, None) без клана."""
    profile = await get_player_profile_by_telegram_id(telegram_id)
    if profile is None:
        return None, None
    from app.database.db import get_connection

    with get_connection() as connection:
        row = connection.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (profile.id,)).fetchone()
    return profile.id, (int(row["clan_id"]) if row else None)


@router.callback_query(F.data == "war2:roster")
async def war2_roster_screen(callback: CallbackQuery) -> None:
    from app.services import war2_roster

    user_id, clan_id = await _viewer_clan_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой игру через /start.", show_alert=True)
        return
    if clan_id is None:
        await _edit_or_send(
            callback, "Нужно состоять в клане, чтобы участвовать в CLAN WAR 2.0.",
            InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
        )
        return

    roster = await war2_roster.get_clan_roster(clan_id)
    limit = await war2_roster.get_roster_size_limit()
    from app.database.db import get_connection

    with get_connection() as connection:
        my_role = connection.execute(
            "SELECT role FROM clan_members WHERE clan_id = ? AND user_id = ?", (clan_id, user_id)
        ).fetchone()
    is_manager = bool(my_role and my_role["role"] in ("leader", "officer"))

    text = f"<b>👥 Ростер CLAN WAR 2.0</b> ({len(roster)}/{limit})\n\n"
    text += "\n".join(f"• {member.nickname}" for member in roster) if roster else "Ростер пуст."
    if not is_manager:
        text += "\n\nТолько лидер или офицер клана может менять состав ростера."

    keyboard = []
    if is_manager:
        for member in roster:
            keyboard.append([InlineKeyboardButton(text=f"❌ Убрать {member.nickname}", callback_data=f"war2:roster_rm:{member.user_id}")])
        if len(roster) < limit:
            keyboard.append([InlineKeyboardButton(text="➕ Добавить игрока", callback_data="war2:roster_add:1")])
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:roster_add:"))
async def war2_roster_add_list(callback: CallbackQuery) -> None:
    from app.database.db import get_connection
    from app.services import war2_roster

    page = int(callback.data.split(":")[2])
    user_id, clan_id = await _viewer_clan_id(callback.from_user.id)
    if user_id is None or clan_id is None:
        await callback.answer()
        return

    roster = await war2_roster.get_clan_roster(clan_id)
    rostered_ids = {member.user_id for member in roster}
    with get_connection() as connection:
        members = connection.execute(
            "SELECT clan_members.user_id, users.nickname FROM clan_members JOIN users ON users.id = clan_members.user_id WHERE clan_members.clan_id = ? ORDER BY users.nickname",
            (clan_id,),
        ).fetchall()
    candidates = [row for row in members if int(row["user_id"]) not in rostered_ids]

    if not candidates:
        await callback.answer("Все участники клана уже в ростере (или клан пуст).", show_alert=True)
        return

    text = "<b>➕ Добавить в ростер</b>\n\nВыбери игрока:"
    keyboard = [
        [InlineKeyboardButton(text=row["nickname"], callback_data=f"war2:roster_add_do:{int(row['user_id'])}")]
        for row in candidates[:20]
    ]
    keyboard.append(_back_row("war2:roster"))
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:roster_add_do:"))
async def war2_roster_add_apply(callback: CallbackQuery) -> None:
    from app.services import war2_roster

    target_user_id = int(callback.data.split(":")[2])
    user_id, clan_id = await _viewer_clan_id(callback.from_user.id)
    if user_id is None or clan_id is None:
        await callback.answer()
        return
    try:
        await war2_roster.add_roster_member(clan_id, target_user_id, user_id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Добавлено в ростер.")
    await war2_roster_screen(callback)


@router.callback_query(F.data.startswith("war2:roster_rm:"))
async def war2_roster_remove(callback: CallbackQuery) -> None:
    from app.services import war2_roster

    target_user_id = int(callback.data.split(":")[2])
    user_id, clan_id = await _viewer_clan_id(callback.from_user.id)
    if user_id is None or clan_id is None:
        await callback.answer()
        return
    try:
        await war2_roster.remove_roster_member(clan_id, target_user_id, user_id)
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Убран из ростера.")
    await war2_roster_screen(callback)


# ---------------------------------------------------------------------------
# Косметика: список своих предметов по типу + экипировка
# ---------------------------------------------------------------------------

COSMETIC_TYPE_TITLES = {"FRAME": "🖼 Рамки", "BACKGROUND": "🏞 Фоны", "NICK_BADGE": "🏷 Приставки"}


@router.callback_query(F.data.startswith("war2:cos:"))
async def war2_cosmetics_list(callback: CallbackQuery) -> None:
    cosmetic_type = callback.data.split(":")[2]
    await _render_cosmetics_list(callback, cosmetic_type)


async def _render_cosmetics_list(callback: CallbackQuery, cosmetic_type: str) -> None:
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return

    items = await war2_cosmetics.get_user_cosmetics_page(profile.id, cosmetic_type)
    title = COSMETIC_TYPE_TITLES.get(cosmetic_type, cosmetic_type)
    text = f"<b>{title}</b>\n\n" + ("У тебя пока нет таких предметов." if not items else "Выбери, что экипировать:")

    keyboard = []
    for item in items:
        mark = "✅ " if item.equipped else ""
        label = f"{mark}{item.title}" + (f" [{item.badge_text}]" if item.badge_text else "")
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"war2:eq:{item.id}:{cosmetic_type}")])

    type_row = [
        InlineKeyboardButton(text=("• " if code == cosmetic_type else "") + label, callback_data=f"war2:cos:{code}")
        for code, label in COSMETIC_TYPE_TITLES.items()
    ]
    keyboard.append(type_row)
    keyboard.append(_back_row())
    await _edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("war2:eq:"))
async def war2_cosmetics_equip(callback: CallbackQuery) -> None:
    _, _, owned_id_text, cosmetic_type = callback.data.split(":")
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer()
        return
    try:
        await war2_cosmetics.equip_cosmetic(profile.id, int(owned_id_text))
    except War2Error as error:
        await callback.answer(error.message, show_alert=True)
        return
    await callback.answer("Экипировано.")
    # ВАЖНО: CallbackQuery.data — замороженное pydantic-поле в этой версии aiogram,
    # присвоение (callback.data = ...) реально падает с ValidationError в проде.
    # Пойман tests/test_war2_handlers_smoke.py. Вызываем общий рендер напрямую.
    await _render_cosmetics_list(callback, cosmetic_type)
