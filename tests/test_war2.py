"""CLAN WAR 2.0: сезон/билеты, подбор соперника, War Roulette, Draft Pool/Snake Draft,
CLONE_WAR/SALARY_WAR/WILD_CARD, паки Legends, косметика (FRAME/BACKGROUND/NICK_BADGE),
рендер. См. docs/CLAN_WAR_2_SPEC.md.

Использует стандартную фикстуру stronghold_db (общая: monkeypatch'ит DATABASE_PATH и
вызывает init_database(), поэтому сид CLAN WAR 2.0 уже применён в каждом тесте)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.database.db import get_connection
from app.services import war2_cosmetics, war2_core, war2_draft, war2_modes, war2_roster
from app.services.war2_common import War2Error
from app.services.war2_seed import COLLECTION_CODE as LEGENDS_COLLECTION_CODE
from tests.conftest import create_test_user


# ---------------------------------------------------------------------------
# Тестовые хелперы: клан + базовый пул карт (в проде — реальный контент админов,
# в свежей тестовой БД коллекция free-cards пуста, поэтому наполняем её сами, как
# делает conftest.py для creator_tournaments/stronghold тестов).
# ---------------------------------------------------------------------------

async def _make_clan(name: str, leader_user_id: int) -> int:
    """Создаёт клан и сразу добавляет лидера в war2_clan_roster (start_war2_match
    теперь требует членство в ростере — раздел ТЗ "Clan size: 5 игроков")."""
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO clans (name, created_by_user_id) VALUES (?, ?)", (name, leader_user_id)
        )
        clan_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, 'leader')",
            (clan_id, leader_user_id),
        )
        connection.execute(
            "INSERT INTO war2_clan_roster (clan_id, user_id, added_by_user_id) VALUES (?, ?, ?)",
            (clan_id, leader_user_id, leader_user_id),
        )
        connection.commit()
    return clan_id


async def _join_clan(clan_id: int, user_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, 'member')",
            (clan_id, user_id),
        )
        connection.commit()


_FILLER_SEQ = 0


async def _seed_base_pool(min_g: int = 5, min_d: int = 10, min_f: int = 20, ovr_92_99_each: int = 3) -> None:
    """Наполняет 'free-cards' (BASE_COLLECTION, is_exclusive=0) достаточным количеством
    карт для Draft Pool (3G/6D/15F) и Clone War (92-99 OVR)."""
    global _FILLER_SEQ
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])

        def _insert(position: str, overall: int) -> None:
            global _FILLER_SEQ
            _FILLER_SEQ += 1
            key = f"war2-filler-{position.lower()}-{_FILLER_SEQ}"
            connection.execute(
                """
                INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
                VALUES (?, ?, ?, ?, 'Test Team', 'Test Country', ?, 'Common', 'assets/uploads/test.png', ?, 1)
                """,
                (key.title(), key, position, overall, collection_id, overall * 100),
            )

        for _ in range(min_g):
            _insert("G", 70)
        for _ in range(min_d):
            _insert("D", 70)
        for _ in range(min_f):
            _insert("F", 70)
        # запас в диапазоне 92-99 для Clone War, по всем трём позициям
        for overall in (92, 94, 96, 98, 99):
            for position in ("F", "D", "G"):
                for _ in range(ovr_92_99_each):
                    _insert(position, overall)
        connection.commit()


async def _play_full_draft(match_id: int) -> None:
    """Проходит весь snake draft: игрок выбирает первую доступную карту пула на каждом
    своём ходу, соперник добирается auto_pick_for_opponent — до 6 карт с каждой стороны (3F/2D/1G)."""
    for _ in range(12):
        state = await war2_draft.get_draft_state(match_id)
        if state["is_complete"]:
            return
        if state["current_picker"] == "user":
            allowed = war2_draft.allowed_remaining_for_picker(state, "user")
            card_id = int(allowed[0]["id"])
            await war2_draft.record_pick(match_id, "user", card_id)
        else:
            await war2_draft.auto_pick_for_opponent(match_id)


# ---------------------------------------------------------------------------
# 1. Билеты
# ---------------------------------------------------------------------------

async def test_tickets_exhaust_after_five_and_reset_next_day(stronghold_db, monkeypatch):
    user_id = await create_test_user("war2-ticket-user")
    assert await war2_core.get_remaining_tickets(user_id) == 5

    with get_connection() as connection:
        for _ in range(5):
            await war2_core.spend_ticket(connection, user_id)
        connection.commit()

    assert await war2_core.get_remaining_tickets(user_id) == 0

    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    # war2_core делает `from app.services.quests import get_daily_period_key` — патчим
    # именно связанное в war2_core имя, а не исходный модуль (иначе monkeypatch не
    # увидит уже импортированную ссылку).
    monkeypatch.setattr(
        war2_core, "get_daily_period_key", lambda: tomorrow.strftime("%Y-%m-%d")
    )
    assert await war2_core.get_remaining_tickets(user_id) == 5


# ---------------------------------------------------------------------------
# 2. Draft Pool: квоты позиций + только BASE_COLLECTION
# ---------------------------------------------------------------------------

async def test_generate_draft_pool_position_quotas_and_base_collection_only(stronghold_db):
    await _seed_base_pool()
    user_id = await create_test_user("war2-pool-user")
    clan_id = await _make_clan("Pool Clan", user_id)

    start = await war2_core.start_war2_match(user_id)
    pool = await war2_draft.generate_draft_pool(start.match_id)

    assert len(pool) == war2_draft.POOL_SIZE == 24
    positions = [row["position"] for row in pool]
    assert positions.count("G") == 3
    assert positions.count("D") == 6
    assert positions.count("F") == 15

    with get_connection() as connection:
        legends_id = connection.execute(
            "SELECT id FROM collections WHERE code = ?", (LEGENDS_COLLECTION_CODE,)
        ).fetchone()["id"]
        stronghold_id = connection.execute(
            "SELECT id FROM collections WHERE code = 'the_stronghold'"
        ).fetchone()["id"]
    card_ids = [int(row["id"]) for row in pool]
    with get_connection() as connection:
        placeholders = ",".join("?" for _ in card_ids)
        collection_ids = {
            row["collection_id"]
            for row in connection.execute(
                f"SELECT collection_id FROM cards WHERE id IN ({placeholders})", card_ids
            ).fetchall()
        }
    assert legends_id not in collection_ids
    assert stronghold_id not in collection_ids


# ---------------------------------------------------------------------------
# 3. Snake draft: порядок, без повторов
# ---------------------------------------------------------------------------

async def test_snake_draft_alternates_and_rejects_double_pick(stronghold_db):
    await _seed_base_pool()
    user_id = await create_test_user("war2-draft-user")
    await _make_clan("Draft Clan", user_id)

    start = await war2_core.start_war2_match(user_id)
    await war2_draft.generate_draft_pool(start.match_id)
    await _play_full_draft(start.match_id)

    with get_connection() as connection:
        picks = connection.execute(
            "SELECT round_number, pick_order, picker, card_id FROM war2_draft_picks WHERE match_id = ? ORDER BY pick_order",
            (start.match_id,),
        ).fetchall()

    assert len(picks) == 12
    assert [p["picker"] for p in picks] == [
        "user", "opponent", "opponent", "user", "user", "opponent",
        "opponent", "user", "user", "opponent", "opponent", "user",
    ]
    card_ids = [p["card_id"] for p in picks]
    assert len(set(card_ids)) == 12  # без повторов

    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is True

    with pytest.raises(War2Error):
        await war2_draft.record_pick(start.match_id, "user", picks[0]["card_id"])


# ---------------------------------------------------------------------------
# 4. CLONE_WAR: одинаковый состав, без пула/пиков
# ---------------------------------------------------------------------------

async def test_clone_war_builds_identical_roster_both_sides(stronghold_db):
    await _seed_base_pool()
    card_ids = await war2_modes.build_clone_war_lineup()

    assert len(card_ids) == war2_modes.CLONE_WAR_ROSTER_SIZE == 6
    with get_connection() as connection:
        placeholders = ",".join("?" for _ in card_ids)
        rows = connection.execute(
            f"SELECT overall, collection_id FROM cards WHERE id IN ({placeholders})", card_ids
        ).fetchall()
        legends_id = connection.execute(
            "SELECT id FROM collections WHERE code = ?", (LEGENDS_COLLECTION_CODE,)
        ).fetchone()["id"]

    for row in rows:
        assert 92 <= int(row["overall"]) <= 99
        assert row["collection_id"] != legends_id

    user_roster = await war2_draft.build_ephemeral_lineup(card_ids)
    opponent_roster = await war2_draft.build_ephemeral_lineup(card_ids)
    assert [c.card_id for c in user_roster] == [c.card_id for c in opponent_roster]
    assert {pos: sum(1 for c in user_roster if c.position == pos) for pos in ("F", "D", "G")} == {"F": 3, "D": 2, "G": 1}


# ---------------------------------------------------------------------------
# 5. SALARY_WAR: блокировка при превышении лимита
# ---------------------------------------------------------------------------

async def test_salary_war_blocks_over_cap_roster(stronghold_db):
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])
        expensive_ids = []
        for i in range(5):
            cursor = connection.execute(
                """
                INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
                VALUES (?, ?, 'F', 90, 'T', 'C', ?, 'Icon', 'x.png', 20000, 1)
                """,
                (f"Pricey {i}", f"war2-pricey-{i}", collection_id),
            )
            expensive_ids.append(int(cursor.lastrowid))
        connection.commit()

    with pytest.raises(War2Error) as exc_info:
        await war2_modes.validate_salary_cap(expensive_ids)
    assert exc_info.value.code == "SALARY_CAP_EXCEEDED"

    cheap_ids = expensive_ids[:2]  # 2 * 20000 = 40000 < 50000 cap
    await war2_modes.validate_salary_cap(cheap_ids)  # не должно бросить


# ---------------------------------------------------------------------------
# 6. WILD_CARD: одна замена, использование фиксируется
# ---------------------------------------------------------------------------

async def test_wild_card_single_use_enforced(stronghold_db, monkeypatch):
    await _seed_base_pool()
    user_id = await create_test_user("war2-wildcard-user")
    await _make_clan("Wildcard Clan", user_id)

    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES ('Own Card', 'war2-own-card', 'F', 95, 'T', 'C', ?, 'Rare', 'x.png', 100, 1)
            """,
            (collection["id"],),
        )
        card_id = int(cursor.lastrowid)
        user_card_cursor = connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')",
            (user_id, card_id),
        )
        own_user_card_id = int(user_card_cursor.lastrowid)
        connection.commit()

    # заставим roulette дать WILD_CARD детерминированно — war2_core делает
    # `from app.services.war2_modes import roll_active_mode`, поэтому патчим связанное
    # имя прямо в war2_core, а не в исходном war2_modes.
    async def _force_wild_card():
        return war2_modes.WAR2_MODE_REGISTRY["WILD_CARD"]
    monkeypatch.setattr(war2_core, "roll_active_mode", _force_wild_card)

    start = await war2_core.start_war2_match(user_id)

    assert start.mode.code == "WILD_CARD"
    await war2_draft.generate_draft_pool(start.match_id)
    await _play_full_draft(start.match_id)

    picks_before = await war2_draft.finalize_lineup_for(start.match_id, "user")
    replace_card_id = next(card.card_id for card in picks_before if card.position == "F")

    new_roster, replaced_id = await war2_modes.apply_wild_card_replacement(
        start.match_id, user_id, replace_card_id, own_user_card_id
    )
    assert replaced_id == replace_card_id
    assert any(card.card_id == card_id for card in new_roster)
    assert len(new_roster) == 6

    with get_connection() as connection:
        row = connection.execute(
            "SELECT used_wild_card, wild_card_replaced_card_id, wild_card_user_card_id FROM war2_matches WHERE id = ?",
            (start.match_id,),
        ).fetchone()
    assert row["used_wild_card"] == 1
    assert row["wild_card_replaced_card_id"] == replace_card_id
    assert row["wild_card_user_card_id"] == own_user_card_id

    # оригинальные драфт-пики не тронуты
    with get_connection() as connection:
        pick_count = connection.execute(
            "SELECT COUNT(*) n FROM war2_draft_picks WHERE match_id = ? AND picker = 'user'", (start.match_id,)
        ).fetchone()["n"]
    assert pick_count == 6

    with pytest.raises(War2Error) as exc_info:
        await war2_modes.apply_wild_card_replacement(start.match_id, user_id, picks_before[1].card_id, own_user_card_id)
    assert exc_info.value.code == "WILD_CARD_ALREADY_USED"


