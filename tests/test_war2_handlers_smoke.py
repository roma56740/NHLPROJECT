"""Прямые вызовы обработчиков app/handlers/war2.py и app/handlers/admin_war2.py через
настоящие (не дак-тайпинг) объекты aiogram Message/CallbackQuery/User/Chat.

Сервисный слой уже полностью покрыт tests/test_war2.py, но сами хендлеры (парсинг
callback_data, вызовы сервисных функций из UI-кода, сборка клавиатур) до этого файла
не выполнялись НИ РАЗУ — только компилировались (py_compile) и собирались в
Dispatcher (setup_routers()). Этот файл — тот же класс дешёвого предохранителя, что и
tests/test_stronghold_handlers_smoke.py, но для реальных Telegram-объектов, а не
только чистых build_*-функций (у war2.py другой стиль хендлеров — они сами вызывают
callback.message.edit_text/answer_photo, а не возвращают (text, keyboard))."""

from datetime import datetime

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from app.database.db import get_connection
from app.handlers import admin_war2, war2
from app.services import war2_core, war2_cosmetics, war2_draft, war2_roster
from app.states.admin_war2 import War2CosmeticCreateStates
from tests.conftest import create_test_user
from tests.test_war2 import _join_clan, _make_clan, _seed_base_pool


async def _fake_return_true(self, *args, **kwargs):
    return True


@pytest.fixture(autouse=True)
def _patch_telegram_io(monkeypatch):
    """Хендлеры реально шлют/редактируют сообщения через Bot API — здесь нет живого
    бота/сети, поэтому подменяем методы отправки на no-op, оставляя настоящие
    pydantic-объекты aiogram (isinstance-проверки в safe_edit_message остаются verны)."""
    monkeypatch.setattr(Message, "edit_text", _fake_return_true)
    monkeypatch.setattr(Message, "answer", _fake_return_true)
    monkeypatch.setattr(Message, "answer_photo", _fake_return_true)
    monkeypatch.setattr(CallbackQuery, "answer", _fake_return_true)


def _fsm_context(telegram_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _callback(telegram_id: int, data: str) -> CallbackQuery:
    user = User(id=telegram_id, is_bot=False, first_name="Test")
    chat = Chat(id=telegram_id, type="private")
    message = Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text="x")
    return CallbackQuery(id="1", from_user=user, chat_instance="x", message=message, data=data)


