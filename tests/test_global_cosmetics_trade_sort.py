from __future__ import annotations

import pytest

from app.database.db import get_connection
from app.services.card_sorting import set_user_card_sort_order
from app.services.community import (
    accept_trade_offer,
    create_trade_offer,
    get_available_user_cards_page,
    get_available_user_cosmetics_page,
    get_trade_offer_profile,
)
from app.services.ranked_common import RankedError
from app.services.ranked_cosmetics import bind_frame_to_card


def _create_user(connection, telegram_id: int, nickname: str) -> int:
    return int(connection.execute(
        "INSERT INTO users (telegram_id, nickname) VALUES (?, ?)",
        (telegram_id, nickname),
    ).lastrowid)


def _create_card(connection, collection_id: int, *, key: str, name: str, overall: int) -> int:
    return int(connection.execute(
        """
        INSERT INTO cards (
            name, player_key, position, overall, team, country,
            collection_id, rarity, image_path, salary, active
        ) VALUES (?, ?, 'F', ?, 'Test', 'Test', ?, 'Common', 'assets/uploads/test.png', 0, 1)
        """,
        (name, key, overall, collection_id),
    ).lastrowid)


@pytest.mark.asyncio
async def test_one_frame_copy_binds_to_only_one_card(stronghold_db):
    with get_connection() as connection:
        user_id = _create_user(connection, 91_001, "FrameOwner")
        collection_id = int(connection.execute("SELECT id FROM collections LIMIT 1").fetchone()["id"])
        first_card_id = _create_card(connection, collection_id, key="frame-copy-a", name="A", overall=80)
        second_card_id = _create_card(connection, collection_id, key="frame-copy-b", name="B", overall=90)
        first_user_card = int(connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')",
            (user_id, first_card_id),
        ).lastrowid)
        second_user_card = int(connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')",
            (user_id, second_card_id),
        ).lastrowid)
        catalog_id = int(connection.execute(
            """
            INSERT INTO war2_cosmetic_items (type, code, title, rarity, image_path)
            VALUES ('CARD_FRAME', 'test-frame-copy', 'Test Frame', 'Epic', 'assets/uploads/test-frame.png')
            """
        ).lastrowid)
        first_copy = int(connection.execute(
            """
            INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source)
            VALUES (?, ?, 'CARD_FRAME', 'Epic', 'test')
            """,
            (user_id, catalog_id),
        ).lastrowid)
        second_copy = int(connection.execute(
            """
            INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source)
            VALUES (?, ?, 'CARD_FRAME', 'Epic', 'test')
            """,
            (user_id, catalog_id),
        ).lastrowid)
        connection.commit()

    await bind_frame_to_card(user_id, first_copy, first_user_card)
    with pytest.raises(RankedError) as exc_info:
        await bind_frame_to_card(user_id, first_copy, second_user_card)
    assert exc_info.value.code == "CARD_FRAME_ALREADY_BOUND"

    await bind_frame_to_card(user_id, second_copy, second_user_card)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT user_cosmetic_item_id, user_card_id FROM user_card_frames WHERE user_id = ? ORDER BY user_cosmetic_item_id",
            (user_id,),
        ).fetchall()
    assert [(int(row["user_cosmetic_item_id"]), int(row["user_card_id"])) for row in rows] == [
        (first_copy, first_user_card),
        (second_copy, second_user_card),
    ]


@pytest.mark.asyncio
async def test_cosmetic_only_trade_transfers_concrete_copies(stronghold_db):
    with get_connection() as connection:
        creator_id = _create_user(connection, 91_002, "Creator")
        accepter_id = _create_user(connection, 91_003, "Accepter")
        frame_catalog = int(connection.execute(
            "INSERT INTO war2_cosmetic_items (type, code, title, rarity, image_path) VALUES ('CARD_FRAME', 'trade-frame', 'Trade Frame', 'Rare', 'frame.png')"
        ).lastrowid)
        prefix_catalog = int(connection.execute(
            "INSERT INTO war2_cosmetic_items (type, code, title, rarity, badge_text) VALUES ('NICK_BADGE', 'trade-prefix', 'Trade Prefix', 'Epic', 'MVP')"
        ).lastrowid)
        offered_copy = int(connection.execute(
            "INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source) VALUES (?, ?, 'CARD_FRAME', 'Rare', 'test')",
            (creator_id, frame_catalog),
        ).lastrowid)
        wanted_copy = int(connection.execute(
            "INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source) VALUES (?, ?, 'NICK_BADGE', 'Epic', 'test')",
            (accepter_id, prefix_catalog),
        ).lastrowid)
        connection.commit()

    result = await create_trade_offer(
        creator_user_id=creator_id,
        offered_user_card_ids=[],
        offered_user_cosmetic_ids=[offered_copy],
        wanted_type="cards",
        wanted_asset_type="cosmetics",
        wanted_cosmetic_item_ids=[prefix_catalog],
    )
    assert result.ok
    offer = await get_trade_offer_profile(int(result.offer_id))
    assert offer is not None
    assert [item.id for item in offer.offered_cosmetics] == [offered_copy]
    assert [item.id for item, _ in offer.wanted_cosmetics] == [prefix_catalog]

    accepted = await accept_trade_offer(int(result.offer_id), accepter_id)
    assert accepted.ok
    with get_connection() as connection:
        assert int(connection.execute(
            "SELECT owner_id FROM user_cosmetic_items WHERE id = ?", (offered_copy,)
        ).fetchone()["owner_id"]) == accepter_id
        assert int(connection.execute(
            "SELECT owner_id FROM user_cosmetic_items WHERE id = ?", (wanted_copy,)
        ).fetchone()["owner_id"]) == creator_id


@pytest.mark.asyncio
async def test_bound_cosmetics_are_not_tradable_and_card_sort_is_global(stronghold_db):
    with get_connection() as connection:
        user_id = _create_user(connection, 91_004, "Sorter")
        collection_id = int(connection.execute("SELECT id FROM collections LIMIT 1").fetchone()["id"])
        weak_id = _create_card(connection, collection_id, key="sort-weak", name="Weak", overall=70)
        strong_id = _create_card(connection, collection_id, key="sort-strong", name="Strong", overall=99)
        weak_copy = int(connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, weak_id)
        ).lastrowid)
        connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'test')", (user_id, strong_id)
        )
        frame_catalog = int(connection.execute(
            "INSERT INTO war2_cosmetic_items (type, code, title, rarity, image_path) VALUES ('CARD_FRAME', 'bound-frame', 'Bound Frame', 'Rare', 'frame.png')"
        ).lastrowid)
        bound_copy = int(connection.execute(
            "INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source) VALUES (?, ?, 'CARD_FRAME', 'Rare', 'test')",
            (user_id, frame_catalog),
        ).lastrowid)
        free_copy = int(connection.execute(
            "INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source) VALUES (?, ?, 'CARD_FRAME', 'Rare', 'test')",
            (user_id, frame_catalog),
        ).lastrowid)
        connection.commit()

    await bind_frame_to_card(user_id, bound_copy, weak_copy)
    cosmetics = await get_available_user_cosmetics_page(user_id, per_page=20)
    assert [item.id for item in cosmetics.items] == [free_copy]

    await set_user_card_sort_order(user_id, "ovr_asc")
    cards = await get_available_user_cards_page(user_id, per_page=20)
    assert [item.overall for item in cards.cards] == [70, 99]

    await set_user_card_sort_order(user_id, "ovr_desc")
    cards = await get_available_user_cards_page(user_id, per_page=20)
    assert [item.overall for item in cards.cards] == [99, 70]