# ---------------------------------------------------------------------------
# 7. Полный матч: результат пишется только в war2_*, users/clans не трогаются
# ---------------------------------------------------------------------------

async def test_full_match_flow_completes_and_does_not_touch_ladder_or_arena_tables(stronghold_db):
    await _seed_base_pool()
    user_id = await create_test_user("war2-full-user")
    clan_id = await _make_clan("Full Clan", user_id)
    opponent_id = await create_test_user("war2-full-opponent")
    await _make_clan("Enemy Clan", opponent_id)

    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO war2_seasons (season_number, status, starts_at, ends_at) VALUES (1, 'active', datetime('now'), datetime('now', '+28 days'))"
        )
        connection.commit()

    with get_connection() as connection:
        before_user = dict(connection.execute("SELECT matches_played, wins, losses, rating_points FROM users WHERE id = ?", (user_id,)).fetchone())
        before_clan = dict(connection.execute("SELECT rating_points, wins FROM clans WHERE id = ?", (clan_id,)).fetchone())

    start = await war2_core.start_war2_match(user_id)
    if start.mode.uses_draft:
        await war2_draft.generate_draft_pool(start.match_id)
        await _play_full_draft(start.match_id)
        user_roster = await war2_draft.finalize_lineup_for(start.match_id, "user")
        opponent_roster = await war2_draft.finalize_lineup_for(start.match_id, "opponent")
    else:
        card_ids = await war2_modes.build_clone_war_lineup()
        user_roster = await war2_draft.build_ephemeral_lineup(card_ids)
        opponent_roster = await war2_draft.build_ephemeral_lineup(card_ids)

    result = await war2_core.record_war2_match_result(
        match_id=start.match_id,
        user_id=user_id,
        user_clan_id=clan_id,
        opponent_clan_id=None,
        user_cards=user_roster,
        opponent_cards=opponent_roster,
        opponent_name=start.opponent.name,
    )

    assert result.result in ("win", "loss")

    with get_connection() as connection:
        match_row = connection.execute("SELECT status FROM war2_matches WHERE id = ?", (start.match_id,)).fetchone()
        stats_row = connection.execute(
            "SELECT matches_played FROM war2_player_stats WHERE user_id = ?", (user_id,)
        ).fetchone()
        tickets_row = connection.execute(
            "SELECT tickets_used FROM war2_daily_tickets WHERE user_id = ?", (user_id,)
        ).fetchone()
        after_user = dict(connection.execute("SELECT matches_played, wins, losses, rating_points FROM users WHERE id = ?", (user_id,)).fetchone())
        after_clan = dict(connection.execute("SELECT rating_points, wins FROM clans WHERE id = ?", (clan_id,)).fetchone())

    assert match_row["status"] == "completed"
    assert stats_row is not None and stats_row["matches_played"] == 1
    assert tickets_row is not None and tickets_row["tickets_used"] == 1
    assert after_user == before_user  # лестница обычных матчей не тронута
    assert after_clan == before_clan  # рейтинг старой системы арен не тронут


