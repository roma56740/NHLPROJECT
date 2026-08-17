"""Прямые вызовы обработчиков app/handlers/ranked.py и app/handlers/admin_ranked.py
через настоящие (не дак-тайпинг) объекты aiogram Message/CallbackQuery/User/Chat —
тот же класс дешёвого предохранителя, что и tests/test_war2_handlers_smoke.py
(который на CLAN WAR 2.0 нашёл 3 реальных бага, невидимых для сервисных тестов)."""

from datetime import datetime

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from app.database.db import get_connection
from app.handlers import admin_ranked, ranked
from app.services import ranked_core, ranked_cosmetics, ranked_pass
from app.states.admin_ranked import RankedCosmeticCreateStates, RankedLeagueEditStates, RankedPassCreateStates
from tests.conftest import create_test_user, grant_balance
from tests.test_ranked import _build_lineup, _set_league


async def _fake_return_true(self, *args, **kwargs):
    return True


@pytest.fixture(autouse=True)
def _patch_telegram_io(monkeypatch):
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


def _message(telegram_id: int, text: str) -> Message:
    user = User(id=telegram_id, is_bot=False, first_name="Test")
    chat = Chat(id=telegram_id, type="private")
    return Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text=text)


async def _telegram_id_for(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"])


class _AsAdmin:
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
# Игровой флоу
# ---------------------------------------------------------------------------

async def test_ranked_main_screen_and_button_do_not_crash(stronghold_db):
    user_id = await create_test_user("smoke-ranked-main")
    await _set_league(user_id, "AHL")
    telegram_id = await _telegram_id_for(user_id)

    await ranked.ranked_main(_callback(telegram_id, "ranked:main"))
    await ranked.ranked_button(_message(telegram_id, ranked.RANKED_BUTTON_TEXT))


async def test_ranked_main_screen_without_profile_does_not_crash(stronghold_db):
    await ranked.ranked_main(_callback(999_999_999, "ranked:main"))
    await ranked.ranked_button(_message(999_999_998, ranked.RANKED_BUTTON_TEXT))


async def test_ranked_play_blocked_below_ahl(stronghold_db):
    user_id = await create_test_user("smoke-ranked-ncaa")
    await _set_league(user_id, "NCAA")
    await _build_lineup(user_id, salary_per_card=3000)
    telegram_id = await _telegram_id_for(user_id)

    await ranked.ranked_play(_callback(telegram_id, "ranked:play"))  # не должно упасть, должен показать ошибку


async def test_full_ranked_match_through_handler(stronghold_db, monkeypatch):
    await ranked_core.start_ranked_season()
    monkeypatch.setattr(ranked, "RANKED_MATCH_PLAYING_SECONDS", 0)
    monkeypatch.setattr(ranked, "SHOOTOUT_CHOICE_SECONDS", 0)
    monkeypatch.setattr(ranked, "SHOOTOUT_RESULT_PAUSE_SECONDS", 0)
    user_id = await create_test_user("smoke-ranked-play")
    await _set_league(user_id, "AHL")
    await _build_lineup(user_id, salary_per_card=3000)
    telegram_id = await _telegram_id_for(user_id)

    await ranked.ranked_play(_callback(telegram_id, "ranked:play"))
    await ranked.ranked_history(_callback(telegram_id, "ranked:history"))
    await ranked.ranked_leaderboard(_callback(telegram_id, "ranked:leaderboard"))

    with get_connection() as connection:
        count = connection.execute("SELECT COUNT(*) n FROM ranked_matches WHERE user_id = ?", (user_id,)).fetchone()["n"]
    assert count == 1


# ---------------------------------------------------------------------------
# Косметика + рамки для карт
# ---------------------------------------------------------------------------

async def test_ranked_cosmetics_and_frame_flow_through_handlers(stronghold_db):
    from app.services import war2_cosmetics

    user_id = await create_test_user("smoke-ranked-cos")
    telegram_id = await _telegram_id_for(user_id)

    for cosmetic_type in ("NICK_BADGE", "PROFILE_BACKGROUND", "TITLE"):
        await ranked.ranked_cosmetics_list(_callback(telegram_id, f"ranked:cosmetics:{cosmetic_type}"))

    badge_id = await war2_cosmetics.create_cosmetic_item(type="NICK_BADGE", code="smoke-ranked-badge", title="Smoke Badge", badge_text="SMOKE")
    owned_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, badge_id)
    await ranked.ranked_cosmetics_equip(_callback(telegram_id, f"ranked:eq:{owned_id}:NICK_BADGE"))
    assert await war2_cosmetics.get_equipped_badge_text(user_id) == "SMOKE"

    # рамка для карты
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        card = connection.execute(
            "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES ('Smoke','smoke','F',80,'T','C',?,'Common','x.png',100,1)",
            (collection["id"],),
        )
        uc = connection.execute("INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, int(card.lastrowid)))
        user_card_id = int(uc.lastrowid)
        connection.commit()

    frame_item_id = await war2_cosmetics.create_cosmetic_item(type="CARD_FRAME", code="smoke-ranked-frame", title="Smoke Frame", image_path="x.png")
    owned_frame_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame_item_id)

    await ranked.ranked_frames_list(_callback(telegram_id, "ranked:frames"))
    await ranked.ranked_frame_pick(_callback(telegram_id, f"ranked:frame_pick:{owned_frame_id}"))
    await ranked.ranked_frame_apply(_callback(telegram_id, f"ranked:frame_apply:{owned_frame_id}:{user_card_id}"))

    binding = await ranked_cosmetics.get_card_frame_for_card(user_card_id)
    assert binding is not None


