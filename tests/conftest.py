import os
import uuid

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "999999999")

import pytest
import pytest_asyncio
from aiogram.types import User as TelegramUser

import app.database.db as db_module
from app.database.db import get_connection, init_database
from app.services.stronghold_common import STRONGHOLD_SLUG
from app.services.users import register_or_update_player

_next_telegram_id = 1_000_000


def business_date_today() -> str:
    """Календарная business_date "сегодня", вычисленная РЕЛЯТИВНО в момент вызова —
    той же функцией, что использует прод-код (app.services.black_market_common.
    business_date()). Раньше BLACK MARKET-тесты хардкодили конкретную дату
    ("2026-07-29"), из-за чего purchase()/list_storefront() (которые сверяют
    business_date() РЕАЛЬНОГО времени с датой сохранённой ротации) начинали падать с
    ROTATION_EXPIRED в любой день после этой даты. Вызывать эту функцию вместо
    хардкода — тесты остаются корректными в любой день запуска."""
    from app.services.black_market_common import business_date

    return business_date()


def business_date_offset(days: int) -> str:
    """business_date со сдвигом в днях относительно реального "сейчас" — для тестов,
    которым нужны ДВЕ разные календарные даты (например "другой день -> другая
    ротация"), без хардкода конкретных календарных чисел."""
    from datetime import datetime, timedelta, timezone

    from app.services.black_market_common import business_date

    return business_date(datetime.now(timezone.utc) + timedelta(days=days))


@pytest.fixture(scope="session")
def app_router():
    """setup_routers() присоединяет module-level singleton-роутеры (start.router,
    black_market.router, ...) к новому дереву Router — aiogram запрещает повторно
    прикреплять один и тот же router-объект к другому родителю (RuntimeError "Router
    is already attached"). Поэтому setup_routers() можно вызвать только ОДИН раз за
    весь процесс тестов — этот session-scoped фикстур гарантирует именно это, вместо
    того чтобы каждый тест дёргал setup_routers() самостоятельно."""
    from app.handlers import setup_routers

    return setup_routers()


@pytest_asyncio.fixture
async def stronghold_db(tmp_path, monkeypatch):
    """Свежая, полностью реальная SQLite БД (схема + миграции + сид) на каждый тест."""
    db_path = tmp_path / f"stronghold_test_{uuid.uuid4().hex}.sqlite3"
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    await init_database()

    # BLACK MARKET хранит process-local кэш витрины (app/services/black_market_store.py),
    # ключ которого включает users.id — а он переиспользуется между тестами (autoincrement
    # начинается заново в каждой свежей временной БД). Без очистки кэш из предыдущего теста
    # мог бы "утечь" в текущий и указывать на несуществующие в новой БД rotation_item_id.
    from app.services.black_market_store import _storefront_cache

    _storefront_cache.clear()

    yield db_path

    _storefront_cache.clear()


@pytest_asyncio.fixture
async def active_event(stronghold_db):
    """Переводит THE STRONGHOLD в ACTIVE с 30-дневным окном + 7-дневным Grace Period."""
    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events WHERE slug = ?", (STRONGHOLD_SLUG,)).fetchone()
        event_id = int(event_row["id"])
        connection.execute(
            """
            UPDATE stronghold_events
            SET status = 'ACTIVE',
                starts_at = datetime('now', '-1 day'),
                ends_at = datetime('now', '+29 days'),
                grace_ends_at = datetime('now', '+36 days')
            WHERE id = ?
            """,
            (event_id,),
        )
        connection.commit()
    return event_id


async def create_test_user(nickname: str) -> int:
    global _next_telegram_id
    _next_telegram_id += 1
    telegram_user = TelegramUser(id=_next_telegram_id, is_bot=False, first_name=nickname)
    profile = await register_or_update_player(telegram_user)
    return profile.id


