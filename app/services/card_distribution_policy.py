"""Central distribution policy for collections that must only be issued by admins.

`Leaders` is an admin-only collection: existing owned copies remain valid and can
still be moved by ownership-transfer mechanics, but automated acquisition sources
(shops, packs, passes, event rewards, free cards, etc.) must never mint a new copy.
"""

from __future__ import annotations

import json
import sqlite3

ADMIN_ONLY_COLLECTION_NAMES = frozenset({"leaders"})
ADMIN_ONLY_COLLECTION_CODES = frozenset({"leaders"})


def _norm(value: object | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_admin_only_collection(*, name: object | None = None, code: object | None = None) -> bool:
    return _norm(name) in ADMIN_ONLY_COLLECTION_NAMES or _norm(code) in ADMIN_ONLY_COLLECTION_CODES




def is_admin_only_collection_id(connection: sqlite3.Connection, collection_id: int | None) -> bool:
    if collection_id is None:
        return False
    row = connection.execute(
        "SELECT name, code FROM collections WHERE id = ?", (int(collection_id),)
    ).fetchone()
    return bool(row and is_admin_only_collection(name=row["name"], code=row["code"]))

def is_admin_only_card(connection: sqlite3.Connection, card_id: int) -> bool:
    row = connection.execute(
        """
        SELECT collections.name, collections.code
        FROM cards
        JOIN collections ON collections.id = cards.collection_id
        WHERE cards.id = ?
        """,
        (card_id,),
    ).fetchone()
    return bool(row and is_admin_only_collection(name=row["name"], code=row["code"]))


def admin_only_card_ids(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute(
        """
        SELECT cards.id
        FROM cards
        JOIN collections ON collections.id = cards.collection_id
        WHERE LOWER(TRIM(collections.name)) = 'leaders'
           OR LOWER(TRIM(COALESCE(collections.code, ''))) = 'leaders'
        """
    ).fetchall()
    return {int(row["id"]) for row in rows}


def cleanup_admin_only_distribution(connection: sqlite3.Connection) -> dict[str, int]:
    """Remove/deactivate existing automated distribution paths for admin-only cards.

    This is intentionally idempotent and keeps already-owned user_cards untouched.
    It does not block user-to-user ownership transfers of an existing copy.
    """
    ids = admin_only_card_ids(connection)
    if not ids:
        return {
            "pack_cards": 0, "pack_slots": 0, "black_market": 0, "black_market_rotations": 0,
            "stronghold_products": 0, "ranked_pack_cards": 0, "starter_kit": 0,
            "ranked_pass_rewards": 0, "hockey_pass_rewards": 0, "events": 0,
            "reward_settings": 0,
        }

    placeholders = ",".join("?" for _ in ids)
    params = tuple(sorted(ids))

    # Mark as exclusive too, so generic Clan War bot/draft pools cannot pull it.
    connection.execute(
        """
        UPDATE collections
        SET is_exclusive = 1
        WHERE LOWER(TRIM(name)) = 'leaders'
           OR LOWER(TRIM(COALESCE(code, ''))) = 'leaders'
        """
    )

    deleted_pack_cards = connection.execute(
        f"DELETE FROM pack_cards WHERE card_id IN ({placeholders})", params
    ).rowcount

    admin_collection_ids = [
        int(row["id"]) for row in connection.execute(
            """
            SELECT id FROM collections
            WHERE LOWER(TRIM(name)) = 'leaders'
               OR LOWER(TRIM(COALESCE(code, ''))) = 'leaders'
            """
        ).fetchall()
    ]
    disabled_pack_slots = 0
    if admin_collection_ids:
        collection_placeholders = ",".join("?" for _ in admin_collection_ids)
        disabled_pack_slots = connection.execute(
            f"""
            UPDATE pack_slots
            SET active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE active != 0
              AND (collection_id IN ({collection_placeholders})
                   OR special_collection_id IN ({collection_placeholders}))
            """,
            (*admin_collection_ids, *admin_collection_ids),
        ).rowcount

    deleted_ranked_pack_cards = connection.execute(
        f"DELETE FROM ranked_pack_cards WHERE card_id IN ({placeholders})", params
    ).rowcount

    deleted_starter_kit = connection.execute(
        f"DELETE FROM starter_kit_cards WHERE card_id IN ({placeholders})", params
    ).rowcount

    disabled_ranked_pass_rewards = connection.execute(
        f"UPDATE ranked_pass_rewards SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE card_id IN ({placeholders}) AND active != 0", params
    ).rowcount
    disabled_hockey_pass_rewards = connection.execute(
        f"UPDATE hockey_pass_rewards SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE card_id IN ({placeholders}) AND active != 0", params
    ).rowcount
    disabled_events = connection.execute(
        f"UPDATE events SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE reward_type = 'card' AND reward_card_id IN ({placeholders}) AND active != 0", params
    ).rowcount
    disabled_reward_settings = connection.execute(
        f"UPDATE reward_settings SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE card_id IN ({placeholders}) AND active != 0", params
    ).rowcount

    black_market_rows = connection.execute(
        f"""
        UPDATE black_market_pool_items
        SET active = 0, updated_at = CURRENT_TIMESTAMP
        WHERE item_type = 'card' AND card_id IN ({placeholders}) AND active != 0
        """,
        params,
    ).rowcount

    # Already materialized storefront slots must disappear immediately rather than
    # surviving until tomorrow's rotation.
    black_market_rotation_rows = connection.execute(
        f"""
        UPDATE black_market_user_rotation_items
        SET item_status = 'REMOVED', remaining_personal_stock = 0, updated_at = CURRENT_TIMESTAMP
        WHERE item_type = 'card'
          AND item_reference_id IN ({placeholders})
          AND item_status != 'REMOVED'
        """,
        params,
    ).rowcount

    # Stronghold store products keep contents as JSON. Disable any product that
    # directly contains a Leaders card. Packs are already sanitized above.
    disabled_products = 0
    rows = connection.execute(
        "SELECT id, contents, active FROM stronghold_store_products"
    ).fetchall()
    for row in rows:
        try:
            contents = json.loads(row["contents"] or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        contains_admin_only = any(
            item.get("type") == "card" and int(item.get("card_id") or 0) in ids
            for item in contents
            if isinstance(item, dict)
        )
        if contains_admin_only and bool(row["active"]):
            connection.execute(
                "UPDATE stronghold_store_products SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(row["id"]),),
            )
            disabled_products += 1

    return {
        "pack_cards": int(deleted_pack_cards or 0),
        "pack_slots": int(disabled_pack_slots or 0),
        "black_market": int(black_market_rows or 0),
        "black_market_rotations": int(black_market_rotation_rows or 0),
        "stronghold_products": disabled_products,
        "ranked_pack_cards": int(deleted_ranked_pack_cards or 0),
        "starter_kit": int(deleted_starter_kit or 0),
        "ranked_pass_rewards": int(disabled_ranked_pass_rewards or 0),
        "hockey_pass_rewards": int(disabled_hockey_pass_rewards or 0),
        "events": int(disabled_events or 0),
        "reward_settings": int(disabled_reward_settings or 0),
    }