# ---------------------------------------------------------------------------
# Ranked Packs + Pass
# ---------------------------------------------------------------------------

async def test_ranked_pack_open_through_handler(stronghold_db):
    user_id = await create_test_user("smoke-ranked-pack")
    telegram_id = await _telegram_id_for(user_id)

    with get_connection() as connection:
        pack_row = connection.execute("SELECT id FROM ranked_packs WHERE code = 'ranked_pack_bronze'").fetchone()
        pack_id = int(pack_row["id"])
        connection.execute("INSERT INTO user_ranked_packs (user_id, pack_id, quantity) VALUES (?, ?, 1)", (user_id, pack_id))
        connection.commit()

    await ranked.ranked_packs_list(_callback(telegram_id, "ranked:packs"))
    await ranked.ranked_pack_open(_callback(telegram_id, f"ranked:pack_open:{pack_id}"))


async def test_ranked_pass_flow_through_handlers(stronghold_db):
    user_id = await create_test_user("smoke-ranked-pass")
    telegram_id = await _telegram_id_for(user_id)
    grant_balance(user_id, "coins", 10_000)

    await ranked.ranked_pass_main(_callback(telegram_id, "ranked:pass"))  # пропуска ещё нет

    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO ranked_passes (title, levels_count, points_per_level, gold_currency_code, gold_price_amount, platinum_currency_code, platinum_price_amount, upgrade_currency_code, upgrade_price_amount, active) VALUES ('Smoke Pass', 60, 100, 'coins', 500, 'coins', 1500, 'coins', 1000, 1)"
        )
        pass_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO ranked_pass_rewards (pass_id, level, track, reward_type, currency_code, amount, title) VALUES (?, 1, 'free', 'currency', 'coins', 50, 'Level 1 Free')",
            (pass_id,),
        )
        connection.execute(
            "INSERT INTO ranked_pass_rewards (pass_id, level, track, reward_type, currency_code, amount, title) VALUES (?, 1, 'gold', 'currency', 'coins', 50, 'Level 1 Gold')",
            (pass_id,),
        )
        connection.commit()

    await ranked.ranked_pass_main(_callback(telegram_id, "ranked:pass"))
    await ranked.ranked_pass_rewards(_callback(telegram_id, f"ranked:pass_rewards:{pass_id}:free"))

    with get_connection() as connection:
        free_reward = connection.execute("SELECT id FROM ranked_pass_rewards WHERE pass_id = ? AND track = 'free'", (pass_id,)).fetchone()
    await ranked.ranked_pass_claim(_callback(telegram_id, f"ranked:pass_claim:{free_reward['id']}"))

    await ranked.ranked_pass_buy_gold(_callback(telegram_id, f"ranked:pass_buy_gold:{pass_id}"))
    state = await ranked_pass.get_user_pass_state(user_id, pass_id)
    assert state.gold_unlocked is True

    await ranked.ranked_pass_upgrade(_callback(telegram_id, f"ranked:pass_upgrade:{pass_id}"))
    state = await ranked_pass.get_user_pass_state(user_id, pass_id)
    assert state.platinum_unlocked is True


