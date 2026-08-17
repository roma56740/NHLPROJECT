"""Прямые вызовы функций построения экранов BLACK MARKET (без Telegram) — тот же
принцип, что и tests/test_stronghold_handlers_smoke.py: дешёвый предохранитель от
регрессий в text/keyboard-builders, которые сервисные тесты не покрывают.
"""

from __future__ import annotations

from app.database.db import get_connection
from app.services.black_market_generation import get_or_create_rotation
from tests.conftest import business_date_today, create_test_user


async def test_build_storefront_screen_paginates_and_shows_next_reset_hint(black_market_pool):
    from app.handlers.black_market import build_storefront_screen

    user_id = await create_test_user("smoke-bm-storefront")
    text, keyboard = await build_storefront_screen(user_id, page=1)
    assert "Чёрный рынок" in text
    assert "00:00 UTC" in text
    # 4 предмета в фикстуре black_market_pool, STOREFRONT_PAGE_SIZE=4 -> помещаются на одну страницу.
    assert len(keyboard.inline_keyboard) >= 1


async def test_build_storefront_screen_pagination_with_many_items(stronghold_db):
    with get_connection() as connection:
        connection.execute("UPDATE black_market_rarity_weights SET weight = 0")
        connection.execute("UPDATE black_market_rarity_weights SET weight = 100 WHERE rarity = 'Common'")
        for index in range(6):
            connection.execute(
                """
                INSERT INTO black_market_pool_items
                    (item_type, currency_code, amount, rarity, title, price_currency_code, price_amount,
                     max_stock_per_rotation, selection_weight)
                VALUES ('currency', 'coins', 1, 'Common', ?, 'coins', 1, 3, 1)
                """,
                (f"Coin Pile {index}",),
            )
        connection.execute("UPDATE black_market_settings SET slots_count = 6, allow_duplicate_slots = 1 WHERE id = 1")
        connection.commit()

    from app.handlers.black_market import build_storefront_screen
    from app.keyboards.black_market import STOREFRONT_PAGE_SIZE

    user_id = await create_test_user("smoke-bm-pagination")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    assert len(rotation.items) == 6
    assert len(rotation.items) > STOREFRONT_PAGE_SIZE

    text_page1, keyboard_page1 = await build_storefront_screen(user_id, page=1)
    # Последняя строка перед "В главное меню" — навигация пагинации (номер страницы).
    nav_row = keyboard_page1.inline_keyboard[-2]
    assert any("1/2" in button.text for button in nav_row)

    text_page2, keyboard_page2 = await build_storefront_screen(user_id, page=2)
    nav_row_2 = keyboard_page2.inline_keyboard[-2]
    assert any("2/2" in button.text for button in nav_row_2)


async def test_build_item_detail_screen_renders_preview_file(black_market_pool):
    from app.handlers.black_market import build_item_detail_screen

    user_id = await create_test_user("smoke-bm-detail")
    rotation = await get_or_create_rotation(user_id, business_date_value=business_date_today())
    item = rotation.items[0]

    text, keyboard, preview_path = await build_item_detail_screen(user_id, item.id, return_page=1)
    assert text is not None
    assert item.name in text
    assert preview_path.exists()
    assert preview_path.suffix == ".png"


async def test_build_item_detail_screen_missing_item_returns_none(black_market_pool):
    from app.handlers.black_market import build_item_detail_screen

    user_id = await create_test_user("smoke-bm-detail-missing")
    text, keyboard, preview_path = await build_item_detail_screen(user_id, 9_999_999, return_page=1)
    assert text is None


def test_render_black_market_item_preview_falls_back_safely_for_missing_asset(tmp_path, monkeypatch):
    from app.services import renders

    monkeypatch.setattr(renders, "PREVIEW_DIR", tmp_path)

    path = renders.render_black_market_item_preview(
        item_type="cosmetic", cache_key="test-missing-asset", image_path="assets/does/not/exist.png", rarity="Rare", cosmetic_type="FRAME"
    )
    assert path.exists()

    # Повторный вызов с тем же cache_key переиспользует файл (кэш), а не перерисовывает.
    mtime_before = path.stat().st_mtime
    path_again = renders.render_black_market_item_preview(
        item_type="cosmetic", cache_key="test-missing-asset", image_path="assets/does/not/exist.png", rarity="Rare", cosmetic_type="FRAME"
    )
    assert path_again == path
    assert path_again.stat().st_mtime == mtime_before


def test_invalidate_black_market_preview_removes_cached_file(tmp_path, monkeypatch):
    from app.services import renders

    monkeypatch.setattr(renders, "PREVIEW_DIR", tmp_path)

    path = renders.render_black_market_item_preview(item_type="card", cache_key="test-invalidate", image_path=None, rarity="Common")
    assert path.exists()
    renders.invalidate_black_market_preview("test-invalidate")
    assert not path.exists()
