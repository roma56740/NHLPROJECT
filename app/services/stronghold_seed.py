"""Повторно запускаемый сид контента THE STRONGHOLD.

Вызывается из `app/database/db.py:init_database()` внутри уже открытой транзакции —
не коммитит и не открывает соединение самостоятельно. Идемпотентен: повторный запуск
не создаёт дублей (см. docs/THE_STRONGHOLD_DATABASE.md).
"""

from __future__ import annotations

import json
import sqlite3

from app.services.stronghold_common import grace_ends_at_text

EVENT_SLUG = "the-stronghold"
COLLECTION_CODE = "the_stronghold"
COLLECTION_NAME = "The Stronghold"

# player_key -> (display_name, position, team, country)
HEISKANEN_KEY = "miro-heiskanen"
HEISKANEN_META = ("Miro Heiskanen", "D", "Dallas Stars", "Finland")

# (player_key, name, position, team, country, overall, salary)
OTHER_CARDS = [
    ("victor-hedman", "Victor Hedman", "D", "Tampa Bay Lightning", "Sweden", 98, 8200),
    ("connor-hellebuyck", "Connor Hellebuyck", "G", "Winnipeg Jets", "USA", 98, 8200),
    ("jaccob-slavin", "Jaccob Slavin", "D", "Carolina Hurricanes", "USA", 98, 8200),
    ("charlie-mcavoy", "Charlie McAvoy", "D", "Boston Bruins", "USA", 97, 7800),
    ("moritz-seider", "Moritz Seider", "D", "Detroit Red Wings", "Germany", 97, 7800),
    ("sergei-bobrovsky", "Sergei Bobrovsky", "G", "Florida Panthers", "Russia", 97, 7800),
    ("aleksander-barkov", "Aleksander Barkov", "F", "Florida Panthers", "Finland", 97, 7800),
    ("devon-toews", "Devon Toews", "D", "Colorado Avalanche", "Canada", 96, 7400),
    ("mackenzie-weegar", "Mackenzie Weegar", "D", "Calgary Flames", "Canada", 96, 7400),
    ("jordan-staal", "Jordan Staal", "F", "Carolina Hurricanes", "Canada", 96, 7400),
    ("jeremy-swayman", "Jeremy Swayman", "G", "Boston Bruins", "USA", 96, 7400),
    ("brock-faber", "Brock Faber", "D", "Minnesota Wild", "USA", 95, 7000),
    ("rasmus-andersson", "Rasmus Andersson", "D", "Calgary Flames", "Sweden", 95, 7000),
    ("radko-gudas", "Radko Gudas", "D", "Anaheim Ducks", "Czechia", 95, 7000),
    ("anthony-cirelli", "Anthony Cirelli", "F", "Tampa Bay Lightning", "Canada", 95, 7000),
]

HEISKANEN_SALARY_BY_OVR = {92: 6000, 93: 6300, 94: 6600, 95: 7000, 96: 7400, 97: 7800, 98: 8200, 99: 8600}

UPGRADE_STEPS = [
    (92, 93, 20, 150_000),
    (93, 94, 30, 250_000),
    (94, 95, 40, 400_000),
    (95, 96, 50, 550_000),
    (96, 97, 65, 700_000),
    (97, 98, 75, 900_000),
    (98, 99, 95, 1_100_000),
]

# (order_index, code, title, first_completion_ft, is_boss)
FORTRESS_FT_REWARDS = [8, 8, 10, 10, 12, 12, 14, 14, 16, 16, 18, 18, 20, 20, 24]

DEFAULT_STAR_RULES = json.dumps([
    {"type": "win"},
    {"type": "goal_diff", "min": 2},
    {"type": "clean_sheet", "max_allowed": 1},
])
BOSS_STAR_RULES = json.dumps([
    {"type": "win"},
    {"type": "goal_diff", "min": 3},
    {"type": "clean_sheet", "max_allowed": 0},
])


