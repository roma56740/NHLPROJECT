"""Per-copy card frame bindings shared by every game mode.

The module name is retained for compatibility, but the functionality is global:
one owned frame copy can be attached to exactly one concrete ``user_cards`` row.
A bound copy cannot be silently moved or traded.  The user must explicitly
remove it first; a second card needs a second owned copy.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.database.db import get_connection
from app.services.ranked_common import RankedError
from app.services.war2_cosmetics import CARD_FRAME_TYPES


@dataclass(frozen=True)
class CardFrameBinding:
    id: int
    user_cosmetic_item_id: int
    user_card_id: int
    frame_title: str
    frame_image_path: str | None


async def bind_frame_to_card(user_id: int, user_cosmetic_item_id: int, user_card_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        owned = connection.execute(
            "SELECT type, trade_locked FROM user_cosmetic_items WHERE id = ? AND owner_id = ?",
            (user_cosmetic_item_id, user_id),
        ).fetchone()
        if owned is None:
            connection.rollback()
            raise RankedError("CARD_FRAME_NOT_OWNED", "Эта рамка вам не принадлежит.")
        if owned["type"] not in CARD_FRAME_TYPES:
            connection.rollback()
            raise RankedError("NOT_A_CARD_FRAME", "Этот предмет — не рамка для карты.")
        if bool(owned["trade_locked"]):
            connection.rollback()
            raise RankedError("CARD_FRAME_LOCKED", "Эта рамка сейчас заблокирована.")

        existing = connection.execute(
            "SELECT user_card_id FROM user_card_frames WHERE user_cosmetic_item_id = ?",
            (user_cosmetic_item_id,),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            raise RankedError(
                "CARD_FRAME_ALREADY_BOUND",
                "Этот экземпляр рамки уже установлен на карту. Сначала снимите его или используйте второй экземпляр.",
            )

        card_owned = connection.execute(
            "SELECT 1 FROM user_cards WHERE id = ? AND user_id = ?",
            (user_card_id, user_id),
        ).fetchone()
        if card_owned is None:
            connection.rollback()
            raise RankedError("CARD_NOT_OWNED", "Эта карта вам не принадлежит.")

        occupied = connection.execute(
            "SELECT 1 FROM user_card_frames WHERE user_card_id = ?",
            (user_card_id,),
        ).fetchone()
        if occupied is not None:
            connection.rollback()
            raise RankedError("CARD_ALREADY_HAS_FRAME", "На этой карте уже установлена рамка. Сначала снимите её.")

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
            raise RankedError("CARD_FRAME_IN_TRADE", "Эта рамка уже выставлена в открытом обмене.")

        connection.execute(
            "INSERT INTO user_card_frames (user_id, user_cosmetic_item_id, user_card_id) VALUES (?, ?, ?)",
            (user_id, user_cosmetic_item_id, user_card_id),
        )
        connection.commit()


async def unbind_frame_from_card(user_id: int, user_card_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM user_card_frames WHERE user_id = ? AND user_card_id = ?",
            (user_id, user_card_id),
        )
        connection.commit()


async def unbind_frame_copy(user_id: int, user_cosmetic_item_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM user_card_frames WHERE user_id = ? AND user_cosmetic_item_id = ?",
            (user_id, user_cosmetic_item_id),
        )
        connection.commit()


async def get_card_frame_for_card(user_card_id: int) -> CardFrameBinding | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT ucf.id, ucf.user_cosmetic_item_id, ucf.user_card_id,
                   wci.title AS frame_title, wci.image_path AS frame_image_path
            FROM user_card_frames ucf
            JOIN user_cosmetic_items uci ON uci.id = ucf.user_cosmetic_item_id
            JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
            WHERE ucf.user_card_id = ?
            """,
            (user_card_id,),
        ).fetchone()
    if row is None:
        return None
    return CardFrameBinding(
        id=int(row["id"]),
        user_cosmetic_item_id=int(row["user_cosmetic_item_id"]),
        user_card_id=int(row["user_card_id"]),
        frame_title=row["frame_title"],
        frame_image_path=row["frame_image_path"],
    )


async def get_frame_paths_for_cards(user_card_ids: list[int]) -> dict[int, str]:
    clean_ids = sorted({int(value) for value in user_card_ids if int(value) > 0})
    if not clean_ids:
        return {}
    placeholders = ",".join("?" for _ in clean_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT ucf.user_card_id, wci.image_path
            FROM user_card_frames ucf
            JOIN user_cosmetic_items uci ON uci.id = ucf.user_cosmetic_item_id
            JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
            WHERE ucf.user_card_id IN ({placeholders})
            """,
            clean_ids,
        ).fetchall()
    return {int(row["user_card_id"]): row["image_path"] for row in rows if row["image_path"]}


async def list_owned_card_frames(user_id: int) -> list[dict]:
    placeholders = ",".join("?" for _ in CARD_FRAME_TYPES)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT uci.id AS owned_id, wci.title AS title, wci.rarity, wci.image_path,
                   ucf.user_card_id AS bound_card_id, cards.name AS bound_card_name,
                   cards.overall AS bound_card_overall, user_cards.lineup_slot AS bound_lineup_slot
            FROM user_cosmetic_items uci
            JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
            LEFT JOIN user_card_frames ucf ON ucf.user_cosmetic_item_id = uci.id
            LEFT JOIN user_cards ON user_cards.id = ucf.user_card_id
            LEFT JOIN cards ON cards.id = user_cards.card_id
            WHERE uci.owner_id = ? AND uci.type IN ({placeholders})
            ORDER BY uci.created_at DESC, uci.id DESC
            """,
            (user_id, *CARD_FRAME_TYPES),
        ).fetchall()
    return [dict(row) for row in rows]