# ---------------------------------------------------------------------------
# 8. Паки Legends: выдают только карты коллекции Clan War Legends
# ---------------------------------------------------------------------------

async def test_legends_packs_grant_only_legends_cards(stronghold_db):
    from app.services.packs import open_user_pack

    user_id = await create_test_user("war2-pack-user")
    with get_connection() as connection:
        legends_id = connection.execute(
            "SELECT id FROM collections WHERE code = ?", (LEGENDS_COLLECTION_CODE,)
        ).fetchone()["id"]

    for code, expected_count in (("clan_war2_pack_level_1", 1), ("clan_war2_pack_level_2", 2), ("clan_war2_pack_level_3", 3)):
        with get_connection() as connection:
            pack_id = connection.execute("SELECT id FROM packs WHERE code = ?", (code,)).fetchone()["id"]
            connection.execute(
                "INSERT INTO user_packs (user_id, pack_id, quantity) VALUES (?, ?, 1) ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + 1",
                (user_id, pack_id),
            )
            connection.commit()

        result, error = await open_user_pack(user_id, int(pack_id))
        assert error is None, error
        assert len(result.rewards) == expected_count

        with get_connection() as connection:
            for reward in result.rewards:
                collection_id = connection.execute(
                    "SELECT collection_id FROM cards WHERE id = ?", (reward.card_id,)
                ).fetchone()["collection_id"]
                assert collection_id == legends_id