async def _telegram_id_for(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"])


class _AsAdmin:
    """config.settings — frozen dataclass, единственный экземпляр, на который все
    модули держат ссылку (`from config import settings`) — object.__setattr__ мутирует
    именно этот общий экземпляр, поэтому патчить нужно только тут, не в каждом модуле,
    который импортировал `settings` по имени."""

    def __init__(self, telegram_id: int):
        self.telegram_id = telegram_id
        self.original = None

    def __enter__(self):
        import config

        self.original = config.settings.admin_ids
        object.__setattr__(config.settings, "admin_ids", frozenset({self.telegram_id}))
        return self

    def __exit__(self, *exc):
        import config

        object.__setattr__(config.settings, "admin_ids", self.original)


# ---------------------------------------------------------------------------
# Игровой флоу: main -> start -> draft -> confirm -> result (SALARY_WAR/WILD_CARD)
# ---------------------------------------------------------------------------

async def test_war2_main_and_start_screens_do_not_crash(stronghold_db):
    await _seed_base_pool()
    user_id = await create_test_user("smoke-war2-main")
    await _make_clan("Smoke Clan", user_id)
    telegram_id = await _telegram_id_for(user_id)

    await war2.war2_main(_callback(telegram_id, "war2:main"))
    await war2.war2_start(_callback(telegram_id, "war2:start"))

    match = await war2_core.get_active_season()  # no active season yet -> should be None, no crash
    assert match is None


async def test_full_draft_flow_through_confirm_and_result(stronghold_db, monkeypatch):
    await _seed_base_pool()
    user_id = await create_test_user("smoke-war2-draft")
    await _make_clan("Smoke Draft Clan", user_id)
    telegram_id = await _telegram_id_for(user_id)

    # заставим roulette дать SALARY_WAR детерминированно (без Wild Card ветки)
    from app.services import war2_modes as modes_module

    async def _force_salary_war():
        return modes_module.WAR2_MODE_REGISTRY["SALARY_WAR"]

    monkeypatch.setattr(war2_core, "roll_active_mode", _force_salary_war)

    start = await war2_core.start_war2_match(user_id)
    assert start.mode.code == "SALARY_WAR"

    await war2.war2_pool(_callback(telegram_id, f"war2:pool:{start.match_id}:1"))

    # доигрываем драфт кликами по первой доступной карте на каждом ходу игрока
    for _ in range(5):
        state = await war2_draft.get_draft_state(start.match_id)
        if state["is_complete"]:
            break
        assert state["current_picker"] == "user"
        card_id = int(state["remaining"][0]["id"])
        await war2.war2_pick(_callback(telegram_id, f"war2:pick:{start.match_id}:{card_id}"))

    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is True

    await war2.war2_confirm(_callback(telegram_id, f"war2:confirm:{start.match_id}"))

    with get_connection() as connection:
        row = connection.execute("SELECT status FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
    assert row["status"] in ("completed", "drafting")  # 'drafting' только если salary cap заблокировал


async def test_clone_war_flow_through_confirm(stronghold_db, monkeypatch):
    await _seed_base_pool()
    user_id = await create_test_user("smoke-war2-clone")
    await _make_clan("Smoke Clone Clan", user_id)
    telegram_id = await _telegram_id_for(user_id)

    from app.services import war2_modes as modes_module

    async def _force_clone_war():
        return modes_module.WAR2_MODE_REGISTRY["CLONE_WAR"]

    monkeypatch.setattr(war2_core, "roll_active_mode", _force_clone_war)

    start = await war2_core.start_war2_match(user_id)
    assert start.mode.code == "CLONE_WAR"

    await war2.war2_clone(_callback(telegram_id, f"war2:clone:{start.match_id}"))

    with get_connection() as connection:
        row = connection.execute("SELECT user_lineup_json FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
    assert row["user_lineup_json"] != "[]"

    await war2.war2_confirm(_callback(telegram_id, f"war2:confirm:{start.match_id}"))

    with get_connection() as connection:
        row = connection.execute("SELECT status, result FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
    assert row["status"] == "completed"
    assert row["result"] in ("win", "loss")


async def test_wild_card_flow_through_handlers(stronghold_db, monkeypatch):
    await _seed_base_pool()
    user_id = await create_test_user("smoke-war2-wc")
    await _make_clan("Smoke WC Clan", user_id)
    telegram_id = await _telegram_id_for(user_id)

    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES ('Smoke Own', 'smoke-own-card', 'F', 95, 'T', 'C', ?, 'Rare', 'x.png', 100, 1)
            """,
            (collection["id"],),
        )
        card_id = int(cursor.lastrowid)
        user_card_cursor = connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, card_id)
        )
        own_user_card_id = int(user_card_cursor.lastrowid)
        connection.commit()

    from app.services import war2_modes as modes_module

    async def _force_wild_card():
        return modes_module.WAR2_MODE_REGISTRY["WILD_CARD"]

    monkeypatch.setattr(war2_core, "roll_active_mode", _force_wild_card)

    start = await war2_core.start_war2_match(user_id)
    assert start.mode.code == "WILD_CARD"

    for _ in range(5):
        state = await war2_draft.get_draft_state(start.match_id)
        if state["is_complete"]:
            break
        picked = int(state["remaining"][0]["id"])
        await war2.war2_pick(_callback(telegram_id, f"war2:pick:{start.match_id}:{picked}"))

    picks = await war2_draft.finalize_lineup_for(start.match_id, "user")
    replace_card_id = picks[0].card_id

    await war2.war2_wildcard_choose_target(_callback(telegram_id, f"war2:wc:{start.match_id}"))
    await war2.war2_wildcard_choose_replacement(_callback(telegram_id, f"war2:wcr:{start.match_id}:{replace_card_id}"))
    await war2.war2_wildcard_apply(
        _callback(telegram_id, f"war2:wcp:{start.match_id}:{replace_card_id}:{own_user_card_id}")
    )

    with get_connection() as connection:
        row = connection.execute(
            "SELECT used_wild_card, wild_card_user_card_id FROM war2_matches WHERE id = ?", (start.match_id,)
        ).fetchone()
    assert row["used_wild_card"] == 1
    assert row["wild_card_user_card_id"] == own_user_card_id

    await war2.war2_confirm(_callback(telegram_id, f"war2:confirm:{start.match_id}"))
    with get_connection() as connection:
        row = connection.execute("SELECT status FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
    assert row["status"] == "completed"


async def test_cancel_and_cosmetics_screens_do_not_crash(stronghold_db):
    await _seed_base_pool()
    user_id = await create_test_user("smoke-war2-misc")
    await _make_clan("Smoke Misc Clan", user_id)
    telegram_id = await _telegram_id_for(user_id)

    start = await war2_core.start_war2_match(user_id)
    await war2.war2_cancel(_callback(telegram_id, f"war2:cancel:{start.match_id}"))
    with get_connection() as connection:
        row = connection.execute("SELECT status FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
    assert row["status"] == "abandoned"

    for cosmetic_type in ("FRAME", "BACKGROUND", "NICK_BADGE"):
        await war2.war2_cosmetics_list(_callback(telegram_id, f"war2:cos:{cosmetic_type}"))

    frame_id = await war2_cosmetics.create_cosmetic_item(type="FRAME", code="smoke-frame", title="Smoke Frame", image_path="x.png")
    owned_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame_id)
    await war2.war2_cosmetics_equip(_callback(telegram_id, f"war2:eq:{owned_id}:FRAME"))
    assert await war2_cosmetics.get_equipped_frame_path(user_id) == "x.png"


# ---------------------------------------------------------------------------
# Админка
# ---------------------------------------------------------------------------

async def test_admin_war2_main_season_and_modes_screens(stronghold_db):
    admin_id = await create_test_user("smoke-war2-admin")
    with get_connection() as connection:
        admin_telegram_id = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (admin_id,)).fetchone()["telegram_id"]

    with _AsAdmin(int(admin_telegram_id)):
        await admin_war2.admin_war2_main(_callback(int(admin_telegram_id), "admin_war2:main"))
        await admin_war2.admin_war2_season(_callback(int(admin_telegram_id), "admin_war2:season"))
        await admin_war2.admin_war2_season_start(_callback(int(admin_telegram_id), "admin_war2:season_start"))

        season = await war2_core.get_active_season()
        assert season is not None

        await admin_war2.admin_war2_modes(_callback(int(admin_telegram_id), "admin_war2:modes"))
        await admin_war2.admin_war2_mode_toggle(_callback(int(admin_telegram_id), "admin_war2:mode_toggle:WILD_CARD"))

        with get_connection() as connection:
            row = connection.execute("SELECT active FROM war2_modes WHERE code = 'WILD_CARD'").fetchone()
        assert row["active"] == 0  # был активен по сиду -> выключен переключателем

        await admin_war2.admin_war2_season_end(_callback(int(admin_telegram_id), "admin_war2:season_end"))
        assert await war2_core.get_active_season() is None


async def test_admin_war2_cosmetic_create_flow(stronghold_db):
    admin_id = await create_test_user("smoke-war2-admin-cos")
    with get_connection() as connection:
        admin_telegram_id = int(connection.execute("SELECT telegram_id FROM users WHERE id = ?", (admin_id,)).fetchone()["telegram_id"])

    with _AsAdmin(admin_telegram_id):
        state = _fsm_context(admin_telegram_id)
        await admin_war2.admin_war2_cosmetic_create_start(
            _callback(admin_telegram_id, "admin_war2:coscreate:NICK_BADGE"), state
        )
        assert await state.get_state() == War2CosmeticCreateStates.waiting_for_code

        user = User(id=admin_telegram_id, is_bot=False, first_name="Admin")
        chat = Chat(id=admin_telegram_id, type="private")

        async def _text_message(text: str) -> Message:
            # Message.answer уже подменена автоиспользуемой фикстурой _patch_telegram_io
            return Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text=text)

        await admin_war2.admin_war2_cosmetic_create_code(await _text_message("smoke-badge-code"), state)
        await admin_war2.admin_war2_cosmetic_create_title(await _text_message("Smoke Badge"), state)
        await admin_war2.admin_war2_cosmetic_create_rarity(await _text_message("Rare"), state)
        await admin_war2.admin_war2_cosmetic_create_badge_text(await _text_message("SMOKE"), state)

        assert await state.get_state() is None
        items = await war2_cosmetics.list_cosmetic_items(type="NICK_BADGE")
        assert any(item.code == "smoke-badge-code" and item.badge_text == "SMOKE" for item in items)


# ---------------------------------------------------------------------------
# Ростер клана: экраны через реальные хендлеры
# ---------------------------------------------------------------------------

async def test_roster_screens_add_and_remove_through_handlers(stronghold_db):
    leader_id = await create_test_user("smoke-roster-leader")
    clan_id = await _make_clan("Smoke Roster Clan", leader_id)  # лидер уже в ростере
    member_id = await create_test_user("smoke-roster-member")
    await _join_clan(clan_id, member_id)
    leader_telegram_id = await _telegram_id_for(leader_id)

    await war2.war2_roster_screen(_callback(leader_telegram_id, "war2:roster"))
    await war2.war2_roster_add_list(_callback(leader_telegram_id, "war2:roster_add:1"))
    await war2.war2_roster_add_apply(_callback(leader_telegram_id, f"war2:roster_add_do:{member_id}"))

    roster = await war2_roster.get_clan_roster(clan_id)
    assert {m.user_id for m in roster} == {leader_id, member_id}

    await war2.war2_roster_remove(_callback(leader_telegram_id, f"war2:roster_rm:{member_id}"))
    roster = await war2_roster.get_clan_roster(clan_id)
    assert {m.user_id for m in roster} == {leader_id}


async def test_roster_screen_without_clan_does_not_crash(stronghold_db):
    user_id = await create_test_user("smoke-roster-no-clan")
    telegram_id = await _telegram_id_for(user_id)
    await war2.war2_roster_screen(_callback(telegram_id, "war2:roster"))


# ---------------------------------------------------------------------------
# SALARY_WAR: пересдача последнего раунда через реальный хендлер
# ---------------------------------------------------------------------------

async def test_salary_war_redo_round_through_handler(stronghold_db, monkeypatch):
    await _seed_base_pool()
    user_id = await create_test_user("smoke-redo-user")
    await _make_clan("Smoke Redo Clan", user_id)
    telegram_id = await _telegram_id_for(user_id)

    from app.services import war2_modes as modes_module

    async def _force_salary_war():
        return modes_module.WAR2_MODE_REGISTRY["SALARY_WAR"]

    monkeypatch.setattr(war2_core, "roll_active_mode", _force_salary_war)
    start = await war2_core.start_war2_match(user_id)

    for _ in range(6):
        state = await war2_draft.get_draft_state(start.match_id)
        if state["is_complete"]:
            break
        card_id = int(war2_draft.allowed_remaining_for_picker(state, "user")[0]["id"])
        await war2.war2_pick(_callback(telegram_id, f"war2:pick:{start.match_id}:{card_id}"))

    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is True

    await war2.war2_redo_last_round(_callback(telegram_id, f"war2:redo:{start.match_id}"))
    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is False
    assert state["current_round"] == 6

    # доигрываем и подтверждаем — весь путь до конца не должен падать
    for _ in range(6):
        state = await war2_draft.get_draft_state(start.match_id)
        if state["is_complete"]:
            break
        card_id = int(war2_draft.allowed_remaining_for_picker(state, "user")[0]["id"])
        await war2.war2_pick(_callback(telegram_id, f"war2:pick:{start.match_id}:{card_id}"))

    await war2.war2_confirm(_callback(telegram_id, f"war2:confirm:{start.match_id}"))
    with get_connection() as connection:
        row = connection.execute("SELECT status FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
    assert row["status"] in ("completed", "drafting")  # 'drafting' только если зарплата снова превышена