def _get_or_create_card(
    connection: sqlite3.Connection,
    *,
    collection_id: int,
    player_key: str,
    name: str,
    position: str,
    overall: int,
    team: str,
    country: str,
    salary: int,
) -> int:
    """Bind gameplay to an admin-uploaded card by name + OVR + collection.

    Admin card creation uses a different player_key format than the historical seed,
    so player_key alone created duplicate placeholder cards. Name/OVR/collection is
    now the primary identity. A real uploaded image is preferred over an old seed
    placeholder when both exist. Missing definitions are still created so a clean
    installation remains bootable.
    """
    row = connection.execute(
        """
        SELECT id
        FROM cards
        WHERE collection_id = ?
          AND overall = ?
          AND lower(trim(name)) = lower(trim(?))
        ORDER BY CASE WHEN image_path LIKE 'assets/uploads/stronghold/%' THEN 1 ELSE 0 END, id DESC
        LIMIT 1
        """,
        (collection_id, overall, name),
    ).fetchone()
    if row is None:
        row = connection.execute(
            "SELECT id FROM cards WHERE player_key = ? AND overall = ? AND collection_id = ? ORDER BY id DESC LIMIT 1",
            (player_key, overall, collection_id),
        ).fetchone()

    if row is not None:
        connection.execute(
            """
            UPDATE cards
            SET player_key = ?, name = ?, position = ?, team = ?, country = ?,
                rarity = 'Event', salary = ?, active = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (player_key, name, position, team, country, salary, row["id"]),
        )
        return int(row["id"])

    image_path = f"assets/uploads/stronghold/{player_key}_{overall}.png"
    cursor = connection.execute(
        """
        INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Event', ?, ?, 1)
        """,
        (name, player_key, position, overall, team, country, collection_id, image_path, salary),
    )
    return int(cursor.lastrowid)


def _seed_event(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT id FROM stronghold_events WHERE slug = ?", (EVENT_SLUG,)).fetchone()
    if row is not None:
        return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO stronghold_events (slug, title, description, status, store_available_in_grace, ft_conversion_rate, config_version)
        VALUES (?, 'THE STRONGHOLD', 'Сезонное событие: 15 Fortress, Endless Siege и апгрейд Miro Heiskanen 92-99.', 'DRAFT', 1, 5000, 1)
        """,
        (EVENT_SLUG,),
    )
    return int(cursor.lastrowid)


