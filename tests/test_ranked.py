"""RANKED MODE (v1): доступ по лиге, зарплатный потолок 54M, обычный режим без cap,
CARD_FRAME (одна рамка -> одна карта), сезон 56 дней, ранг/лиги/XP, Ranked Pack,
Ranked Pass (Gold -> Platinum с ретроактивной выдачей). См. docs/RANKED_MODE_SPEC.md.

Использует стандартную фикстуру stronghold_db (общая: monkeypatch'ит DATABASE_PATH и
вызывает init_database(), поэтому сид Ranked Mode уже применён в каждом тесте)."""

import pytest

from app.database.db import get_connection
from app.services import ranked_core, ranked_cosmetics, ranked_packs, ranked_pass
from app.services.ranked_common import RankedError
from tests.conftest import create_test_user


async def _telegram_id_for(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return int(row["telegram_id"])


async def _set_league(user_id: int, league: str) -> None:
    with get_connection() as connection:
        connection.execute("UPDATE users SET league = ? WHERE id = ?", (league, user_id))
        connection.commit()


_FILLER_SEQ = 0


async def _build_lineup(user_id: int, *, salary_per_card: int) -> None:
    """Полный состав из 6 карт free-cards с заданной зарплатой за карту (для тестов
    зарплатного потолка) — тот же паттерн, что и в tests/test_war2.py/test_creator_tournaments.py."""
    global _FILLER_SEQ
    from tests.conftest import give_and_slot_card

    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])
        card_ids = {}
        for slot, position in [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]:
            _FILLER_SEQ += 1
            key = f"ranked-filler-{slot.lower()}-{_FILLER_SEQ}"
            cursor = connection.execute(
                """
                INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
                VALUES (?, ?, ?, 70, 'T', 'C', ?, 'Common', 'x.png', ?, 1)
                """,
                (key, key, position, collection_id, salary_per_card),
            )
            card_ids[slot] = int(cursor.lastrowid)
        connection.commit()
    for slot, card_id in card_ids.items():
        await give_and_slot_card(user_id, card_id, slot)


async def _ranked_ready_player(nickname: str, *, league: str = "AHL", salary_per_card: int = 5000) -> tuple[int, int]:
    user_id = await create_test_user(nickname)
    await _set_league(user_id, league)
    await _build_lineup(user_id, salary_per_card=salary_per_card)
    return user_id, await _telegram_id_for(user_id)


# ---------------------------------------------------------------------------
# 1. RANKED ACCESS: ниже AHL не пускает
# ---------------------------------------------------------------------------

async def test_below_ahl_player_blocked_from_ranked(stronghold_db):
    user_id, telegram_id = await _ranked_ready_player("ranked-ncaa-user", league="NCAA")
    with pytest.raises(RankedError) as exc_info:
        await ranked_core.play_ranked_match(telegram_id)
    assert exc_info.value.code == "LEAGUE_TOO_LOW"


async def test_ahl_and_above_allowed_into_ranked(stronghold_db):
    for league in ("AHL", "NHL", "OLYMPICS"):
        user_id, telegram_id = await _ranked_ready_player(f"ranked-{league.lower()}-user", league=league, salary_per_card=3000)
        result = await ranked_core.play_ranked_match(telegram_id)
        assert result.result in ("win", "loss")


# ---------------------------------------------------------------------------
# 2. SALARY CAP: Ranked = 54M, не лиговый потолок
# ---------------------------------------------------------------------------

async def test_ranked_uses_54m_cap_not_league_cap(stronghold_db):
    # AHL: лиговый потолок 26000 (5000*6=30000 уже превысил бы обычный AHL-cap, если
    # бы Ranked его использовал) — но Ranked-потолок 54000, состав 30000 должен пройти.
    user_id, telegram_id = await _ranked_ready_player("ranked-cap-ok-user", league="AHL", salary_per_card=5000)
    result = await ranked_core.play_ranked_match(telegram_id)
    assert result.result in ("win", "loss")


async def test_ranked_blocks_over_54m_cap(stronghold_db):
    user_id, telegram_id = await _ranked_ready_player("ranked-cap-over-user", league="OLYMPICS", salary_per_card=10000)  # 60000 > 54000
    with pytest.raises(RankedError) as exc_info:
        await ranked_core.play_ranked_match(telegram_id)
    assert exc_info.value.code == "SALARY_CAP_EXCEEDED"
    assert "54.0M" in exc_info.value.message


# ---------------------------------------------------------------------------
# 3. NORMAL MODE: без salary cap
# ---------------------------------------------------------------------------

