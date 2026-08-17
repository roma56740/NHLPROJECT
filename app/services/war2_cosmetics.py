"""Global cosmetic catalog and tradable owned-item inventory.

The physical table names still contain ``war2`` for migration compatibility, but
cosmetics are not tied to CLAN WAR or Ranked.  Every ``user_cosmetic_items`` row
is one concrete copy that may be equipped, bound to one card, sold on Black
Market (catalog item) or transferred in player trades (owned copy).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.war2_common import War2Error

COSMETIC_TYPES = ("FRAME", "BACKGROUND", "NICK_BADGE", "CARD_FRAME", "PROFILE_BACKGROUND", "TITLE")
CARD_FRAME_TYPES = ("CARD_FRAME", "FRAME")
PROFILE_BACKGROUND_TYPES = ("PROFILE_BACKGROUND", "BACKGROUND")
PREFIX_TYPES = ("NICK_BADGE",)


@dataclass(frozen=True)
class CosmeticItem:
    id: int
    type: str
    code: str
    title: str
    description: str
    rarity: str
    image_path: str | None
    badge_text: str | None
    active: bool


@dataclass(frozen=True)
class OwnedCosmeticItem:
    id: int
    cosmetic_item_id: int
    type: str
    rarity: str
    source: str
    equipped: bool
    title: str
    image_path: str | None
    badge_text: str | None
    trade_locked: bool = False
    bound_user_card_id: int | None = None


def canonical_cosmetic_type(value: str) -> str:
    if value in CARD_FRAME_TYPES:
        return "CARD_FRAME"
    if value in PROFILE_BACKGROUND_TYPES:
        return "PROFILE_BACKGROUND"
    return value


def compatible_types(value: str) -> tuple[str, ...]:
    canonical = canonical_cosmetic_type(value)
    if canonical == "CARD_FRAME":
        return CARD_FRAME_TYPES
    if canonical == "PROFILE_BACKGROUND":
        return PROFILE_BACKGROUND_TYPES
    return (canonical,)


def cosmetic_type_title(value: str) -> str:
    return {
        "CARD_FRAME": "Рамка карты",
        "PROFILE_BACKGROUND": "Фон профиля/состава",
        "NICK_BADGE": "Приписка к нику",
        "TITLE": "Титул",
    }.get(canonical_cosmetic_type(value), value)


def _row_to_item(row: sqlite3.Row) -> CosmeticItem:
    return CosmeticItem(
        id=int(row["id"]),
        type=row["type"],
        code=row["code"],
        title=row["title"],
        description=row["description"],
        rarity=row["rarity"],
        image_path=row["image_path"],
        badge_text=row["badge_text"],
        active=bool(row["active"]),
    )


def _row_to_owned(row: sqlite3.Row) -> OwnedCosmeticItem:
    keys = row.keys()
    return OwnedCosmeticItem(
        id=int(row["id"]),
        cosmetic_item_id=int(row["cosmetic_item_id"]),
        type=row["type"],
        rarity=row["rarity"],
        source=row["source"],
        equipped=bool(row["equipped"]),
        title=row["title"],
        image_path=row["image_path"],
        badge_text=row["badge_text"],
        trade_locked=bool(row["trade_locked"]) if "trade_locked" in keys else False,
        bound_user_card_id=(int(row["bound_user_card_id"]) if "bound_user_card_id" in keys and row["bound_user_card_id"] is not None else None),
    )


async def create_cosmetic_item(
    *,
    type: str,
    code: str,
    title: str,
    description: str = "",
    rarity: str = "Common",
    image_path: str | None = None,
    badge_text: str | None = None,
) -> int:
    if type not in COSMETIC_TYPES:
        raise War2Error("COSMETIC_INVALID_TYPE", f"Неизвестный тип предмета: {type}.")
    with get_connection() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO war2_cosmetic_items (type, code, title, description, rarity, image_path, badge_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (type, code, title, description, rarity, image_path, badge_text),
            )
        except sqlite3.IntegrityError as error:
            raise War2Error("COSMETIC_CODE_TAKEN", f"Код '{code}' уже используется.") from error
        connection.commit()
        return int(cursor.lastrowid)


async def update_cosmetic_item(
    cosmetic_item_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    rarity: str | None = None,
    image_path: str | None = None,
    badge_text: str | None = None,
    active: bool | None = None,
) -> None:
    fields: list[str] = []
    params: list[object] = []
    for column, value in (
        ("title", title),
        ("description", description),
        ("rarity", rarity),
        ("image_path", image_path),
        ("badge_text", badge_text),
    ):
        if value is not None:
            fields.append(f"{column} = ?")
            params.append(value)
    if active is not None:
        fields.append("active = ?")
        params.append(1 if active else 0)
    if not fields:
        return
    fields.append("updated_at = CURRENT_TIMESTAMP")
    params.append(cosmetic_item_id)
    with get_connection() as connection:
        connection.execute(f"UPDATE war2_cosmetic_items SET {', '.join(fields)} WHERE id = ?", params)
        connection.commit()


async def delete_cosmetic_item(cosmetic_item_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE war2_cosmetic_items SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (cosmetic_item_id,),
        )
        connection.commit()


async def list_cosmetic_items(type: str | None = None, active_only: bool = False) -> list[CosmeticItem]:
    filters: list[str] = []
    params: list[object] = []
    if type is not None:
        aliases = compatible_types(type)
        filters.append(f"type IN ({','.join('?' for _ in aliases)})")
        params.extend(aliases)
    if active_only:
        filters.append("active = 1")
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM war2_cosmetic_items {where_sql} ORDER BY type, title", params
        ).fetchall()
    return [_row_to_item(row) for row in rows]


async def get_cosmetic_item(cosmetic_item_id: int) -> CosmeticItem | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM war2_cosmetic_items WHERE id = ?", (cosmetic_item_id,)).fetchone()
    return _row_to_item(row) if row is not None else None


async def grant_cosmetic_to_user(user_id: int, cosmetic_item_id: int, source: str = "admin_grant") -> int:
    item = await get_cosmetic_item(cosmetic_item_id)
    if item is None:
        raise War2Error("COSMETIC_NOT_FOUND", "Предмет не найден.")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source, trade_locked)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (user_id, cosmetic_item_id, item.type, item.rarity, source),
        )
        connection.commit()
        return int(cursor.lastrowid)


async def equip_cosmetic(user_id: int, user_cosmetic_item_id: int) -> None:
    """Equip one global background/prefix/title copy.

    Card frames are deliberately rejected: every frame copy must be bound to one
    concrete ``user_cards`` instance through ranked_cosmetics.bind_frame_to_card.
    """
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        owned = connection.execute(
            "SELECT type, trade_locked FROM user_cosmetic_items WHERE id = ? AND owner_id = ?",
            (user_cosmetic_item_id, user_id),
        ).fetchone()
        if owned is None:
            connection.rollback()
            raise War2Error("COSMETIC_NOT_OWNED", "Этот предмет вам не принадлежит.")
        if bool(owned["trade_locked"]):
            connection.rollback()
            raise War2Error("COSMETIC_TRADE_LOCKED", "Предмет заблокирован и сейчас недоступен.")
        in_open_trade = connection.execute(
            """
            SELECT 1 FROM trade_offer_cosmetics toc
            JOIN trade_offers t ON t.id = toc.offer_id
            WHERE toc.user_cosmetic_item_id = ? AND t.status = 'open'
            LIMIT 1
            """,
            (user_cosmetic_item_id,),
        ).fetchone()
        if in_open_trade is not None:
            connection.rollback()
            raise War2Error("COSMETIC_IN_TRADE", "Предмет выставлен в открытом обмене. Сначала отмените обмен.")
        if canonical_cosmetic_type(owned["type"]) == "CARD_FRAME":
            connection.rollback()
            raise War2Error("FRAME_REQUIRES_CARD", "Рамку нужно установить на конкретную карту.")

        aliases = compatible_types(owned["type"])
        placeholders = ",".join("?" for _ in aliases)
        connection.execute(
            f"UPDATE user_cosmetic_items SET equipped = 0 WHERE owner_id = ? AND type IN ({placeholders}) AND equipped = 1",
            (user_id, *aliases),
        )
        connection.execute(
            "UPDATE user_cosmetic_items SET equipped = 1 WHERE id = ? AND owner_id = ?",
            (user_cosmetic_item_id, user_id),
        )
        connection.commit()


async def unequip_cosmetic(user_id: int, type: str) -> None:
    aliases = compatible_types(type)
    placeholders = ",".join("?" for _ in aliases)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE user_cosmetic_items SET equipped = 0 WHERE owner_id = ? AND type IN ({placeholders}) AND equipped = 1",
            (user_id, *aliases),
        )
        connection.commit()


async def get_user_cosmetics_page(user_id: int, type: str) -> list[OwnedCosmeticItem]:
    aliases = compatible_types(type)
    placeholders = ",".join("?" for _ in aliases)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT uci.*, wci.title, wci.image_path, wci.badge_text,
                   ucf.user_card_id AS bound_user_card_id
            FROM user_cosmetic_items uci
            JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
            LEFT JOIN user_card_frames ucf ON ucf.user_cosmetic_item_id = uci.id
            WHERE uci.owner_id = ? AND uci.type IN ({placeholders})
            ORDER BY uci.created_at DESC, uci.id DESC
            """,
            (user_id, *aliases),
        ).fetchall()
    return [_row_to_owned(row) for row in rows]


