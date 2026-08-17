"""Повторно запускаемый сид контента CLAN WAR 2.0.

Вызывается из `app/database/db.py:init_database()` внутри уже открытой транзакции —
не коммитит и не открывает соединение самостоятельно. Идемпотентен: повторный запуск
не создаёт дублей. Структура намеренно копирует app/services/stronghold_seed.py
(тот же паттерн upsert-по-коду/upsert-по-(player_key,overall,collection_id)), но
хелперы — локальные копии, а не общий импорт: два независимых сид-модуля проще
редактировать по отдельности, не боясь задеть другое событие.
"""

from __future__ import annotations

import sqlite3

COLLECTION_CODE = "clan_war2_legends"
COLLECTION_NAME = "Clan War Legends"

# (player_key, name, position, team, country, overall, salary)
# Зарплата — по той же шкале, что и Upgrade Chain THE STRONGHOLD (см. stronghold_seed.py
# HEISKANEN_SALARY_BY_OVR): ~ +400 за каждый OVR в диапазоне 93-98.
LEGENDS_CARDS: list[tuple[str, str, str, str, str, int, int]] = [
    ("henrik-zetterberg", "Henrik Zetterberg", "F", "Detroit Red Wings", "Sweden", 98, 8200),
    ("anze-kopitar", "Anze Kopitar", "F", "Los Angeles Kings", "Slovenia", 98, 8200),
    ("mark-stone", "Mark Stone", "F", "Vegas Golden Knights", "Canada", 97, 7800),
    ("brayden-point", "Brayden Point", "F", "Tampa Bay Lightning", "Canada", 97, 7800),
    ("ryan-oreilly", "Ryan O'Reilly", "F", "Nashville Predators", "Canada", 96, 7400),
    ("sebastian-aho", "Sebastian Aho", "F", "Carolina Hurricanes", "Finland", 96, 7400),
    ("jaccob-slavin-legends", "Jaccob Slavin", "D", "Carolina Hurricanes", "USA", 96, 7400),
    ("filip-forsberg", "Filip Forsberg", "F", "Nashville Predators", "Sweden", 95, 7000),
    ("mika-zibanejad", "Mika Zibanejad", "F", "New York Rangers", "Sweden", 95, 7000),
    ("thatcher-demko", "Thatcher Demko", "G", "Vancouver Canucks", "USA", 95, 7000),
    ("robert-thomas", "Robert Thomas", "F", "St. Louis Blues", "Canada", 94, 6600),
    ("brock-boeser", "Brock Boeser", "F", "Vancouver Canucks", "USA", 94, 6600),
    ("timo-meier", "Timo Meier", "F", "New Jersey Devils", "Switzerland", 94, 6600),
    ("mikhail-sergachev", "Mikhail Sergachev", "D", "Utah Hockey Club", "Russia", 93, 6300),
    ("moritz-seider-legends", "Moritz Seider", "D", "Detroit Red Wings", "Germany", 93, 6300),
    ("juuse-saros", "Juuse Saros", "G", "Nashville Predators", "Finland", 93, 6300),
]

# (code, title, description, slot_count)
LEGENDS_PACKS: list[tuple[str, str, str, int]] = [
    ("clan_war2_pack_level_1", "Clan War Legends: уровень 1", "Выдаёт 1 карту из коллекции Clan War Legends.", 1),
    ("clan_war2_pack_level_2", "Clan War Legends: уровень 2", "Выдаёт 2 карты из коллекции Clan War Legends.", 2),
    ("clan_war2_pack_level_3", "Clan War Legends: уровень 3", "Выдаёт 3 карты из коллекции Clan War Legends.", 3),
]

# (code, title, description, uses_draft)
WAR2_MODES = [
    ("CLONE_WAR", "Clone War", "Одинаковый состав для обеих сторон, без Draft — источник Base Collection, 92-99 OVR.", 0),
    ("SALARY_WAR", "Salary War", "После Draft проверяется зарплатный потолок состава.", 1),
    ("WILD_CARD", "Wild Card", "После Draft можно заменить одну карту на карту из своей коллекции.", 1),
]