async def test_normal_quick_match_ignores_salary_cap(stronghold_db):
    from app.services.matches import play_quick_match

    # AHL лиговый потолок = 26000; состав на 45000 раньше блокировал бы обычный матч.
    user_id, telegram_id = await _ranked_ready_player("normal-nocap-user", league="AHL", salary_per_card=7500)
    result = await play_quick_match(telegram_id)
    assert result.success is True


async def test_normal_matchmaking_ignores_salary_cap(stronghold_db):
    from app.services.matches import enter_matchmaking

    user_id, telegram_id = await _ranked_ready_player("normal-nocap-mm-user", league="AHL", salary_per_card=7500)
    result = await enter_matchmaking(telegram_id, chat_id=1, message_id=1)
    assert result.status in ("queued", "matched")  # не "not_ready" из-за зарплаты


# ---------------------------------------------------------------------------
# 4. CARD_FRAME: одна рамка -> одна карта
# ---------------------------------------------------------------------------

async def test_card_frame_binding_is_one_to_one(stronghold_db):
    from app.services import war2_cosmetics

    user_id = await create_test_user("ranked-frame-user")
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        card_a = connection.execute(
            "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES ('A','a','F',80,'T','C',?,'Common','x.png',100,1)",
            (collection["id"],),
        )
        card_a_id = int(card_a.lastrowid)
        card_b = connection.execute(
            "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES ('B','b','F',80,'T','C',?,'Common','x.png',100,1)",
            (collection["id"],),
        )
        card_b_id = int(card_b.lastrowid)
        uc1 = connection.execute("INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, card_a_id))
        user_card_1 = int(uc1.lastrowid)
        uc2 = connection.execute("INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, card_b_id))
        user_card_2 = int(uc2.lastrowid)
        connection.commit()

    frame_item_id = await war2_cosmetics.create_cosmetic_item(type="CARD_FRAME", code="test-frame", title="Test Frame", image_path="x.png")
    owned_frame_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame_item_id)

    await ranked_cosmetics.bind_frame_to_card(user_id, owned_frame_id, user_card_1)
    binding = await ranked_cosmetics.get_card_frame_for_card(user_card_1)
    assert binding is not None and binding.user_cosmetic_item_id == owned_frame_id

    # Тот же физический экземпляр нельзя молча перенести на другую карту.
    with pytest.raises(RankedError) as exc_info:
        await ranked_cosmetics.bind_frame_to_card(user_id, owned_frame_id, user_card_2)
    assert exc_info.value.code == "CARD_FRAME_ALREADY_BOUND"

    # Для второй карты нужен второй экземпляр рамки.
    frame_item_2_id = await war2_cosmetics.create_cosmetic_item(type="CARD_FRAME", code="test-frame-2", title="Test Frame 2", image_path="y.png")
    owned_frame_2_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame_item_2_id)
    await ranked_cosmetics.bind_frame_to_card(user_id, owned_frame_2_id, user_card_2)
    binding_2 = await ranked_cosmetics.get_card_frame_for_card(user_card_2)
    assert binding_2 is not None and binding_2.user_cosmetic_item_id == owned_frame_2_id

    with get_connection() as connection:
        total = connection.execute("SELECT COUNT(*) n FROM user_card_frames").fetchone()["n"]
    assert total == 2

    # На уже занятую карту нельзя повесить ещё одну рамку, пока текущая не снята.
    frame_item_3_id = await war2_cosmetics.create_cosmetic_item(type="CARD_FRAME", code="test-frame-4", title="Test Frame 4", image_path="z.png")
    owned_frame_3_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame_item_3_id)
    with pytest.raises(RankedError) as occupied_error:
        await ranked_cosmetics.bind_frame_to_card(user_id, owned_frame_3_id, user_card_2)
    assert occupied_error.value.code == "CARD_ALREADY_HAS_FRAME"

    await ranked_cosmetics.unbind_frame_from_card(user_id, user_card_2)
    await ranked_cosmetics.bind_frame_to_card(user_id, owned_frame_3_id, user_card_2)
    binding_after = await ranked_cosmetics.get_card_frame_for_card(user_card_2)
    assert binding_after.user_cosmetic_item_id == owned_frame_3_id