async def list_all_owned_cosmetics(user_id: int, *, tradable_only: bool = False) -> list[OwnedCosmeticItem]:
    extra = """
      AND uci.trade_locked = 0
      AND uci.equipped = 0
      AND ucf.id IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM trade_offer_cosmetics toc
          JOIN trade_offers t ON t.id = toc.offer_id
          WHERE toc.user_cosmetic_item_id = uci.id AND t.status = 'open'
      )
    """ if tradable_only else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT uci.*, wci.title, wci.image_path, wci.badge_text,
                   ucf.user_card_id AS bound_user_card_id
            FROM user_cosmetic_items uci
            JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
            LEFT JOIN user_card_frames ucf ON ucf.user_cosmetic_item_id = uci.id
            WHERE uci.owner_id = ? {extra}
            ORDER BY uci.type, wci.title, uci.id
            """,
            (user_id,),
        ).fetchall()
    return [_row_to_owned(row) for row in rows]


async def _get_equipped(user_id: int, type: str) -> OwnedCosmeticItem | None:
    aliases = compatible_types(type)
    placeholders = ",".join("?" for _ in aliases)
    canonical = canonical_cosmetic_type(type)
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT uci.*, wci.title, wci.image_path, wci.badge_text,
                   NULL AS bound_user_card_id
            FROM user_cosmetic_items uci
            JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
            WHERE uci.owner_id = ? AND uci.type IN ({placeholders}) AND uci.equipped = 1
            ORDER BY CASE WHEN uci.type = ? THEN 0 ELSE 1 END, uci.id DESC
            LIMIT 1
            """,
            (user_id, *aliases, canonical),
        ).fetchone()
    return _row_to_owned(row) if row is not None else None


async def get_equipped_background_path(user_id: int) -> str | None:
    item = await _get_equipped(user_id, "PROFILE_BACKGROUND")
    return item.image_path if item else None


async def get_equipped_frame_path(user_id: int) -> str | None:
    """Deprecated global frame API.

    Frames are no longer painted over every card.  They are inventory copies
    bound to one concrete card, so callers receive ``None`` and renderers load
    per-card bindings instead.
    """
    return None


async def get_equipped_badge_text(user_id: int) -> str | None:
    item = await _get_equipped(user_id, "NICK_BADGE")
    return item.badge_text if item else None


async def get_equipped_title(user_id: int) -> str | None:
    item = await _get_equipped(user_id, "TITLE")
    return item.title if item else None


def format_nickname_with_badge(nickname: str, badge_text: str | None) -> str:
    if not badge_text:
        return nickname
    return f"{nickname} [{badge_text}]"


async def get_display_nickname(user_id: int, nickname: str) -> str:
    return format_nickname_with_badge(nickname, await get_equipped_badge_text(user_id))