# ---------------------------------------------------------------------------
# 9. Косметика: grant -> equip -> get_equipped_*, вытеснение того же типа
# ---------------------------------------------------------------------------

async def test_cosmetics_grant_equip_and_unequip_sibling(stronghold_db):
    user_id = await create_test_user("war2-cosmetics-user")

    frame_id = await war2_cosmetics.create_cosmetic_item(
        type="FRAME", code="frame-gold", title="Golden Frame", image_path="assets/uploads/war2_frames/gold.png"
    )
    badge_id = await war2_cosmetics.create_cosmetic_item(
        type="NICK_BADGE", code="badge-goat", title="GOAT Badge", badge_text="GOAT"
    )

    owned_frame_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame_id)
    owned_badge_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, badge_id)

    await war2_cosmetics.equip_cosmetic(user_id, owned_frame_id)
    await war2_cosmetics.equip_cosmetic(user_id, owned_badge_id)

    assert await war2_cosmetics.get_equipped_frame_path(user_id) == "assets/uploads/war2_frames/gold.png"
    assert await war2_cosmetics.get_equipped_badge_text(user_id) == "GOAT"
    assert war2_cosmetics.format_nickname_with_badge("Hudson", "GOAT") == "Hudson [GOAT]"

    # второй FRAME того же типа вытесняет первый
    frame2_id = await war2_cosmetics.create_cosmetic_item(type="FRAME", code="frame-silver", title="Silver Frame", image_path="silver.png")
    owned_frame2_id = await war2_cosmetics.grant_cosmetic_to_user(user_id, frame2_id)
    await war2_cosmetics.equip_cosmetic(user_id, owned_frame2_id)

    assert await war2_cosmetics.get_equipped_frame_path(user_id) == "silver.png"
    items = await war2_cosmetics.get_user_cosmetics_page(user_id, "FRAME")
    equipped = [item for item in items if item.equipped]
    assert len(equipped) == 1
    assert equipped[0].id == owned_frame2_id


