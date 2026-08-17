"""Сквозной smoke-test THE STRONGHOLD против реального сервисного слоя (без Telegram).

Эквивалент "smoke flow" из исходного ТЗ (открыть событие -> кошелёк -> preview ->
Upgrade -> Fortress -> Missions -> Store), адаптированный под отсутствие REST API:
вызывает те же async-сервисы, что и Telegram-хендлеры, на отдельной временной БД —
существующие данные не трогает.

Использование:
    python scripts/stronghold_smoke_test.py

Код возврата 0 — всё в порядке, 1 — шаг упал.
"""

import asyncio
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os

os.environ.setdefault("BOT_TOKEN", "smoke-test-token")
os.environ.setdefault("ADMIN_IDS", "1")


async def run() -> bool:
    import app.database.db as db_module
    from app.database.db import get_connection, init_database

    tmp_path = Path(tempfile.mktemp(suffix=".sqlite3"))
    db_module.DATABASE_PATH = tmp_path

    steps_ok = True

    def step(name: str, ok: bool, note: str = "") -> None:
        nonlocal steps_ok
        print(f"[{'OK' if ok else 'FAIL'}] {name}{f' — {note}' if note else ''}")
        steps_ok = steps_ok and ok

    try:
        await init_database()
        step("init_database (миграции + сид)", True)

        from aiogram.types import User as TelegramUser

        from app.services.stronghold_common import STRONGHOLD_SLUG, get_active_event
        from app.services.stronghold_endless import get_status as get_endless_status
        from app.services.stronghold_fortress import list_fortresses, play_fortress_match
        from app.services.stronghold_missions import claim_mission, list_missions
        from app.services.stronghold_season_track import get_track
        from app.services.stronghold_store import list_products, purchase
        from app.services.stronghold_upgrade import confirm_upgrade, ensure_starter_card, preview_upgrade
        from app.services.stronghold_wallet import credit, get_wallet
        from app.services.users import register_or_update_player

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE stronghold_events
                SET status = 'ACTIVE', starts_at = datetime('now', '-1 day'),
                    ends_at = datetime('now', '+29 days'), grace_ends_at = datetime('now', '+36 days')
                WHERE slug = ?
                """,
                (STRONGHOLD_SLUG,),
            )
            connection.commit()
        step("активировать событие (ACTIVE)", True)

        event = await get_active_event()
        step("получить событие", event is not None and event.status == "ACTIVE")

        telegram_user = TelegramUser(id=900_100_001, is_bot=False, first_name="Smoke Test")
        profile = await register_or_update_player(telegram_user)
        step("зарегистрировать игрока", profile is not None)

        wallet = await get_wallet(profile.id)
        step("получить кошелёк", wallet.coins >= 0 and wallet.fortress_tokens >= 0)

        await ensure_starter_card(profile.id)
        with get_connection() as connection:
            heiskanen_row = connection.execute(
                "SELECT user_cards.id AS uc_id FROM user_cards JOIN cards ON cards.id = user_cards.card_id WHERE user_cards.user_id = ? AND cards.player_key = 'miro-heiskanen'",
                (profile.id,),
            ).fetchone()
        step("стартовая карта Miro Heiskanen 92 выдана", heiskanen_row is not None)
        user_card_id = int(heiskanen_row["uc_id"])

        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            credit(connection, user_id=profile.id, event_id=event.id, currency_code="fortress_token", amount=1000, reason="smoke_test")
            credit(connection, user_id=profile.id, event_id=event.id, currency_code="coins", amount=10_000_000, reason="smoke_test")
            connection.commit()
        step("пополнить баланс для теста", True)

        preview = await preview_upgrade(profile.id, user_card_id)
        step("Upgrade preview", preview.blocking_reason is None, f"стоимость {preview.ft_cost} FT / {preview.coins_cost} Coins")

        result = await confirm_upgrade(profile.id, user_card_id, request_id="smoke-upgrade-1")
        step("Upgrade confirm", result.success, f"новый OVR {result.to_overall}")

        fortresses = await list_fortresses(profile.id)
        step("получить список Fortress", len(fortresses) == 15)

        from app.services.lineup import set_lineup_card

        with get_connection() as connection:
            collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
            filler_ids = []
            for slot, position in [("G", "G"), ("D2", "D"), ("F1", "F"), ("F2", "F"), ("F3", "F")]:
                cursor = connection.execute(
                    "INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active) VALUES (?, ?, ?, 60, 'T', 'C', ?, 'Common', 'x.png', 100, 1)",
                    (f"Smoke {slot}", f"smoke-{slot.lower()}", position, collection["id"]),
                )
                filler_ids.append((slot, cursor.lastrowid))
            connection.commit()
        await set_lineup_card(profile.id, "D1", user_card_id)
        for slot, card_id in filler_ids:
            with get_connection() as connection:
                cursor = connection.execute("INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'smoke_test')", (profile.id, card_id))
                connection.commit()
            await set_lineup_card(profile.id, slot, cursor.lastrowid)
        step("собрать состав", True)

        fortress1_matches = fortresses[0]
        from app.services.stronghold_fortress import get_fortress

        fortress_detail = await get_fortress(profile.id, fortress1_matches.id)
        first_match = fortress_detail.matches[0]
        with get_connection() as connection:
            connection.execute("UPDATE stronghold_fortress_matches SET opponent_ovr = 1 WHERE id = ?", (first_match.id,))
            connection.commit()
        match_result = await play_fortress_match(900_100_001, profile.id, first_match.id)
        step("сыграть матч Fortress", match_result.success)

        missions = await list_missions(profile.id, "DAILY")
        step("получить Missions", len(missions) > 0)

        season_track = await get_track(profile.id)
        step("получить Season Track", season_track is not None)

        endless_status = await get_endless_status(profile.id)
        step("получить статус Endless Siege", endless_status is not None)

        products = await list_products(profile.id, "Featured")
        step("получить Event Store", len(products) > 0)
        if products:
            purchase_result = await purchase(profile.id, products[0].id, request_id="smoke-purchase-1")
            step("покупка в Event Store", purchase_result.success)

        from app.services.stronghold_health import get_health_status

        health = await get_health_status()
        step("healthcheck", health.ok)

    except Exception:
        traceback.print_exc()
        steps_ok = False
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    return steps_ok


if __name__ == "__main__":
    ok = asyncio.run(run())
    print("\nSMOKE TEST: " + ("PASSED" if ok else "FAILED"))
    sys.exit(0 if ok else 1)