def _get_or_create_filler_card(connection, *, player_key: str, position: str, salary: int) -> int:
    collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
    collection_id = int(collection["id"])
    row = connection.execute("SELECT id FROM cards WHERE player_key = ?", (player_key,)).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
        VALUES (?, ?, ?, 60, 'Test Team', 'Test Country', ?, 'Common', 'assets/uploads/test.png', ?, 1)
        """,
        (player_key.title(), player_key, position, collection_id, salary),
    )
    return int(cursor.lastrowid)


async def give_and_slot_card(user_id: int, card_id: int, slot_code: str) -> int:
    from app.services.lineup import set_lineup_card

    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked) VALUES (?, ?, 'test', 0, 0)",
            (user_id, card_id),
        )
        user_card_id = int(cursor.lastrowid)
        connection.commit()
    result = await set_lineup_card(user_id, slot_code, user_card_id)
    assert result.success, result.message
    return user_card_id


async def build_full_stronghold_lineup(user_id: int) -> int:
    """Собирает полный состав из 6 слотов, где D1 = карта THE STRONGHOLD (Miro Heiskanen 92).

    Возвращает user_cards.id карты Heiskanen (для апгрейд-тестов).
    """
    from app.services.stronghold_upgrade import ensure_starter_card

    await ensure_starter_card(user_id)

    with get_connection() as connection:
        heiskanen_row = connection.execute(
            """
            SELECT user_cards.id AS user_card_id
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            WHERE user_cards.user_id = ? AND cards.player_key = 'miro-heiskanen'
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        assert heiskanen_row is not None, "стартовая карта Heiskanen не выдана"
        heiskanen_user_card_id = int(heiskanen_row["user_card_id"])

        filler_ids = {
            "goalie": _get_or_create_filler_card(connection, player_key=f"filler-g-{user_id}", position="G", salary=100),
            "d2": _get_or_create_filler_card(connection, player_key=f"filler-d-{user_id}", position="D", salary=100),
            "f1": _get_or_create_filler_card(connection, player_key=f"filler-f1-{user_id}", position="F", salary=100),
            "f2": _get_or_create_filler_card(connection, player_key=f"filler-f2-{user_id}", position="F", salary=100),
            "f3": _get_or_create_filler_card(connection, player_key=f"filler-f3-{user_id}", position="F", salary=100),
        }
        connection.commit()

    from app.services.lineup import set_lineup_card

    result = await set_lineup_card(user_id, "D1", heiskanen_user_card_id)
    assert result.success, result.message
    await give_and_slot_card(user_id, filler_ids["goalie"], "G")
    await give_and_slot_card(user_id, filler_ids["d2"], "D2")
    await give_and_slot_card(user_id, filler_ids["f1"], "F1")
    await give_and_slot_card(user_id, filler_ids["f2"], "F2")
    await give_and_slot_card(user_id, filler_ids["f3"], "F3")

    return heiskanen_user_card_id


def get_balance(user_id: int, currency_code: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?", (user_id, currency_code)
        ).fetchone()
    return int(row["amount"]) if row else 0


def grant_balance(user_id: int, currency_code: str, amount: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO currency_balances (user_id, currency_code, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, currency_code) DO UPDATE SET amount = amount + excluded.amount
            """,
            (user_id, currency_code, amount),
        )
        connection.commit()


@pytest_asyncio.fixture
async def black_market_pool(stronghold_db):
    """Единый master pool из 4 предметов (currency/pack/card/cosmetic), все Common —
    веса редкости перекрыты на 100% Common, чтобы генерация была детерминирована без
    гонки редкостей в тестах. slots_count=4 ровно под 4 предмета (без дублей по умолчанию)."""
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")

        pack_cursor = connection.execute(
            "INSERT INTO packs (code, name, price_currency_code, price_amount) VALUES ('bm-test-pack', 'BM Test Pack', 'coins', 0)"
        )
        pack_id = int(pack_cursor.lastrowid)

        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        card_cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES ('BM Test Card', 'bm-test-card', 'F', 70, 'Test Team', 'Test Country', ?, 'Common', 'assets/uploads/test.png', 0, 1)
            """,
            (int(collection["id"]),),
        )
        card_id = int(card_cursor.lastrowid)

        cosmetic_cursor = connection.execute(
            "INSERT INTO war2_cosmetic_items (type, code, title, rarity) VALUES ('FRAME', 'bm-test-frame', 'BM Test Frame', 'Common')"
        )
        cosmetic_id = int(cosmetic_cursor.lastrowid)

        specs = {
            "currency": {"currency_code": "coins", "amount": 100, "pack_id": None, "card_id": None, "cosmetic_item_id": None},
            "pack": {"currency_code": None, "amount": 1, "pack_id": pack_id, "card_id": None, "cosmetic_item_id": None},
            "card": {"currency_code": None, "amount": 1, "pack_id": None, "card_id": card_id, "cosmetic_item_id": None},
            "cosmetic": {"currency_code": None, "amount": 1, "pack_id": None, "card_id": None, "cosmetic_item_id": cosmetic_id},
        }
        item_ids: dict[str, int] = {}
        for item_type, spec in specs.items():
            cursor = connection.execute(
                """
                INSERT INTO black_market_pool_items (
                    item_type, currency_code, amount, pack_id, card_id, cosmetic_item_id, rarity,
                    title, price_currency_code, price_amount, max_stock_per_rotation, selection_weight
                ) VALUES (?, ?, ?, ?, ?, ?, 'Common', ?, 'coins', 50, 3, 1)
                """,
                (
                    item_type,
                    spec["currency_code"],
                    spec["amount"],
                    spec["pack_id"],
                    spec["card_id"],
                    spec["cosmetic_item_id"],
                    f"BM {item_type.title()}",
                ),
            )
            item_ids[item_type] = int(cursor.lastrowid)

        connection.execute("UPDATE black_market_settings SET slots_count = 4 WHERE id = 1")
        connection.commit()

    return item_ids