def _seed_collection(connection: sqlite3.Connection) -> int:
    """Merge legacy/admin-created aliases into exact collection `The Stronghold`."""
    alias_codes = (COLLECTION_CODE, "the-stronghold")
    placeholders = ", ".join("?" for _ in alias_codes)
    rows = connection.execute(
        f"""
        SELECT id, code
        FROM collections
        WHERE code IN ({placeholders}) OR lower(trim(name)) = ?
        ORDER BY CASE WHEN code = ? THEN 0 ELSE 1 END, id
        """,
        (*alias_codes, COLLECTION_NAME.lower(), COLLECTION_CODE),
    ).fetchall()

    if rows:
        canonical_id = int(rows[0]["id"])
    else:
        cursor = connection.execute(
            "INSERT INTO collections (code, name, description, active) VALUES (?, ?, '', 1)",
            (COLLECTION_CODE, COLLECTION_NAME),
        )
        canonical_id = int(cursor.lastrowid)
        rows = []

    for row in rows[1:]:
        duplicate_id = int(row["id"])
        connection.execute("UPDATE cards SET collection_id = ? WHERE collection_id = ?", (canonical_id, duplicate_id))
        connection.execute("UPDATE pack_slots SET collection_id = ? WHERE collection_id = ?", (canonical_id, duplicate_id))
        connection.execute("UPDATE pack_slots SET special_collection_id = ? WHERE special_collection_id = ?", (canonical_id, duplicate_id))
        connection.execute("DELETE FROM collections WHERE id = ?", (duplicate_id,))

    connection.execute(
        """
        UPDATE collections
        SET code = ?, name = ?, description = 'Событийная коллекция The Stronghold.',
            active = 1, is_exclusive = 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (COLLECTION_CODE, COLLECTION_NAME, canonical_id),
    )
    return canonical_id


def _seed_cards(connection: sqlite3.Connection, collection_id: int) -> dict[str, int]:
    card_ids: dict[str, int] = {}

    for overall, salary in HEISKANEN_SALARY_BY_OVR.items():
        name, position, team, country = HEISKANEN_META
        card_id = _get_or_create_card(
            connection,
            collection_id=collection_id,
            player_key=HEISKANEN_KEY,
            name=name,
            position=position,
            overall=overall,
            team=team,
            country=country,
            salary=salary,
        )
        card_ids[f"heiskanen_{overall}"] = card_id

    for player_key, name, position, team, country, overall, salary in OTHER_CARDS:
        card_id = _get_or_create_card(
            connection,
            collection_id=collection_id,
            player_key=player_key,
            name=name,
            position=position,
            overall=overall,
            team=team,
            country=country,
            salary=salary,
        )
        card_ids[player_key] = card_id

    assert len(card_ids) == 23, f"THE STRONGHOLD должна содержать 23 Card Definition, получено {len(card_ids)}"
    return card_ids


def _seed_upgrade_steps(connection: sqlite3.Connection, event_id: int, card_ids: dict[str, int]) -> None:
    total_ft = 0
    total_coins = 0
    for step_order, (from_ovr, to_ovr, ft_cost, coins_cost) in enumerate(UPGRADE_STEPS, start=1):
        from_card_id = card_ids[f"heiskanen_{from_ovr}"]
        to_card_id = card_ids[f"heiskanen_{to_ovr}"]
        total_ft += ft_cost
        total_coins += coins_cost
        connection.execute(
            """
            INSERT INTO stronghold_upgrade_steps (event_id, step_order, from_card_id, to_card_id, ft_cost, coins_cost)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, step_order) DO UPDATE SET
                from_card_id = excluded.from_card_id,
                to_card_id = excluded.to_card_id,
                ft_cost = excluded.ft_cost,
                coins_cost = excluded.coins_cost,
                updated_at = CURRENT_TIMESTAMP
            """,
            (event_id, step_order, from_card_id, to_card_id, ft_cost, coins_cost),
        )

    assert total_ft == 375, f"Сумма FT Upgrade Chain должна быть 375, получено {total_ft}"
    assert total_coins == 4_050_000, f"Сумма Coins Upgrade Chain должна быть 4 050 000, получено {total_coins}"


def _seed_fortresses(connection: sqlite3.Connection, event_id: int) -> None:
    assert len(FORTRESS_FT_REWARDS) == 15
    assert sum(FORTRESS_FT_REWARDS) == 220, f"Сумма FT за Fortress должна быть 220, получено {sum(FORTRESS_FT_REWARDS)}"

    for order_index in range(1, 16):
        is_boss = order_index == 15
        code = f"fortress-{order_index:02d}"
        title = f"Fortress {order_index}" if not is_boss else "Fortress 15 — The Last Stand"
        first_completion_ft = FORTRESS_FT_REWARDS[order_index - 1]
        repeat_coins_reward = 10_000 + (order_index - 1) * 1_000 + (30_000 if is_boss else 0)

        connection.execute(
            """
            INSERT INTO stronghold_fortresses (event_id, order_index, code, title, description, is_boss, first_completion_ft, repeat_coins_reward, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(event_id, order_index) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                is_boss = excluded.is_boss,
                first_completion_ft = excluded.first_completion_ft,
                repeat_coins_reward = excluded.repeat_coins_reward,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                event_id,
                order_index,
                code,
                title,
                f"Крепость {order_index} события THE STRONGHOLD.",
                int(is_boss),
                first_completion_ft,
                repeat_coins_reward,
            ),
        )
        fortress_row = connection.execute(
            "SELECT id FROM stronghold_fortresses WHERE event_id = ? AND order_index = ?", (event_id, order_index)
        ).fetchone()
        fortress_id = int(fortress_row["id"])

        base_ovr = 65 + (order_index - 1) * 2
        for match_order in range(1, 7):
            is_final_match = match_order == 6
            opponent_ovr = min(base_ovr + match_order, 99)
            opponent_name = f"{title} Boss" if (is_boss and is_final_match) else f"{title} Guard {match_order}"
            star_rules = BOSS_STAR_RULES if (is_boss and is_final_match) else DEFAULT_STAR_RULES

            connection.execute(
                """
                INSERT INTO stronghold_fortress_matches (fortress_id, order_index, opponent_name, opponent_ovr, star_rules, active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(fortress_id, order_index) DO UPDATE SET
                    opponent_name = excluded.opponent_name,
                    opponent_ovr = excluded.opponent_ovr,
                    star_rules = excluded.star_rules,
                    active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (fortress_id, match_order, opponent_name, opponent_ovr, star_rules),
            )


def _seed_endless_config(connection: sqlite3.Connection, event_id: int) -> None:
    connection.execute(
        """
        INSERT INTO stronghold_endless_config (event_id, base_opponent_ovr, ovr_growth_per_wave, max_opponent_ovr, weekly_ft_cap, ft_per_wave, modifier_every_n_waves)
        VALUES (?, 80, 1, 99, 20, 2, 5)
        ON CONFLICT(event_id) DO UPDATE SET
            base_opponent_ovr = excluded.base_opponent_ovr,
            ovr_growth_per_wave = excluded.ovr_growth_per_wave,
            max_opponent_ovr = excluded.max_opponent_ovr,
            weekly_ft_cap = excluded.weekly_ft_cap,
            ft_per_wave = excluded.ft_per_wave,
            modifier_every_n_waves = excluded.modifier_every_n_waves,
            updated_at = CURRENT_TIMESTAMP
        """,
        (event_id,),
    )


def _seed_missions(connection: sqlite3.Connection, event_id: int) -> None:
    missions = [
        ("daily_play_2", "DAILY", "Сыграть 2 матча", "play_matches", 2, 2, 5_000, 5),
        ("daily_win_1", "DAILY", "Выиграть 1 матч", "win_matches", 1, 2, 5_000, 5),
        ("weekly_fortress_5", "WEEKLY", "Пройти 5 матчей Fortress", "fortress_match_complete", 5, 8, 20_000, 20),
        ("weekly_stars_10", "WEEKLY", "Заработать 10 звёзд в Fortress", "earn_stars", 10, 7, 15_000, 15),
        ("weekly_endless_3", "WEEKLY", "Пройти 3 волны Endless Siege", "endless_wave_complete", 3, 5, 10_000, 10),
        ("season_fortress_5", "SEASONAL", "Пройти 5 крепостей полностью", "fortress_complete", 5, 10, 50_000, 30),
        ("season_upgrade_3", "SEASONAL", "Улучшить Miro Heiskanen 3 раза", "upgrade_heiskanen", 3, 10, 50_000, 30),
        ("season_endless_10", "SEASONAL", "Пройти 10 волн Endless Siege", "endless_wave_complete", 10, 10, 50_000, 30),
    ]

    daily_ft_total = sum(m[5] for m in missions if m[1] == "DAILY")
    weekly_ft_total = sum(m[5] for m in missions if m[1] == "WEEKLY")
    assert daily_ft_total == 4, f"Daily Missions должны давать 4 FT/день, получено {daily_ft_total}"
    assert weekly_ft_total == 20, f"Weekly Missions должны давать 20 FT/неделю, получено {weekly_ft_total}"

    for sort_order, (code, mission_type, title, condition_type, target_value, reward_ft, reward_coins, reward_xp) in enumerate(missions, start=1):
        connection.execute(
            """
            INSERT INTO stronghold_missions (event_id, code, type, title, description, condition_type, target_value, reward_ft, reward_coins, reward_xp, active, sort_order)
            VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(event_id, code) DO UPDATE SET
                type = excluded.type,
                title = excluded.title,
                condition_type = excluded.condition_type,
                target_value = excluded.target_value,
                reward_ft = excluded.reward_ft,
                reward_coins = excluded.reward_coins,
                reward_xp = excluded.reward_xp,
                active = 1,
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            (event_id, code, mission_type, title, condition_type, target_value, reward_ft, reward_coins, reward_xp, sort_order),
        )