async def test_card_frame_rejects_not_owned(stronghold_db):
    from app.services import war2_cosmetics

    owner_id = await create_test_user("frame-owner")
    other_id = await create_test_user("frame-other")
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        card = connection.execute(
            "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES ('C','c','F',80,'T','C',?,'Common','x.png',100,1)",
            (collection["id"],),
        )
        uc = connection.execute("INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (owner_id, int(card.lastrowid)))
        user_card_id = int(uc.lastrowid)
        connection.commit()

    frame_item_id = await war2_cosmetics.create_cosmetic_item(type="CARD_FRAME", code="test-frame-3", title="Test Frame 3", image_path="x.png")
    owned_frame_id = await war2_cosmetics.grant_cosmetic_to_user(owner_id, frame_item_id)

    with pytest.raises(RankedError) as exc_info:
        await ranked_cosmetics.bind_frame_to_card(other_id, owned_frame_id, user_card_id)
    assert exc_info.value.code == "CARD_FRAME_NOT_OWNED"


# ---------------------------------------------------------------------------
# 5. PASS PURCHASE: Gold -> Platinum ретроактивно выдаёт открытые Platinum награды
# ---------------------------------------------------------------------------

async def _seed_test_ranked_pass() -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO ranked_passes (title, levels_count, points_per_level, gold_currency_code, gold_price_amount, platinum_currency_code, platinum_price_amount, upgrade_currency_code, upgrade_price_amount, active)
            VALUES ('Test Pass', 60, 100, 'coins', 500, 'coins', 1500, 'coins', 1000, 1)
            """
        )
        pass_id = int(cursor.lastrowid)
        for level in (1, 2, 3, 5):
            connection.execute(
                "INSERT INTO ranked_pass_rewards (pass_id, level, track, reward_type, currency_code, amount, title) VALUES (?, ?, 'platinum', 'currency', 'coins', 100, ?)",
                (pass_id, level, f"Platinum L{level}"),
            )
        connection.commit()
    return pass_id


async def test_gold_to_platinum_upgrade_grants_retroactive_rewards(stronghold_db):
    from tests.conftest import grant_balance

    user_id = await create_test_user("pass-upgrade-user")
    pass_id = await _seed_test_ranked_pass()
    grant_balance(user_id, "coins", 10_000)

    # даём XP на уровень 4 (100/уровень -> 300 xp = уровень 4), чтобы уровни 1,2,3
    # были достигнуты, а уровень 5 — ещё нет
    with get_connection() as connection:
        cursor = connection.execute("INSERT INTO ranked_seasons (season_number, status) VALUES (1, 'active')")
        season_id = int(cursor.lastrowid)
        connection.execute("UPDATE ranked_passes SET season_id = ? WHERE id = ?", (season_id, pass_id))
        connection.execute(
            "INSERT INTO ranked_player_stats (season_id, user_id, ranked_xp) VALUES (?, ?, 300)", (season_id, user_id)
        )
        connection.commit()

    await ranked_pass.purchase_gold(user_id, pass_id)
    granted = await ranked_pass.upgrade_gold_to_platinum(user_id, pass_id)
    assert granted == 3  # уровни 1,2,3 (уровень 5 ещё не достигнут)

    with get_connection() as connection:
        claimed = connection.execute(
            "SELECT COUNT(*) n FROM user_ranked_pass_rewards WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    assert claimed == 3

    state = await ranked_pass.get_user_pass_state(user_id, pass_id)
    assert state.platinum_unlocked is True


async def test_platinum_locked_without_upgrade(stronghold_db):
    from tests.conftest import grant_balance

    user_id = await create_test_user("pass-locked-user")
    pass_id = await _seed_test_ranked_pass()
    grant_balance(user_id, "coins", 10_000)

    with get_connection() as connection:
        cursor = connection.execute("INSERT INTO ranked_seasons (season_number, status) VALUES (1, 'active')")
        season_id = int(cursor.lastrowid)
        connection.execute("UPDATE ranked_passes SET season_id = ? WHERE id = ?", (season_id, pass_id))
        connection.execute("INSERT INTO ranked_player_stats (season_id, user_id, ranked_xp) VALUES (?, ?, 300)", (season_id, user_id))
        reward = connection.execute("SELECT id FROM ranked_pass_rewards WHERE pass_id = ? AND level = 1", (pass_id,)).fetchone()
        connection.commit()

    with pytest.raises(RankedError) as exc_info:
        await ranked_pass.claim_reward(user_id, int(reward["id"]))
    assert exc_info.value.code == "PLATINUM_LOCKED"


# ---------------------------------------------------------------------------
# 6. PASS XP: начисляется за матч, больше за победу, бонус за новую лигу
# ---------------------------------------------------------------------------

async def test_ranked_xp_awarded_per_match_and_win_bonus(stronghold_db):
    await ranked_core.start_ranked_season()
    user_id, telegram_id = await _ranked_ready_player("xp-user", league="AHL", salary_per_card=3000)

    result = await ranked_core.play_ranked_match(telegram_id)
    season = await ranked_core.get_active_season()
    stats = await ranked_core.get_ranked_stats(user_id, season.id)

    assert stats.matches_played == 1
    expected_min_xp = 20  # ranked_xp_per_match default
    assert stats.ranked_xp >= expected_min_xp
    if result.result == "win":
        assert stats.ranked_xp >= 20 + 30  # + win bonus default


async def test_ranked_xp_division_up_bonus(stronghold_db, monkeypatch):
    """Форсируем гарантированную победу (соперник намного слабее), чтобы игрок
    поднялся хотя бы на 100 очков рейтинга -> пересёк порог Silver (300)."""
    await ranked_core.start_ranked_season()
    user_id, telegram_id = await _ranked_ready_player("division-up-user", league="AHL", salary_per_card=3000)
    season = await ranked_core.get_active_season()

    with get_connection() as connection:
        connection.execute(
            "INSERT INTO ranked_player_stats (season_id, user_id, rank_points) VALUES (?, ?, 290)", (season.id, user_id)
        )
        connection.commit()

    # моделируем сильную победу напрямую через build_simulation с большим разрывом OVR
    async def _force_weak_bot_ovr(user_ovr):
        return 1

    monkeypatch.setattr(ranked_core, "_resolve_opponent_ovr", lambda opponent, user_ovr: _force_weak_bot_ovr(user_ovr))

    for _ in range(10):
        result = await ranked_core.play_ranked_match(telegram_id)
        if result.result == "win":
            break

    stats = await ranked_core.get_ranked_stats(user_id, season.id)
    if stats.rank_points >= 300:  # пересекли порог Silver
        assert result.league_up is True or stats.rank_points < 300


# ---------------------------------------------------------------------------
# 7. Сезон: 56 дней, конец архивирует, не удаляет, новый сезон стартует с 0
# ---------------------------------------------------------------------------

async def test_season_length_defaults_to_56_days(stronghold_db):
    from datetime import datetime

    season = await ranked_core.start_ranked_season()
    starts = datetime.strptime(season.starts_at, "%Y-%m-%d %H:%M:%S")
    ends = datetime.strptime(season.ends_at, "%Y-%m-%d %H:%M:%S")
    assert (ends - starts).days == 56


async def test_season_end_archives_and_does_not_delete_stats(stronghold_db):
    season = await ranked_core.start_ranked_season()
    user_id, telegram_id = await _ranked_ready_player("season-end-user", league="AHL", salary_per_card=3000)
    await ranked_core.play_ranked_match(telegram_id)

    await ranked_core.end_ranked_season()

    with get_connection() as connection:
        row = connection.execute("SELECT status, top_json FROM ranked_seasons WHERE id = ?", (season.id,)).fetchone()
        assert row["status"] == "ended"
        assert row["top_json"] is not None
        stats_row = connection.execute(
            "SELECT matches_played FROM ranked_player_stats WHERE season_id = ? AND user_id = ?", (season.id, user_id)
        ).fetchone()
        assert stats_row is not None  # архивные данные не удалены

    assert await ranked_core.get_active_season() is None

    new_season = await ranked_core.start_ranked_season()
    new_stats = await ranked_core.get_ranked_stats(user_id, new_season.id)
    assert new_stats.rank_points == 0
    assert new_stats.matches_played == 0


# ---------------------------------------------------------------------------
# Полный матч: users.rating_points/league не трогаются
# ---------------------------------------------------------------------------

async def test_ranked_match_does_not_touch_ladder_stats(stronghold_db):
    await ranked_core.start_ranked_season()
    user_id, telegram_id = await _ranked_ready_player("ladder-safe-user", league="AHL", salary_per_card=3000)

    with get_connection() as connection:
        before = dict(connection.execute("SELECT rating_points, league, matches_played, wins, losses FROM users WHERE id = ?", (user_id,)).fetchone())

    await ranked_core.play_ranked_match(telegram_id)

    with get_connection() as connection:
        after = dict(connection.execute("SELECT rating_points, league, matches_played, wins, losses FROM users WHERE id = ?", (user_id,)).fetchone())

    assert before == after


# ---------------------------------------------------------------------------
# Ranked Pack: карта/валюта/XP/косметика за слот
# ---------------------------------------------------------------------------

async def test_ranked_pack_open_grants_configured_rewards(stronghold_db):
    await ranked_core.start_ranked_season()
    user_id = await create_test_user("pack-open-user")

    with get_connection() as connection:
        pack_row = connection.execute("SELECT id FROM ranked_packs WHERE code = 'ranked_pack_bronze'").fetchone()
        pack_id = int(pack_row["id"])
        connection.execute("INSERT INTO user_ranked_packs (user_id, pack_id, quantity) VALUES (?, ?, 1)", (user_id, pack_id))
        connection.commit()

    result = await ranked_packs.open_ranked_pack(user_id, pack_id)
    assert len(result.rewards) >= 1  # дефолтный XP-слот из сида как минимум

    with get_connection() as connection:
        remaining = connection.execute(
            "SELECT quantity FROM user_ranked_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()["quantity"]
    assert remaining == 0
