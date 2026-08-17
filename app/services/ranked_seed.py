"""Повторно запускаемый сид контента RANKED MODE (v1).

Вызывается из `app/database/db.py:init_database()` внутри уже открытой транзакции —
не коммитит и не открывает соединение самостоятельно. Идемпотентен: повторный запуск
не создаёт дублей (upsert по коду/уникальным ключам, тот же паттерн, что и в
app/services/war2_seed.py и app/services/stronghold_seed.py).

Не сидируются здесь (по прямой аналогии с существующим Hockey Pass, у которого тоже
нет ни одной дефолтной записи — полностью admin-managed с нуля): активный сезон
(`ranked_seasons`, admin запускает через admin_ranked:season_start) и сам Ranked Pass
(`ranked_passes`, admin создаёт под сезон). Здесь только структура: 21 лига, коллекция
Ranked Season 1 (без встроенных карт), 7 паков (с минимальным функциональным слотом по умолчанию),
награды по лигам (NICK_BADGE/CARD_FRAME/PROFILE_BACKGROUND).
"""

from __future__ import annotations

import sqlite3

LEGENDS_COLLECTION_CODE = "ranked_season1_legends"
LEGENDS_COLLECTION_NAME = "Ranked Season 1"

# (division_code, title, icon)
DIVISIONS: list[tuple[str, str, str]] = [
    ("bronze", "Bronze", "🥉"),
    ("silver", "Silver", "🥈"),
    ("gold", "Gold", "🥇"),
    ("platinum", "Platinum", "💠"),
    ("diamond", "Diamond", "💎"),
    ("master", "Master", "🎖"),
    ("legend", "Legend", "👑"),
]

# (division_code, tier_number) -> min_points; 7 дивизионов x 3 уровня = 21 лига.
TIER_THRESHOLDS: dict[str, list[int]] = {
    "bronze": [0, 100, 200],
    "silver": [300, 450, 600],
    "gold": [800, 1000, 1200],
    "platinum": [1500, 1800, 2100],
    "diamond": [2500, 2900, 3300],
    "master": [3800, 4300, 4800],
    "legend": [5500, 6300, 7100],
}

REWARD_TYPE_BY_TIER = {1: "NICK_BADGE", 2: "CARD_FRAME", 3: "PROFILE_BACKGROUND"}

# (code, division_code, name)
RANKED_PACKS: list[tuple[str, str, str]] = [
    (f"ranked_pack_{division_code}", division_code, f"{title} Pack") for division_code, title, _icon in DIVISIONS
]


def _seed_legends_collection(connection: sqlite3.Connection) -> int:
    """Resolve/merge the admin-uploaded collection and keep its cards intact.

    Before this update an administrator may already have created `Ranked Season 1`
    through the Cards panel. That produces code `ranked-season-1`, while old builds
    had the empty code `ranked_season1_legends`. We merge both into the old stable
    code so all foreign keys and future updates attach to the uploaded cards.
    """
    alias_codes = (LEGENDS_COLLECTION_CODE, "ranked-season-1", "ranked_season_1")
    placeholders = ", ".join("?" for _ in alias_codes)
    rows = connection.execute(
        f"""
        SELECT id, code
        FROM collections
        WHERE code IN ({placeholders}) OR lower(trim(name)) IN (?, ?)
        ORDER BY CASE WHEN code = ? THEN 0 ELSE 1 END, id
        """,
        (*alias_codes, LEGENDS_COLLECTION_NAME.lower(), "ranked season 1 legends", LEGENDS_COLLECTION_CODE),
    ).fetchall()

    if rows:
        canonical_id = int(rows[0]["id"])
    else:
        cursor = connection.execute(
            "INSERT INTO collections (code, name, description, active) VALUES (?, ?, '', 1)",
            (LEGENDS_COLLECTION_CODE, LEGENDS_COLLECTION_NAME),
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
        SET code = ?, name = ?,
            description = 'Коллекция наград Ranked Season 1 — карты загружаются администрацией через раздел Карточки.',
            active = 1, is_exclusive = 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (LEGENDS_COLLECTION_CODE, LEGENDS_COLLECTION_NAME, canonical_id),
    )
    return canonical_id


