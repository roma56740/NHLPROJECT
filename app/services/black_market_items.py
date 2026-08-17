"""Реестр адаптеров по item_type для BLACK MARKET.

До аудита отображение (генерация имени/preview) и выдача награды при покупке были
двумя параллельными if/elif-цепочками в black_market_generation.py и
black_market_store.py. Это ровно тот антипаттерн, который явно запрещён ТЗ аудита
("не должно быть одной огромной цепочки if/elif" — раздел 8). Теперь оба места
(генерация и покупка) обращаются к ОДНОМУ реестру `ITEM_ADAPTERS`: добавление
нового item_type — это одна новая запись в реестре, а не правка двух функций.

Выдача награды переиспользует существующие сервисы игры (раздел 8 ТЗ аудита):
— CURRENCY -> app.services.rewards.grant_currency (общий wallet-хелпер);
— PACK -> app.services.rewards.grant_pack (общий packs-хелпер);
— CARD -> прямой INSERT в user_cards (как и в app.services.stronghold_store.py —
  отдельного grant_card-сервиса в проекте нет, паттерн — inline INSERT с проверкой
  active=1);
— FRAME/BACKGROUND (cosmetic) -> INSERT в user_cosmetic_items, та же таблица и тот
  же смысл, что и app.services.war2_cosmetics.grant_cosmetic_to_user (не отдельный
  косметический движок, а тот же самый общий каталог war2_cosmetic_items).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from app.services.black_market_common import BlackMarketError
from app.services.rewards import grant_currency, grant_pack

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemDisplay:
    name: str
    description: str
    preview: str | None
    reference_id: int | None


DisplayResolver = Callable[[sqlite3.Connection, sqlite3.Row], ItemDisplay]
GrantFn = Callable[[sqlite3.Connection, int, sqlite3.Row], None]


@dataclass(frozen=True)
class ItemAdapter:
    item_type: str
    label: str
    resolve_display: DisplayResolver
    grant: GrantFn


def _display_currency(connection: sqlite3.Connection, pool_row: sqlite3.Row) -> ItemDisplay:
    name = pool_row["title"] or ""
    if not name:
        currency = connection.execute(
            "SELECT name, icon FROM currencies WHERE code = ?", (pool_row["currency_code"],)
        ).fetchone()
        if currency is not None:
            name = f"{currency['icon']} {currency['name']}"
    return ItemDisplay(name=name, description=pool_row["description"] or "", preview=None, reference_id=None)


def _grant_currency_item(connection: sqlite3.Connection, user_id: int, item_row: sqlite3.Row) -> None:
    pool_row = connection.execute(
        "SELECT currency_code, amount FROM black_market_pool_items WHERE id = ?",
        (item_row["pool_item_id"],),
    ).fetchone()
    if pool_row is None or not pool_row["currency_code"]:
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Некорректная валюта в составе товара.")
    grant_currency(connection, user_id, pool_row["currency_code"], int(pool_row["amount"]))


def _display_pack(connection: sqlite3.Connection, pool_row: sqlite3.Row) -> ItemDisplay:
    pack = connection.execute(
        "SELECT name, description, image_path FROM packs WHERE id = ?", (pool_row["pack_id"],)
    ).fetchone()
    name = pool_row["title"] or (pack["name"] if pack is not None else "")
    description = pool_row["description"] or ((pack["description"] if pack is not None else "") or "")
    preview = pack["image_path"] if pack is not None else None
    return ItemDisplay(name=name, description=description, preview=preview, reference_id=pool_row["pack_id"])


def _grant_pack_item(connection: sqlite3.Connection, user_id: int, item_row: sqlite3.Row) -> None:
    reference_id = item_row["item_reference_id"]
    if reference_id is None or not grant_pack(connection, user_id, int(reference_id), 1):
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Пак больше недоступен.")


def _display_card(connection: sqlite3.Connection, pool_row: sqlite3.Row) -> ItemDisplay:
    card = connection.execute("SELECT name, image_path FROM cards WHERE id = ?", (pool_row["card_id"],)).fetchone()
    name = pool_row["title"] or (card["name"] if card is not None else "")
    preview = card["image_path"] if card is not None else None
    return ItemDisplay(name=name, description=pool_row["description"] or "", preview=preview, reference_id=pool_row["card_id"])


def _grant_card_item(connection: sqlite3.Connection, user_id: int, item_row: sqlite3.Row) -> None:
    reference_id = item_row["item_reference_id"]
    if reference_id is None:
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Карта больше недоступна.")
    card_exists = connection.execute("SELECT 1 FROM cards WHERE id = ? AND active = 1", (reference_id,)).fetchone()
    if card_exists is None:
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Карта больше недоступна.")
    connection.execute(
        "INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked) VALUES (?, ?, 'black_market', 0, 0)",
        (user_id, reference_id),
    )


def _display_cosmetic(connection: sqlite3.Connection, pool_row: sqlite3.Row) -> ItemDisplay:
    cosmetic = connection.execute(
        "SELECT title, description, image_path FROM war2_cosmetic_items WHERE id = ?",
        (pool_row["cosmetic_item_id"],),
    ).fetchone()
    name = pool_row["title"] or (cosmetic["title"] if cosmetic is not None else "")
    description = pool_row["description"] or ((cosmetic["description"] if cosmetic is not None else "") or "")
    preview = cosmetic["image_path"] if cosmetic is not None else None
    return ItemDisplay(name=name, description=description, preview=preview, reference_id=pool_row["cosmetic_item_id"])


def _grant_cosmetic_item(connection: sqlite3.Connection, user_id: int, item_row: sqlite3.Row) -> None:
    reference_id = item_row["item_reference_id"]
    if reference_id is None:
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Косметика больше недоступна.")
    cosmetic = connection.execute(
        "SELECT type, rarity FROM war2_cosmetic_items WHERE id = ? AND active = 1", (reference_id,)
    ).fetchone()
    if cosmetic is None:
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Косметика больше недоступна.")
    connection.execute(
        "INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source) VALUES (?, ?, ?, ?, 'black_market_purchase')",
        (user_id, reference_id, cosmetic["type"], cosmetic["rarity"]),
    )


ITEM_ADAPTERS: dict[str, ItemAdapter] = {
    "currency": ItemAdapter("currency", "Валюта", _display_currency, _grant_currency_item),
    "pack": ItemAdapter("pack", "Пак", _display_pack, _grant_pack_item),
    "card": ItemAdapter("card", "Карта", _display_card, _grant_card_item),
    # Один адаптер обслуживает и FRAME, и BACKGROUND: у обоих один и тот же общий
    # каталог/таблица war2_cosmetic_items, различаются только значением war2_cosmetic_items.type
    # (см. app.services.war2_cosmetics.COSMETIC_TYPES) — заводить два физически разных
    # item_type под них означало бы дублировать одну и ту же логику ради различия,
    # которое уже выражено полем `type` в самой косметике.
    "cosmetic": ItemAdapter("cosmetic", "Косметика (рамка/фон)", _display_cosmetic, _grant_cosmetic_item),
}


def resolve_display(connection: sqlite3.Connection, pool_row: sqlite3.Row) -> ItemDisplay:
    adapter = ITEM_ADAPTERS.get(pool_row["item_type"])
    if adapter is None:
        logger.warning("black market: unknown item_type=%s for pool_item_id=%s", pool_row["item_type"], pool_row["id"])
        return ItemDisplay(name=pool_row["title"] or "???", description=pool_row["description"] or "", preview=None, reference_id=None)
    return adapter.resolve_display(connection, pool_row)


def grant_item(connection: sqlite3.Connection, user_id: int, item_row: sqlite3.Row) -> None:
    adapter = ITEM_ADAPTERS.get(item_row["item_type"])
    if adapter is None:
        raise BlackMarketError("INVALID_ITEM_CONFIGURATION", "Неизвестный тип награды.")
    adapter.grant(connection, user_id, item_row)


def get_preview_render_args(
    connection: sqlite3.Connection,
    *,
    item_type: str,
    reference_id: int | None,
    preview_path: str | None,
    rarity: str,
) -> dict:
    """Собирает аргументы для app.services.renders.render_black_market_item_preview —
    для cosmetic нужно ещё узнать FRAME/BACKGROUND (war2_cosmetic_items.type),
    т.к. рендерятся они по-разному (фон демо-карты vs рамка поверх неё)."""
    cosmetic_type: str | None = None
    if item_type == "cosmetic" and reference_id is not None:
        row = connection.execute("SELECT type FROM war2_cosmetic_items WHERE id = ?", (reference_id,)).fetchone()
        if row is not None:
            cosmetic_type = row["type"]
    return {
        "item_type": item_type,
        "image_path": preview_path,
        "rarity": rarity,
        "cosmetic_type": cosmetic_type,
    }