# ---------------------------------------------------------------------------
# 11. Сезон: длительность, не удаляет статистику при завершении
# ---------------------------------------------------------------------------

async def test_season_lifecycle_keeps_stats_on_end(stronghold_db):
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO war2_seasons (season_number, status, starts_at, ends_at) VALUES (1, 'active', datetime('now'), datetime('now', '+28 days'))"
        )
        season_id = int(cursor.lastrowid)
        connection.commit()

    active = await war2_core.get_active_season()
    assert active is not None and active.id == season_id

    user_id = await create_test_user("war2-season-user")
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO war2_player_stats (season_id, user_id, rating_points, matches_played) VALUES (?, ?, 1200, 3)",
            (season_id, user_id),
        )
        connection.execute("UPDATE war2_seasons SET status = 'ended' WHERE id = ?", (season_id,))
        connection.commit()

    assert await war2_core.get_active_season() is None
    with get_connection() as connection:
        stats = connection.execute("SELECT matches_played FROM war2_player_stats WHERE season_id = ? AND user_id = ?", (season_id, user_id)).fetchone()
    assert stats is not None and stats["matches_played"] == 3


# ---------------------------------------------------------------------------
# 10. Рендер: regression (без новых аргументов — как раньше) + war2 lineup + wildcard
# ---------------------------------------------------------------------------