def _seed_leagues(connection: sqlite3.Connection) -> dict[tuple[str, int], int]:
    league_ids: dict[tuple[str, int], int] = {}
    sort_order = 0
    for division_code, title, icon in DIVISIONS:
        thresholds = TIER_THRESHOLDS[division_code]
        for tier_number in (1, 2, 3):
            min_points = thresholds[tier_number - 1]
            tier_title = f"{title} {tier_number}"
            connection.execute(
                """
                INSERT INTO ranked_leagues (division_code, tier_number, title, min_points, sort_order, icon, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(division_code, tier_number) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP
                """,
                (division_code, tier_number, tier_title, min_points, sort_order, icon),
            )
            row = connection.execute(
                "SELECT id FROM ranked_leagues WHERE division_code = ? AND tier_number = ?",
                (division_code, tier_number),
            ).fetchone()
            league_ids[(division_code, tier_number)] = int(row["id"])
            sort_order += 1
    return league_ids


def _get_or_create_cosmetic_item(
    connection: sqlite3.Connection,
    *,
    type: str,
    code: str,
    title: str,
    rarity: str,
    badge_text: str | None = None,
) -> int:
    row = connection.execute("SELECT id FROM war2_cosmetic_items WHERE code = ?", (code,)).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO war2_cosmetic_items (type, code, title, rarity, badge_text, active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (type, code, title, rarity, badge_text),
    )
    return int(cursor.lastrowid)


def _seed_league_rewards(connection: sqlite3.Connection, league_ids: dict[tuple[str, int], int]) -> None:
    for division_code, title, _icon in DIVISIONS:
        for tier_number in (1, 2, 3):
            reward_type = REWARD_TYPE_BY_TIER[tier_number]
            code = f"ranked_reward_{division_code}_{tier_number}"
            cosmetic_title = f"{title} {reward_type.replace('_', ' ').title()}"
            cosmetic_item_id = _get_or_create_cosmetic_item(
                connection,
                type=reward_type,
                code=code,
                title=cosmetic_title,
                rarity="Rare",
                badge_text=f"{title.upper()}" if reward_type == "NICK_BADGE" else None,
            )
            league_id = league_ids[(division_code, tier_number)]
            existing = connection.execute(
                "SELECT id FROM ranked_league_rewards WHERE ranked_league_id = ? AND cosmetic_item_id = ?",
                (league_id, cosmetic_item_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO ranked_league_rewards (ranked_league_id, reward_type, cosmetic_item_id, active)
                    VALUES (?, 'cosmetic', ?, 1)
                    """,
                    (league_id, cosmetic_item_id),
                )


def _seed_ranked_packs(connection: sqlite3.Connection) -> None:
    for code, division_code, name in RANKED_PACKS:
        connection.execute(
            """
            INSERT INTO ranked_packs (code, division_code, name, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (code, division_code, name),
        )
        pack_row = connection.execute("SELECT id FROM ranked_packs WHERE code = ?", (code,)).fetchone()
        pack_id = int(pack_row["id"])

        has_slots = connection.execute(
            "SELECT 1 FROM ranked_pack_slots WHERE pack_id = ? LIMIT 1", (pack_id,)
        ).fetchone()
        if has_slots is None:
            # Минимальный функциональный слот по умолчанию (XP — не требует контента от
            # админа) — админ настраивает реальные награды (карты/валюту/косметику)
            # позже через админку, раздел ADMIN PANEL ТЗ.
            connection.execute(
                """
                INSERT INTO ranked_pack_slots (pack_id, slot_number, reward_type, amount, active)
                VALUES (?, 1, 'xp', 50, 1)
                """,
                (pack_id,),
            )


def seed_ranked_content(connection: sqlite3.Connection) -> None:
    _seed_legends_collection(connection)
    league_ids = _seed_leagues(connection)
    _seed_league_rewards(connection, league_ids)
    _seed_ranked_packs(connection)
