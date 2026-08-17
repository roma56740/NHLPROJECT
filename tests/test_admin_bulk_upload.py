from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.database.db import get_connection
from app.services import admin_bulk_upload as bulk


def _source(tmp_path: Path, rows: list[dict], name: str = "manifest.json") -> bulk.PreparedSource:
    path = tmp_path / name
    path.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    return bulk.PreparedSource(path, name, None)


@pytest.mark.asyncio
async def test_bulk_card_upsert_and_atomic_validation(stronghold_db, tmp_path):
    collection = bulk.get_target("collections")
    assert collection is not None
    bulk.apply_import(
        collection,
        _source(tmp_path, [{"code": "bulk-test", "name": "Bulk Test", "active": 1}], "collections.json"),
    )

    cards = bulk.get_target("cards")
    assert cards is not None
    first = _source(
        tmp_path,
        [{
            "name": "Bulk Player",
            "player_key": "bulk-player",
            "position": "F",
            "overall": 95,
            "team": "Bulk Team",
            "country": "Canada",
            "collection_code": "bulk-test",
            "rarity": "Epic",
            "salary": 5_000_000,
        }],
        "cards.json",
    )
    result = bulk.apply_import(cards, first)
    assert result.inserted == 1

    update = _source(
        tmp_path,
        [{
            "name": "Bulk Player",
            "player_key": "bulk-player",
            "position": "F",
            "overall": 95,
            "team": "Bulk Team",
            "country": "Canada",
            "collection_code": "bulk-test",
            "rarity": "Epic",
            "salary": 7_000_000,
        }],
        "cards-update.json",
    )
    result = bulk.apply_import(cards, update)
    assert result.updated == 1

    with get_connection() as connection:
        row = connection.execute("SELECT salary FROM cards WHERE player_key = 'bulk-player'").fetchone()
        assert int(row["salary"]) == 7_000_000
        before = int(connection.execute("SELECT COUNT(*) AS c FROM cards").fetchone()["c"])

    invalid = _source(
        tmp_path,
        [
            {
                "name": "Valid Looking",
                "player_key": "valid-looking",
                "position": "F",
                "overall": 90,
                "team": "Team",
                "country": "Canada",
                "collection_code": "bulk-test",
                "rarity": "Epic",
            },
            {
                "name": "Broken",
                "position": "INVALID",
                "overall": 95,
                "team": "Team",
                "country": "Canada",
                "collection_code": "bulk-test",
                "rarity": "Epic",
            },
        ],
        "invalid.json",
    )
    preview = bulk.build_preview(cards, invalid)
    assert len(preview.errors) == 1
    with pytest.raises(ValueError):
        bulk.apply_import(cards, invalid)

    with get_connection() as connection:
        after = int(connection.execute("SELECT COUNT(*) AS c FROM cards").fetchone()["c"])
        assert after == before


@pytest.mark.asyncio
async def test_bulk_wallet_pack_and_cosmetic_grants(stronghold_db, tmp_path):
    with get_connection() as connection:
        user = connection.execute("SELECT id, telegram_id FROM users ORDER BY id LIMIT 1").fetchone()
        if user is None:
            cursor = connection.execute("INSERT INTO users(telegram_id, nickname) VALUES(880001, 'Bulk User')")
            user_id = int(cursor.lastrowid)
            telegram_id = 880001
        else:
            user_id = int(user["id"])
            telegram_id = int(user["telegram_id"])
        pack_cursor = connection.execute(
            "INSERT INTO packs(code, name, price_currency_code, price_amount) VALUES('bulk-pack', 'Bulk Pack', 'coins', 0)"
        )
        pack_id = int(pack_cursor.lastrowid)
        cosmetic_cursor = connection.execute(
            "INSERT INTO war2_cosmetic_items(type, code, title, rarity) VALUES('CARD_FRAME', 'bulk-frame', 'Bulk Frame', 'Epic')"
        )
        cosmetic_id = int(cosmetic_cursor.lastrowid)
        connection.commit()

    wallet = bulk.get_target("wallet_adjustments")
    packs = bulk.get_target("pack_grants")
    cosmetics = bulk.get_target("cosmetic_grants")
    assert wallet and packs and cosmetics

    bulk.apply_import(wallet, _source(tmp_path, [{"telegram_id": telegram_id, "currency_code": "coins", "operation": "add", "amount": 1234}], "wallet.json"))
    bulk.apply_import(packs, _source(tmp_path, [{"telegram_id": telegram_id, "pack_code": "bulk-pack", "quantity": 3}], "packs.json"))
    bulk.apply_import(cosmetics, _source(tmp_path, [{"telegram_id": telegram_id, "cosmetic_code": "bulk-frame", "quantity": 2}], "cosmetics.json"))

    with get_connection() as connection:
        balance = connection.execute("SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = 'coins'", (user_id,)).fetchone()
        owned_pack = connection.execute("SELECT quantity FROM user_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)).fetchone()
        owned_cosmetics = connection.execute("SELECT COUNT(*) AS c FROM user_cosmetic_items WHERE owner_id = ? AND cosmetic_item_id = ?", (user_id, cosmetic_id)).fetchone()
    assert int(balance["amount"]) >= 1234
    assert int(owned_pack["quantity"]) == 3
    assert int(owned_cosmetics["c"]) == 2


def test_bulk_zip_assets_are_safe_and_copied(stronghold_db, tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(bulk, "UPLOADS_ROOT", uploads)

    zip_path = tmp_path / "cards.zip"
    manifest = {
        "rows": [{
            "name": "ZIP Player",
            "player_key": "zip-player",
            "position": "D",
            "overall": 91,
            "team": "ZIP Team",
            "country": "Sweden",
            "collection_code": "free-cards",
            "rarity": "Rare",
            "asset_file": "assets/zip-player.png",
        }]
    }
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        archive.writestr("assets/zip-player.png", b"fake-png-content")

    prepared = bulk.prepare_source(zip_path, tmp_path / "job", zip_path.name)
    target = bulk.get_target("cards")
    assert target is not None
    preview = bulk.build_preview(target, prepared)
    assert not preview.errors
    result = bulk.apply_import(target, prepared)
    assert result.inserted == 1

    with get_connection() as connection:
        row = connection.execute("SELECT image_path FROM cards WHERE player_key = 'zip-player'").fetchone()
    assert row is not None
    assert Path(row["image_path"]).exists()