# Коллекции, которые НЕ должны попадать в Draft Pool / Clone War (раздел "COLLECTION
# SYSTEM" ТЗ: EXCLUSIVE_COLLECTION используется Packs/Inventory/Wild Card, не Draft).
# ВАЖНО: 'free-cards' сюда НЕ входит — это базовая коллекция, откуда как раз и должен
# пополняться Draft Pool/Clone War (BASE_COLLECTION). Помечаем эксклюзивными только
# событийные/наградные коллекции.
EXCLUSIVE_COLLECTION_CODES = ("the_stronghold", COLLECTION_CODE)


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
    row = connection.execute(
        "SELECT id FROM cards WHERE player_key = ? AND overall = ? AND collection_id = ?",
        (player_key, overall, collection_id),
    ).fetchone()
    if row is not None:
        connection.execute(
            "UPDATE cards SET name = ?, position = ?, team = ?, country = ?, salary = ?, active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (name, position, team, country, salary, row["id"]),
        )
        return int(row["id"])

    image_path = f"assets/uploads/clan_war2/{player_key}_{overall}.png"
    cursor = connection.execute(
        """
        INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Icon', ?, ?, 1)
        """,
        (name, player_key, position, overall, team, country, collection_id, image_path, salary),
    )
    return int(cursor.lastrowid)


def _seed_collection(connection: sqlite3.Connection) -> int:
    connection.execute(
        """
        INSERT INTO collections (code, name, description, active)
        VALUES (?, ?, 'Легенды CLAN WAR 2.0 — коллекция для паков CLAN_WAR_PACK_LEVEL_1/2/3.', 1)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            active = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (COLLECTION_CODE, COLLECTION_NAME),
    )
    row = connection.execute("SELECT id FROM collections WHERE code = ?", (COLLECTION_CODE,)).fetchone()
    collection_id = int(row["id"])

    placeholders = ", ".join("?" for _ in EXCLUSIVE_COLLECTION_CODES)
    connection.execute(
        f"UPDATE collections SET is_exclusive = 1 WHERE code IN ({placeholders})",
        EXCLUSIVE_COLLECTION_CODES,
    )
    return collection_id


def _seed_cards(connection: sqlite3.Connection, collection_id: int) -> dict[str, int]:
    card_ids: dict[str, int] = {}
    for player_key, name, position, team, country, overall, salary in LEGENDS_CARDS:
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

    assert len(card_ids) == 16, f"Clan War Legends должна содержать 16 карт, получено {len(card_ids)}"
    return card_ids


def _seed_packs(connection: sqlite3.Connection, card_ids: dict[str, int]) -> None:
    legends_ids = list(card_ids.values())

    for code, title, description, slot_count in LEGENDS_PACKS:
        connection.execute(
            """
            INSERT INTO packs (code, name, description, price_currency_code, price_amount, active, is_shop_available, is_starter, sort_order)
            VALUES (?, ?, ?, NULL, 0, 1, 0, 0, 100)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (code, title, description),
        )
        pack_row = connection.execute("SELECT id FROM packs WHERE code = ?", (code,)).fetchone()
        pack_id = int(pack_row["id"])

        existing_slots = connection.execute(
            "SELECT COUNT(*) AS n FROM pack_slots WHERE pack_id = ?", (pack_id,)
        ).fetchone()["n"]
        if int(existing_slots) != slot_count:
            connection.execute("DELETE FROM pack_slots WHERE pack_id = ?", (pack_id,))
            for slot_number in range(1, slot_count + 1):
                connection.execute(
                    """
                    INSERT INTO pack_slots (pack_id, slot_number, title, collection_id, position, rarity, active)
                    VALUES (?, ?, ?, NULL, NULL, NULL, 1)
                    """,
                    (pack_id, slot_number, f"Legend #{slot_number}"),
                )

        for card_id in legends_ids:
            connection.execute(
                "INSERT OR IGNORE INTO pack_cards (pack_id, card_id) VALUES (?, ?)",
                (pack_id, card_id),
            )


def _seed_modes(connection: sqlite3.Connection) -> None:
    for code, title, description, uses_draft in WAR2_MODES:
        connection.execute(
            """
            INSERT INTO war2_modes (code, title, description, uses_draft, active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                uses_draft = excluded.uses_draft,
                updated_at = CURRENT_TIMESTAMP
            """,
            (code, title, description, uses_draft),
        )

    active_count = connection.execute(
        "SELECT COUNT(*) AS n FROM war2_modes WHERE active = 1"
    ).fetchone()["n"]
    if int(active_count or 0) == 0:
        codes = [item[0] for item in WAR2_MODES]
        placeholders = ", ".join("?" for _ in codes)
        connection.execute(
            f"UPDATE war2_modes SET active = 1, updated_at = CURRENT_TIMESTAMP WHERE code IN ({placeholders})",
            codes,
        )


def seed_war2_content(connection: sqlite3.Connection) -> None:
    collection_id = _seed_collection(connection)
    card_ids = _seed_cards(connection, collection_id)
    _seed_packs(connection, card_ids)
    _seed_modes(connection)