# ---------------------------------------------------------------------------
# Админка
# ---------------------------------------------------------------------------

async def test_admin_ranked_main_season_and_leagues_screens(stronghold_db):
    admin_id = await create_test_user("smoke-ranked-admin")
    admin_telegram_id = await _telegram_id_for(admin_id)

    with _AsAdmin(admin_telegram_id):
        await admin_ranked.admin_ranked_main(_callback(admin_telegram_id, "admin_ranked:main"))
        await admin_ranked.admin_ranked_season(_callback(admin_telegram_id, "admin_ranked:season"))
        await admin_ranked.admin_ranked_season_start(_callback(admin_telegram_id, "admin_ranked:season_start"))

        season = await ranked_core.get_active_season()
        assert season is not None

        await admin_ranked.admin_ranked_leagues(_callback(admin_telegram_id, "admin_ranked:leagues:1"))

        with get_connection() as connection:
            league_row = connection.execute("SELECT id FROM ranked_leagues WHERE division_code = 'bronze' AND tier_number = 1").fetchone()
        league_id = int(league_row["id"])

        state = _fsm_context(admin_telegram_id)
        await admin_ranked.admin_ranked_league_edit_start(_callback(admin_telegram_id, f"admin_ranked:league_edit:{league_id}"), state)
        assert await state.get_state() == RankedLeagueEditStates.waiting_for_min_points
        await admin_ranked.admin_ranked_league_edit_apply(_message(admin_telegram_id, "77"), state)

        with get_connection() as connection:
            updated = connection.execute("SELECT min_points FROM ranked_leagues WHERE id = ?", (league_id,)).fetchone()
        assert updated["min_points"] == 77

        await admin_ranked.admin_ranked_season_end(_callback(admin_telegram_id, "admin_ranked:season_end"))
        assert await ranked_core.get_active_season() is None


async def test_admin_ranked_packs_screens(stronghold_db):
    admin_id = await create_test_user("smoke-ranked-admin-packs")
    admin_telegram_id = await _telegram_id_for(admin_id)

    with _AsAdmin(admin_telegram_id):
        await admin_ranked.admin_ranked_packs(_callback(admin_telegram_id, "admin_ranked:packs"))

        with get_connection() as connection:
            pack_row = connection.execute("SELECT id FROM ranked_packs WHERE code = 'ranked_pack_gold'").fetchone()
        pack_id = int(pack_row["id"])

        await admin_ranked.admin_ranked_pack_detail(_callback(admin_telegram_id, f"admin_ranked:pack:{pack_id}"))

        state = _fsm_context(admin_telegram_id)
        await admin_ranked.admin_ranked_pack_slot_currency_start(_callback(admin_telegram_id, f"admin_ranked:pack_slot_currency:{pack_id}"), state)
        await admin_ranked.admin_ranked_pack_slot_currency_apply(_message(admin_telegram_id, "250"), state)

        with get_connection() as connection:
            slots = connection.execute("SELECT COUNT(*) n FROM ranked_pack_slots WHERE pack_id = ?", (pack_id,)).fetchone()["n"]
        assert slots >= 2  # дефолтный XP-слот из сида + новый currency-слот


