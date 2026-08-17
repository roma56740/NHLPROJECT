"""Shared OVR sorting preference for every player-facing card list.

A user chooses the order once and the same preference is reused by collection,
lineup pickers, trades, cosmetics binding and other card selectors.  This avoids
independent, contradictory sort state in every handler.
"""
from __future__ import annotations

from app.database.db import get_connection

SORT_OVR_DESC = "ovr_desc"
SORT_OVR_ASC = "ovr_asc"
VALID_SORT_ORDERS = {SORT_OVR_DESC, SORT_OVR_ASC}
DEFAULT_SORT_ORDER = SORT_OVR_DESC


def normalize_sort_order(value: str | None) -> str:
    return value if value in VALID_SORT_ORDERS else DEFAULT_SORT_ORDER


def order_by_overall(sort_order: str | None, *, card_alias: str = "cards", tie_breaker: str = "id") -> str:
    direction = "ASC" if normalize_sort_order(sort_order) == SORT_OVR_ASC else "DESC"
    return f"{card_alias}.overall {direction}, {card_alias}.name ASC, {card_alias}.{tie_breaker} DESC"


async def get_user_card_sort_order(user_id: int) -> str:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT sort_order FROM user_card_view_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return normalize_sort_order(row["sort_order"] if row else None)


async def set_user_card_sort_order(user_id: int, sort_order: str) -> str:
    normalized = normalize_sort_order(sort_order)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_card_view_preferences (user_id, sort_order)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, normalized),
        )
        connection.commit()
    return normalized


def sort_label(sort_order: str | None) -> str:
    return "слабые → сильные" if normalize_sort_order(sort_order) == SORT_OVR_ASC else "сильные → слабые"
