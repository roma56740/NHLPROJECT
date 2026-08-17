"""Прямые вызовы функций построения экранов/клавиатур THE STRONGHOLD (без Telegram).

Сервисный слой уже покрыт тестами, но именно text/keyboard-builders в
app/handlers/stronghold.py и app/keyboards/stronghold.py раньше не вызывались тестами
вообще — рефакторинг (вынос текстов/клавиатур в отдельные модули) один раз реально
сломал экран (обращение к уже удалённому локальному словарю ERROR_MESSAGES) без единого
падающего теста, т.к. ни один сервисный тест не проходит через этот код. Этот файл —
дешёвый предохранитель именно от такого класса регрессий.
"""

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from app.database.db import get_connection
from app.keyboards import stronghold as keyboards
from tests.conftest import build_full_stronghold_lineup, create_test_user, grant_balance


def _fsm_context(user_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


async def test_build_overview_returns_text_and_keyboard(active_event):
    from app.handlers.stronghold import build_overview

    user_id = await create_test_user("smoke-overview-user")
    text, keyboard = await build_overview(user_id)
    assert "THE STRONGHOLD" in text
    assert len(keyboard.inline_keyboard) > 0


async def test_build_upgrade_screen_no_blocking_reason(active_event):
    from app.handlers.stronghold import build_upgrade_screen

    user_id = await create_test_user("smoke-upgrade-user")
    await build_full_stronghold_lineup(user_id)
    grant_balance(user_id, "fortress_token", 100)
    grant_balance(user_id, "coins", 1_000_000)

    state = _fsm_context(user_id)
    text, keyboard = await build_upgrade_screen(user_id, state)
    assert "Upgrade Chain" in text
    assert "Подтвердить апгрейд" in str(keyboard.inline_keyboard)


async def test_build_upgrade_screen_with_blocking_reason(active_event):
    """Именно эта ветка (blocking_reason truthy) раньше падала с NameError:
    ERROR_MESSAGES не определена после выноса текстов в app/texts/stronghold.py."""
    from app.handlers.stronghold import build_upgrade_screen

    user_id = await create_test_user("smoke-upgrade-blocked-user")
    await build_full_stronghold_lineup(user_id)
    # намеренно НЕ выдаём FT/Coins -> preview.blocking_reason = INSUFFICIENT_COINS

    state = _fsm_context(user_id)
    text, keyboard = await build_upgrade_screen(user_id, state)
    assert "Недостаточно" in text
    assert "Подтвердить апгрейд" not in str(keyboard.inline_keyboard)


async def test_all_keyboard_builders_run_without_error(active_event):
    from app.services.stronghold_endless import get_leaderboard, get_status
    from app.services.stronghold_fortress import get_fortress, list_fortresses
    from app.services.stronghold_missions import list_missions
    from app.services.stronghold_season_track import get_track
    from app.services.stronghold_store import list_products
    from app.services.stronghold_wallet import get_currency_history

    user_id = await create_test_user("smoke-keyboards-user")
    await build_full_stronghold_lineup(user_id)

    with get_connection() as connection:
        event_row = connection.execute("SELECT id FROM stronghold_events LIMIT 1").fetchone()

    fortresses = await list_fortresses(user_id)
    assert keyboards.build_fortress_list_keyboard(fortresses).inline_keyboard

    fortress = await get_fortress(user_id, fortresses[0].id)
    assert keyboards.build_fortress_view_keyboard(fortress).inline_keyboard

    endless_status = await get_status(user_id)
    assert keyboards.build_endless_keyboard(unlocked=endless_status.unlocked).inline_keyboard

    board = await get_leaderboard(page=1, user_id=user_id)
    assert keyboards.build_leaderboard_keyboard(board).inline_keyboard

    missions = await list_missions(user_id, "DAILY")
    assert keyboards.build_missions_keyboard(missions, "DAILY", ["DAILY", "WEEKLY", "SEASONAL"]).inline_keyboard

    track = await get_track(user_id)
    assert keyboards.build_season_track_keyboard(track).inline_keyboard

    products = await list_products(user_id, "Featured")
    assert keyboards.build_store_keyboard(products, "Featured", ["Featured", "Cards", "Resources", "Bundles"]).inline_keyboard

    history = await get_currency_history(user_id, event_row["id"], page=1)
    assert keyboards.build_wallet_history_keyboard(history).inline_keyboard

    assert keyboards.build_overview_keyboard().inline_keyboard
    assert keyboards.build_upgrade_keyboard(can_confirm=True).inline_keyboard
    assert keyboards.build_upgrade_keyboard(can_confirm=False).inline_keyboard