async def test_admin_ranked_pass_create_and_reward_flow(stronghold_db):
    admin_id = await create_test_user("smoke-ranked-admin-pass")
    admin_telegram_id = await _telegram_id_for(admin_id)

    with _AsAdmin(admin_telegram_id):
        state = _fsm_context(admin_telegram_id)
        await admin_ranked.admin_ranked_pass_create_start(_callback(admin_telegram_id, "admin_ranked:pass_create"), state)
        assert await state.get_state() == RankedPassCreateStates.waiting_for_title

        await admin_ranked.admin_ranked_pass_create_title(_message(admin_telegram_id, "Smoke Admin Pass"), state)
        await admin_ranked.admin_ranked_pass_create_gold_price(_message(admin_telegram_id, "500"), state)
        await admin_ranked.admin_ranked_pass_create_platinum_price(_message(admin_telegram_id, "0"), state)
        await admin_ranked.admin_ranked_pass_create_upgrade_price(_message(admin_telegram_id, "1000"), state)

        active_pass = await ranked_pass.get_active_pass()
        assert active_pass is not None and active_pass.title == "Smoke Admin Pass"

        await admin_ranked.admin_ranked_pass_main(_callback(admin_telegram_id, "admin_ranked:pass"))

        state2 = _fsm_context(admin_telegram_id)
        await admin_ranked.admin_ranked_pass_reward_add_start(_callback(admin_telegram_id, f"admin_ranked:pass_reward_add:{active_pass.id}"), state2)
        await admin_ranked.admin_ranked_pass_reward_level(_message(admin_telegram_id, "5,gold"), state2)
        await admin_ranked.admin_ranked_pass_reward_amount(_message(admin_telegram_id, "300"), state2)
        await admin_ranked.admin_ranked_pass_reward_title(_message(admin_telegram_id, "Level 5 Gold Reward"), state2)

        with get_connection() as connection:
            reward = connection.execute(
                "SELECT * FROM ranked_pass_rewards WHERE pass_id = ? AND level = 5 AND track = 'gold'", (active_pass.id,)
            ).fetchone()
        assert reward is not None and reward["amount"] == 300


async def test_admin_ranked_cosmetic_create_flow(stronghold_db):
    admin_id = await create_test_user("smoke-ranked-admin-cos")
    admin_telegram_id = await _telegram_id_for(admin_id)

    with _AsAdmin(admin_telegram_id):
        state = _fsm_context(admin_telegram_id)
        await admin_ranked.admin_ranked_cosmetics_list(_callback(admin_telegram_id, "admin_ranked:cos:TITLE"))
        await admin_ranked.admin_ranked_cosmetic_create_start(_callback(admin_telegram_id, "admin_ranked:coscreate:TITLE"), state)
        assert await state.get_state() == RankedCosmeticCreateStates.waiting_for_code

        await admin_ranked.admin_ranked_cosmetic_create_code(_message(admin_telegram_id, "smoke-ranked-title"), state)
        await admin_ranked.admin_ranked_cosmetic_create_title(_message(admin_telegram_id, "Smoke Title"), state)
        await admin_ranked.admin_ranked_cosmetic_create_rarity(_message(admin_telegram_id, "Epic"), state)
        await admin_ranked.admin_ranked_cosmetic_create_badge_text(_message(admin_telegram_id, "THE GREATEST"), state)

        assert await state.get_state() is None

        from app.services import war2_cosmetics

        items = await war2_cosmetics.list_cosmetic_items(type="TITLE")
        assert any(item.code == "smoke-ranked-title" and item.badge_text == "THE GREATEST" for item in items)
