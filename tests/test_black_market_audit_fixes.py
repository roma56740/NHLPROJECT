"""Тесты, добавленные по результатам технического аудита BLACK MARKET:
shop_enabled, доступность по датам, personal_purchase_limit независимый от стока,
allow_repeat_in_rotation (per-item и глобальный), детерминизм RANDOM_RANGE после
принудительной регенерации, fallback-логирование при пустой редкости, пустой пул,
валидация цен, порядок роутеров (чтобы creator_tournaments не перехватывал кнопку),
и полный прогон FSM "Добавить предмет" (CURRENCY) напрямую по функциям хендлера.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.database.db import get_connection
from app.services import black_market_admin
from app.services.black_market_common import BlackMarketError
from app.services.black_market_generation import get_or_create_rotation
from app.services.black_market_store import purchase
from tests.conftest import business_date_today, create_test_user, grant_balance


def _fsm_context(user_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


def _item_by_type(rotation, item_type: str):
    return next(item for item in rotation.items if item.item_type == item_type)


# ---------------------------------------------------------------------------
# shop_enabled
# ---------------------------------------------------------------------------

async def test_shop_disabled_blocks_listing(black_market_pool):
    from app.services.black_market_store import list_storefront

    user_id = await create_test_user("bm-audit-disabled-list")
    await black_market_admin.set_shop_enabled(1, False)
    with pytest.raises(BlackMarketError) as exc_info:
        await list_storefront(user_id)
    assert exc_info.value.code == "SHOP_DISABLED"
    await black_market_admin.set_shop_enabled(1, True)


async def test_shop_disabled_blocks_purchase(black_market_pool):
    user_id = await create_test_user("bm-audit-disabled-buy")
    grant_balance(user_id, "coins", 1000)
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = _item_by_type(rotation, "currency")

    await black_market_admin.set_shop_enabled(1, False)
    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "SHOP_DISABLED"


# ---------------------------------------------------------------------------
# Доступность по датам
# ---------------------------------------------------------------------------

async def test_available_from_in_future_excludes_item(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                 max_stock_per_rotation, selection_weight, available_from)
            VALUES ('currency', 'coins', 10, 'Common', 'Future Coins', 'coins', 5, 3, 1, '2099-01-01 00:00:00')
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 2 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-future-item")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    assert rotation.items == []


async def test_available_until_in_past_excludes_item(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                 max_stock_per_rotation, selection_weight, available_until)
            VALUES ('currency', 'coins', 10, 'Common', 'Expired Coins', 'coins', 5, 3, 1, '2000-01-01 00:00:00')
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 2 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-expired-item")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    assert rotation.items == []


# ---------------------------------------------------------------------------
# personal_purchase_limit независимый от стока
# ---------------------------------------------------------------------------

async def test_personal_purchase_limit_independent_of_stock(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                 max_stock_per_rotation, personal_purchase_limit, selection_weight)
            VALUES ('currency', 'coins', 10, 'Common', 'Limited Coins', 'coins', 1, 5, 2, 1)
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 1 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-limit-user")
    grant_balance(user_id, "coins", 1000)
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = rotation.items[0]
    assert item.initial_personal_stock == 5
    assert item.personal_purchase_limit == 2

    await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    with pytest.raises(BlackMarketError) as exc_info:
        await purchase(user_id, item.id, request_id=str(uuid.uuid4()))
    assert exc_info.value.code == "PURCHASE_LIMIT_REACHED"

    with get_connection() as connection:
        remaining = connection.execute(
            "SELECT remaining_personal_stock FROM black_market_user_rotation_items WHERE id = ?", (item.id,)
        ).fetchone()["remaining_personal_stock"]
    assert remaining == 3  # сток остался (лимит покупок исчерпан раньше стока)


# ---------------------------------------------------------------------------
# allow_repeat_in_rotation (per-item и глобальный)
# ---------------------------------------------------------------------------

async def test_item_level_allow_repeat_permits_duplicate_slots(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                 max_stock_per_rotation, selection_weight, allow_repeat_in_rotation)
            VALUES ('currency', 'coins', 10, 'Common', 'Repeatable Coins', 'coins', 5, 3, 1, 1)
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 3, allow_duplicate_slots = 0 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-repeat-item")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    assert len(rotation.items) == 3
    assert len({item.pool_item_id for item in rotation.items}) == 1


async def test_global_allow_duplicate_slots_overrides_item_flag(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                 max_stock_per_rotation, selection_weight, allow_repeat_in_rotation)
            VALUES ('currency', 'coins', 10, 'Common', 'Solo Coins', 'coins', 5, 3, 1, 0)
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 3, allow_duplicate_slots = 1 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-repeat-global")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    assert len(rotation.items) == 3
    assert len({item.pool_item_id for item in rotation.items}) == 1


# ---------------------------------------------------------------------------
# Пустой мастер-пул
# ---------------------------------------------------------------------------

async def test_empty_master_pool_generates_empty_rotation_without_crash(stronghold_db):
    user_id = await create_test_user("bm-audit-empty-pool")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    assert rotation.items == []


# ---------------------------------------------------------------------------
# Fallback между редкостями + логирование
# ---------------------------------------------------------------------------

async def test_rarity_fallback_fills_slot_and_logs_warning(stronghold_db, caplog):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Rare'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                 max_stock_per_rotation, selection_weight)
            VALUES ('currency', 'coins', 10, 'Common', 'Only Common Coins', 'coins', 5, 3, 1)
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 1 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-fallback")
    with caplog.at_level("WARNING"):
        rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())

    assert len(rotation.items) == 1
    assert rotation.items[0].rarity == "Common"
    assert any("no valid pool items for rarity=Rare" in message for message in caplog.messages)


# ---------------------------------------------------------------------------
# Детерминизм RANDOM_RANGE после принудительной регенерации (тот же seed)
# ---------------------------------------------------------------------------

async def test_random_range_price_reproducible_after_forced_regeneration(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        connection.execute(
            """
            INSERT INTO black_market_pool_items
                (item_type, currency_code, amount, rarity, title, price_currency_code,
                 price_mode, price_min_amount, price_max_amount, max_stock_per_rotation, selection_weight)
            VALUES ('currency', 'coins', 10, 'Common', 'Range Coins', 'coins', 'RANDOM_RANGE', 10, 100000, 3, 1)
            """
        )
        connection.execute("UPDATE black_market_settings SET slots_count = 1 WHERE id = 1")
        connection.commit()

    user_id = await create_test_user("bm-audit-range-repro")
    first = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    first_price = first.items[0].price_amount

    await black_market_admin.refresh_one_user(admin_id=1, target_user_id=user_id)
    second = await get_or_create_rotation(user_id, business_date_value=business_date_today())

    assert second.id != first.id
    assert second.items[0].price_amount == first_price


# ---------------------------------------------------------------------------
# Валидация цен
# ---------------------------------------------------------------------------

async def test_create_pool_item_rejects_inverted_price_range(stronghold_db):
    with pytest.raises(BlackMarketError) as exc_info:
        await black_market_admin.create_pool_item(
            1, item_type="currency", rarity="Common", price_currency_code="coins",
            currency_code="coins", amount=1, price_mode="RANDOM_RANGE", price_min_amount=100, price_max_amount=10,
        )
    assert exc_info.value.code == "PRICE_RANGE_INVALID"


async def test_create_pool_item_rejects_negative_fixed_price(stronghold_db):
    with pytest.raises(BlackMarketError) as exc_info:
        await black_market_admin.create_pool_item(
            1, item_type="currency", rarity="Common", price_currency_code="coins",
            currency_code="coins", amount=1, price_mode="FIXED", price_amount=-5,
        )
    assert exc_info.value.code == "PRICE_RANGE_INVALID"


# ---------------------------------------------------------------------------
# Порядок роутеров: Чёрный рынок регистрируется раньше catch-all creator_tournaments
# ---------------------------------------------------------------------------

def test_black_market_routers_registered_before_creator_tournaments_catchall(app_router):
    from app.handlers import admin_black_market, black_market, creator_tournaments

    assert app_router.sub_routers.index(black_market.router) < app_router.sub_routers.index(creator_tournaments.router)
    assert app_router.sub_routers.index(admin_black_market.router) < app_router.sub_routers.index(creator_tournaments.router)


# ---------------------------------------------------------------------------
# Admin FSM "Добавить предмет" — полный прогон (CURRENCY) напрямую по функциям хендлера
# ---------------------------------------------------------------------------

class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeMessage:
    def __init__(self, user_id: int, text: str | None = None) -> None:
        self.from_user = _FakeUser(user_id)
        self.text = text
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.chat = _FakeUser(user_id)
        self.sent: list[str] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.sent.append(text)

    async def answer_photo(self, photo, caption: str | None = None, reply_markup=None) -> None:
        self.sent.append(caption or "")

    async def delete(self) -> None:
        pass


class _FakeBot:
    async def send_message(self, chat_id, text, reply_markup=None) -> None:
        pass

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None) -> None:
        pass


class _FakeCallback:
    def __init__(self, user_id: int, data: str) -> None:
        self.from_user = _FakeUser(user_id)
        self.data = data
        self.message = _FakeMessage(user_id)
        self.bot = _FakeBot()
        self.answered: list[str | None] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answered.append(text)


async def test_admin_add_item_currency_wizard_creates_pool_item(stronghold_db, monkeypatch):
    from app.handlers import admin_black_market as handlers

    admin_id = 999999999
    monkeypatch.setattr(handlers, "_require_permission", lambda user_id: True)

    async def _fake_edit_or_send(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(handlers, "edit_or_send", _fake_edit_or_send)

    state = _fsm_context(admin_id)

    await handlers.admin_add_item_start(_FakeCallback(admin_id, "bm_admin:add_item:start"), state)
    await handlers.admin_add_item_type_chosen(_FakeCallback(admin_id, "bm_admin:add_item:type:currency"), state)

    currencies = await black_market_admin.list_currency_choices()
    code = currencies[0]["code"]
    await handlers.admin_add_item_currency_chosen(_FakeCallback(admin_id, f"bm_admin:add_item:currency:{code}"), state)
    await handlers.admin_add_item_currency_amount_input(_FakeMessage(admin_id, "500"), state)

    await handlers.admin_add_item_rarity_chosen(_FakeCallback(admin_id, "bm_admin:add_item:rarity:Common"), state)
    await handlers.admin_add_item_price_currency_chosen(_FakeCallback(admin_id, f"bm_admin:add_item:price_currency:{code}"), state)
    await handlers.admin_add_item_price_mode_fixed(_FakeCallback(admin_id, "bm_admin:add_item:price_mode:FIXED"), state)
    await handlers.admin_add_item_price_fixed_input(_FakeMessage(admin_id, "20"), state)
    await handlers.admin_add_item_stock_input(_FakeMessage(admin_id, "3"), state)
    await handlers.admin_add_item_purchase_limit_input(_FakeMessage(admin_id, "0"), state)
    await handlers.admin_add_item_selection_weight_input(_FakeMessage(admin_id, "1"), state)
    await handlers.admin_add_item_repeat_chosen(_FakeCallback(admin_id, "bm_admin:add_item:repeat:no"), state)
    await handlers.admin_add_item_dates_no(_FakeCallback(admin_id, "bm_admin:add_item:dates:no"), state)
    await handlers.admin_add_item_confirm(_FakeCallback(admin_id, "bm_admin:add_item:confirm"), state)

    items = await black_market_admin.list_pool_items(item_type="currency")
    matching = [item for item in items if item.currency_code == code and item.amount == 500]
    assert len(matching) == 1
    assert matching[0].price_amount == 20
    assert matching[0].max_stock_per_rotation == 3
    assert matching[0].rarity == "Common"