async def test_render_lineup_image_unchanged_without_new_args(stronghold_db):
    from app.services import renders
    from app.services.lineup import get_lineup_overview
    from tests.conftest import give_and_slot_card

    user_id = await create_test_user("war2-render-ladder-user")
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])
        card_ids = {}
        for slot, position in [("G", "G"), ("D1", "D"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]:
            cursor = connection.execute(
                "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES (?, ?, ?, 70, 'T', 'C', ?, 'Common', 'x.png', 100, 1)",
                (f"Render {slot}", f"war2-render-{slot.lower()}", position, collection_id),
            )
            card_ids[slot] = int(cursor.lastrowid)
        connection.commit()
    for slot, card_id in card_ids.items():
        await give_and_slot_card(user_id, card_id, slot)

    overview = await get_lineup_overview(user_id)

    output_path = renders.render_lineup_image(overview, user_id)
    assert output_path.exists()
    assert output_path.stat().st_size > 0


async def test_render_war2_lineup_image_handles_wildcard_roster(stronghold_db):
    from app.services import renders

    await _seed_base_pool()
    card_ids = await war2_modes.build_clone_war_lineup()
    roster = await war2_draft.build_ephemeral_lineup(card_ids)
    assert len(roster) == 5

    output_path = renders.render_war2_lineup_image(
        roster, user_id=1, average_overall=95, title="CLAN WAR 2.0", nickname="Hudson", badge_text="GOAT"
    )
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    # с background/frame override на несуществующий путь — не должно падать (fallback)
    output_path_2 = renders.render_war2_lineup_image(
        roster, user_id=1, average_overall=95,
        background_override_path="assets/uploads/war2_backgrounds/does_not_exist.png",
        frame_override_path="assets/uploads/war2_frames/does_not_exist.png",
    )
    assert output_path_2.exists()


# ---------------------------------------------------------------------------
# 12. Ростер клана (раздел ТЗ "Clan size: 5 игроков")
# ---------------------------------------------------------------------------

async def test_roster_add_remove_and_size_limit(stronghold_db):
    leader_id = await create_test_user("war2-roster-leader")
    clan_id = await _make_clan("Roster Clan", leader_id)  # лидер уже в ростере (1/5)

    member_ids = []
    for i in range(5):
        uid = await create_test_user(f"war2-roster-member-{i}")
        await _join_clan(clan_id, uid)
        member_ids.append(uid)

    # добираем ростер до лимита (лидер уже там -> ещё 4 штатно, 5-й должен упасть)
    for uid in member_ids[:4]:
        await war2_roster.add_roster_member(clan_id, uid, leader_id)

    roster = await war2_roster.get_clan_roster(clan_id)
    assert len(roster) == 5

    with pytest.raises(War2Error) as exc_info:
        await war2_roster.add_roster_member(clan_id, member_ids[4], leader_id)
    assert exc_info.value.code == "ROSTER_FULL"

    await war2_roster.remove_roster_member(clan_id, member_ids[0], leader_id)
    assert len(await war2_roster.get_clan_roster(clan_id)) == 4
    await war2_roster.add_roster_member(clan_id, member_ids[4], leader_id)
    assert len(await war2_roster.get_clan_roster(clan_id)) == 5


async def test_roster_requires_manager_role(stronghold_db):
    leader_id = await create_test_user("war2-roster-nm-leader")
    clan_id = await _make_clan("NM Clan", leader_id)
    plain_member_id = await create_test_user("war2-roster-nm-member")
    await _join_clan(clan_id, plain_member_id)
    target_id = await create_test_user("war2-roster-nm-target")
    await _join_clan(clan_id, target_id)

    with pytest.raises(War2Error) as exc_info:
        await war2_roster.add_roster_member(clan_id, target_id, plain_member_id)
    assert exc_info.value.code == "ROSTER_NOT_MANAGER"


async def test_roster_rejects_non_clan_member(stronghold_db):
    leader_id = await create_test_user("war2-roster-outsider-leader")
    clan_id = await _make_clan("Outsider Clan", leader_id)
    outsider_id = await create_test_user("war2-roster-outsider")

    with pytest.raises(War2Error) as exc_info:
        await war2_roster.add_roster_member(clan_id, outsider_id, leader_id)
    assert exc_info.value.code == "ROSTER_NOT_CLAN_MEMBER"


async def test_start_match_blocked_without_clan_or_roster(stronghold_db):
    await _seed_base_pool()
    no_clan_user = await create_test_user("war2-no-clan")
    with pytest.raises(War2Error) as exc_info:
        await war2_core.start_war2_match(no_clan_user)
    assert exc_info.value.code == "NO_CLAN"

    leader_id = await create_test_user("war2-roster-empty-leader")
    with get_connection() as connection:
        cursor = connection.execute("INSERT INTO clans (name, created_by_user_id) VALUES ('Empty Roster Clan', ?)", (leader_id,))
        clan_id = int(cursor.lastrowid)
        connection.execute("INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, 'leader')", (clan_id, leader_id))
        connection.commit()
    # клан создан БЕЗ автоматического добавления в war2_clan_roster (в отличие от _make_clan)
    with pytest.raises(War2Error) as exc_info:
        await war2_core.start_war2_match(leader_id)
    assert exc_info.value.code == "ROSTER_NOT_SET"

    not_rostered_member = await create_test_user("war2-not-rostered")
    await _join_clan(clan_id, not_rostered_member)
    await war2_roster.add_roster_member(clan_id, leader_id, leader_id)
    with pytest.raises(War2Error) as exc_info:
        await war2_core.start_war2_match(not_rostered_member)
    assert exc_info.value.code == "NOT_ON_ROSTER"


async def test_opponent_search_only_considers_rostered_players(stronghold_db):
    await _seed_base_pool()
    user_id = await create_test_user("war2-oppo-search-user")
    clan_id = await _make_clan("Oppo Search Clan", user_id)

    other_clan_leader = await create_test_user("war2-oppo-search-other-leader")
    other_clan_id = await _make_clan("Oppo Search Other Clan", other_clan_leader)
    not_rostered = await create_test_user("war2-oppo-search-not-rostered")
    await _join_clan(other_clan_id, not_rostered)  # в клане, но НЕ в ростере

    opponent = await war2_core.find_war2_opponent(user_id)
    assert opponent.type == "player"
    assert opponent.user_id == other_clan_leader  # единственный рострированный в другом клане


# ---------------------------------------------------------------------------
# 13. SALARY_WAR: пересдача последнего раунда вместо отмены всего матча
# ---------------------------------------------------------------------------

async def test_salary_war_redo_last_round_lets_player_repick(stronghold_db, monkeypatch):
    await _seed_base_pool()
    user_id = await create_test_user("war2-redo-user")
    await _make_clan("Redo Clan", user_id)

    async def _force_salary_war():
        return war2_modes.WAR2_MODE_REGISTRY["SALARY_WAR"]

    monkeypatch.setattr(war2_core, "roll_active_mode", _force_salary_war)
    start = await war2_core.start_war2_match(user_id)
    assert start.mode.code == "SALARY_WAR"

    for _ in range(6):
        state = await war2_draft.get_draft_state(start.match_id)
        if state["is_complete"]:
            break
        card_id = int(war2_draft.allowed_remaining_for_picker(state, "user")[0]["id"])
        await war2_draft.record_pick(start.match_id, "user", card_id)
        state2 = await war2_draft.get_draft_state(start.match_id)
        if not state2["is_complete"] and state2["current_picker"] == "opponent":
            await war2_draft.auto_pick_for_opponent(start.match_id)
            state3 = await war2_draft.get_draft_state(start.match_id)
            if not state3["is_complete"] and state3["current_picker"] == "opponent":
                await war2_draft.auto_pick_for_opponent(start.match_id)

    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is True

    with get_connection() as connection:
        picks_before = connection.execute(
            "SELECT id FROM war2_draft_picks WHERE match_id = ? AND round_number = 6", (start.match_id,)
        ).fetchall()
    assert len(picks_before) == 2  # user + opponent, раунд 6

    redone_round = await war2_draft.redo_last_round(start.match_id)
    assert redone_round == 6

    with get_connection() as connection:
        picks_after = connection.execute(
            "SELECT id FROM war2_draft_picks WHERE match_id = ? AND round_number = 6", (start.match_id,)
        ).fetchall()
    assert len(picks_after) == 0

    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is False
    assert state["current_round"] == 6
    assert state["current_picker"] == "user"

    # доигрываем заново
    card_id = int(war2_draft.allowed_remaining_for_picker(state, "user")[0]["id"])
    await war2_draft.record_pick(start.match_id, "user", card_id)
    await war2_draft.auto_pick_for_opponent(start.match_id)
    state = await war2_draft.get_draft_state(start.match_id)
    assert state["is_complete"] is True