def _seed_season_track(connection: sqlite3.Connection, event_id: int) -> None:
    levels = [
        (1, 100, 0, 10_000),
        (2, 250, 5, 15_000),
        (3, 450, 0, 20_000),
        (4, 700, 10, 20_000),
        (5, 1_000, 0, 25_000),
        (6, 1_400, 10, 25_000),
        (7, 1_900, 0, 30_000),
        (8, 2_500, 10, 30_000),
        (9, 3_200, 0, 35_000),
        (10, 4_000, 15, 40_000),
    ]
    total_ft = sum(level[2] for level in levels)
    assert total_ft == 50, f"Season Track должен давать 50 FT, получено {total_ft}"

    for level, xp_threshold, reward_ft, reward_coins in levels:
        connection.execute(
            """
            INSERT INTO stronghold_season_track_levels (event_id, level, xp_threshold, reward_ft, reward_coins, title)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, level) DO UPDATE SET
                xp_threshold = excluded.xp_threshold,
                reward_ft = excluded.reward_ft,
                reward_coins = excluded.reward_coins,
                title = excluded.title,
                updated_at = CURRENT_TIMESTAMP
            """,
            (event_id, level, xp_threshold, reward_ft, reward_coins, f"Уровень {level}"),
        )


def _seed_store(connection: sqlite3.Connection, event_id: int, card_ids: dict[str, int]) -> None:
    products = [
        (
            "featured_coin_cache",
            "Featured",
            "Тайник Coins",
            "Обменяй Fortress Tokens на крупную сумму Coins.",
            "fortress_token",
            10,
            0,
            [{"type": "currency", "currency_code": "coins", "amount": 60_000}],
        ),
        (
            "resources_ft_bundle",
            "Bundles",
            "Набор Fortress Tokens",
            "Пакет Fortress Tokens за Coins (ограничено).",
            "coins",
            500_000,
            3,
            [{"type": "currency", "currency_code": "fortress_token", "amount": 5}],
        ),
        (
            "cards_radko_gudas",
            "Cards",
            "Radko Gudas (95 OVR)",
            "Дополнительная копия карты коллекции THE STRONGHOLD.",
            "fortress_token",
            15,
            1,
            [{"type": "card", "card_id": card_ids["radko-gudas"], "amount": 1}],
        ),
        (
            "resources_energy_boost",
            "Resources",
            "Малый набор Coins",
            "Небольшой набор Coins для текущих нужд.",
            "fortress_token",
            5,
            0,
            [{"type": "currency", "currency_code": "coins", "amount": 25_000}],
        ),
    ]

    for sort_order, (code, category, title, description, price_currency_code, price_amount, purchase_limit, contents) in enumerate(products, start=1):
        connection.execute(
            """
            INSERT INTO stronghold_store_products (
                event_id, code, category, title, description, price_currency_code, price_amount,
                purchase_limit, contents, active, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(event_id, code) DO UPDATE SET
                category = excluded.category,
                title = excluded.title,
                description = excluded.description,
                price_currency_code = excluded.price_currency_code,
                price_amount = excluded.price_amount,
                purchase_limit = excluded.purchase_limit,
                contents = excluded.contents,
                active = 1,
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            (event_id, code, category, title, description, price_currency_code, price_amount, purchase_limit, json.dumps(contents), sort_order),
        )


def seed_stronghold_content(connection: sqlite3.Connection) -> None:
    event_id = _seed_event(connection)
    collection_id = _seed_collection(connection)
    card_ids = _seed_cards(connection, collection_id)
    _seed_upgrade_steps(connection, event_id, card_ids)
    _seed_fortresses(connection, event_id)
    _seed_endless_config(connection, event_id)
    _seed_missions(connection, event_id)
    _seed_season_track(connection, event_id)
    _seed_store(connection, event_id, card_ids)


def schedule_default_dates_if_missing(connection: sqlite3.Connection, *, starts_at_text: str, days: int = 30) -> None:
    """Утилита для dev/smoke: если у события ещё нет дат, планирует ACTIVE на `days` дней."""
    from datetime import datetime, timedelta

    row = connection.execute("SELECT id, starts_at, ends_at FROM stronghold_events WHERE slug = ?", (EVENT_SLUG,)).fetchone()
    if row is None or row["starts_at"]:
        return
    starts_at = datetime.strptime(starts_at_text, "%Y-%m-%d %H:%M:%S")
    ends_at_text = (starts_at + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        "UPDATE stronghold_events SET starts_at = ?, ends_at = ?, grace_ends_at = ? WHERE id = ?",
        (starts_at_text, ends_at_text, grace_ends_at_text(ends_at_text), row["id"]),
    )
