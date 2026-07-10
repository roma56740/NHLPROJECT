"""Программа официальных креаторов.

Новая логика:
- уровень креатора выставляется только вручную администратором;
- после одобрения заявки пользователь сразу становится креатором 1 уровня;
- вступительные и недельные бонусы начисляются в банк выдачи;
- креатор может пополнять банк валютой, паками и карточками, вывести обратно нельзя;
- разыгранная сумма считается только после фактической выдачи игроку;
- все требования, бонусы и личные награды уровней редактируются через админ-раздел.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from app.database.db import get_connection
from app.database.schema import DEFAULT_CREATOR_LEVEL_SETTINGS
from app.services.quick_sell import quick_sell_price
from app.services.rewards import grant_currency, grant_pack
from app.services.settings import get_bool_setting, get_int_setting, get_setting, set_setting_value


CURRENCY_VALUE_IN_COINS = {
    "coins": 1,
    "energy": 10_000,      # в интерфейсе проекта эта валюта уже переименована в рубли
    "rubles": 10_000,
    "ruble": 10_000,
    "rank_point": 40_000,
    "rank_coin": 40_000,
}

DEFAULT_CREATOR_LEVELS_BY_LEVEL = {int(item["level"]): item for item in DEFAULT_CREATOR_LEVEL_SETTINGS}
MIN_SUBSCRIBERS = int(DEFAULT_CREATOR_LEVELS_BY_LEVEL[1]["required_subscribers"])

# Совместимость со старым кодом/текстами.
CREATOR_LEVELS = {
    level: {
        "min_subs": int(cfg["required_subscribers"]),
        "required_distributed": int(cfg["required_distributed_value"]),
        "coins": int(cfg["weekly_coins"]),
        "packs": int(cfg["weekly_elite_packs"]) + int(cfg["weekly_legendary_packs"]),
        "title": f"{level} уровень",
    }
    for level, cfg in DEFAULT_CREATOR_LEVELS_BY_LEVEL.items()
}


@dataclass(frozen=True)
class CreatorLevelConfig:
    level: int
    required_subscribers: int
    required_distributed_value: int
    welcome_coins: int
    weekly_coins: int
    weekly_elite_packs: int
    weekly_legendary_packs: int
    weekly_elite_pack_id: int | None
    weekly_legendary_pack_id: int | None
    promo_codes_weekly: int
    author_code_percent_bp: int
    exclusive_card_rating: int
    perks_text: str
    personal_rewards_text: str


@dataclass(frozen=True)
class CreatorApplication:
    id: int
    user_id: int
    nickname: str
    telegram_id: int
    channel: str
    subscribers: int
    description: str
    status: str


@dataclass(frozen=True)
class CreatorBankItem:
    id: int
    item_type: str
    title: str
    quantity: int
    value_per_unit: int
    currency_code: str | None = None
    pack_id: int | None = None
    user_card_id: int | None = None

    @property
    def total_value(self) -> int:
        return int(self.quantity) * int(self.value_per_unit)


@dataclass(frozen=True)
class CreatorPanel:
    is_creator: bool
    level: int
    level_title: str
    channel: str | None
    subscribers: int
    distributed_value: int
    required_subscribers: int
    required_distributed_value: int
    welcome_claimed: bool
    bank_items: list[CreatorBankItem]
    perks_text: str
    personal_rewards_text: str

    @property
    def coins_available(self) -> int:
        return sum(item.quantity for item in self.bank_items if item.item_type == "currency" and item.currency_code == "coins")

    @property
    def packs(self) -> list[tuple[int, str, int]]:
        return [
            (int(item.pack_id or 0), item.title, int(item.quantity))
            for item in self.bank_items
            if item.item_type == "pack" and item.pack_id is not None
        ]

    @property
    def bank_total_value(self) -> int:
        return sum(item.total_value for item in self.bank_items)


@dataclass(frozen=True)
class WeeklyPayoutResult:
    creators_count: int
    total_coins: int
    total_packs: int
    telegram_ids: list[int]


def format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def currency_value_per_unit(currency_code: str | None) -> int:
    if not currency_code:
        return 0
    return CURRENCY_VALUE_IN_COINS.get(currency_code.strip().lower(), 1)


def level_for_subscribers(subs: int) -> int:
    """Подсказка по подписчикам. Уровень всё равно выставляет админ вручную."""
    level = 1
    for lvl in sorted(CREATOR_LEVELS):
        if subs >= CREATOR_LEVELS[lvl]["min_subs"]:
            level = lvl
    return level


def _row_to_level_config(row: Any) -> CreatorLevelConfig:
    return CreatorLevelConfig(
        level=int(row["level"]),
        required_subscribers=int(row["required_subscribers"]),
        required_distributed_value=int(row["required_distributed_value"]),
        welcome_coins=int(row["welcome_coins"]),
        weekly_coins=int(row["weekly_coins"]),
        weekly_elite_packs=int(row["weekly_elite_packs"]),
        weekly_legendary_packs=int(row["weekly_legendary_packs"]),
        weekly_elite_pack_id=int(row["weekly_elite_pack_id"]) if row["weekly_elite_pack_id"] is not None else None,
        weekly_legendary_pack_id=int(row["weekly_legendary_pack_id"]) if row["weekly_legendary_pack_id"] is not None else None,
        promo_codes_weekly=int(row["promo_codes_weekly"]),
        author_code_percent_bp=int(row["author_code_percent_bp"]),
        exclusive_card_rating=int(row["exclusive_card_rating"]),
        perks_text=row["perks_text"] or "",
        personal_rewards_text=row["personal_rewards_text"] or "",
    )


def _get_level_config(connection, level: int) -> CreatorLevelConfig | None:
    row = connection.execute(
        "SELECT * FROM creator_level_settings WHERE level = ?",
        (level,),
    ).fetchone()
    return _row_to_level_config(row) if row else None


def _upsert_bank_item(
    connection,
    user_id: int,
    item_type: str,
    quantity: int,
    value_per_unit: int,
    currency_code: str | None = None,
    pack_id: int | None = None,
    user_card_id: int | None = None,
) -> int:
    if item_type in {"currency", "pack"}:
        row = connection.execute(
            """
            SELECT id FROM creator_bank_items
            WHERE user_id = ?
              AND item_type = ?
              AND status = 'available'
              AND COALESCE(currency_code, '') = COALESCE(?, '')
              AND COALESCE(pack_id, 0) = COALESCE(?, 0)
            LIMIT 1
            """,
            (user_id, item_type, currency_code, pack_id),
        ).fetchone()
        if row:
            connection.execute(
                """
                UPDATE creator_bank_items
                SET quantity = quantity + ?, value_per_unit = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (quantity, value_per_unit, int(row["id"])),
            )
            return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO creator_bank_items (
            user_id, item_type, currency_code, pack_id, user_card_id, quantity, value_per_unit
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, item_type, currency_code, pack_id, user_card_id, quantity, value_per_unit),
    )
    return int(cursor.lastrowid)


def _pack_value_in_coins(connection, pack_id: int) -> int:
    row = connection.execute(
        "SELECT price_currency_code, price_amount FROM packs WHERE id = ?",
        (pack_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row["price_amount"] or 0) * currency_value_per_unit(row["price_currency_code"])


def _pack_title(connection, pack_id: int) -> str:
    row = connection.execute("SELECT name FROM packs WHERE id = ?", (pack_id,)).fetchone()
    return row["name"] if row else f"Пак #{pack_id}"


def _find_pack_id_for_kind(connection, configured_pack_id: int | None, kind: str) -> int | None:
    if configured_pack_id:
        row = connection.execute("SELECT id FROM packs WHERE id = ? AND active = 1", (configured_pack_id,)).fetchone()
        if row:
            return int(row["id"])

    if kind == "elite":
        patterns = ["%elite%", "%элит%"]
    else:
        patterns = ["%legend%", "%леген%"]

    for pattern in patterns:
        row = connection.execute(
            """
            SELECT id FROM packs
            WHERE active = 1 AND (LOWER(code) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?))
            ORDER BY is_shop_available DESC, sort_order, id
            LIMIT 1
            """,
            (pattern, pattern),
        ).fetchone()
        if row:
            return int(row["id"])

    row = connection.execute(
        "SELECT id FROM packs WHERE active = 1 ORDER BY is_shop_available DESC, sort_order, id LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _grant_creator_bank_pack(connection, user_id: int, pack_id: int | None, quantity: int) -> int:
    if not pack_id or quantity <= 0:
        return 0
    value = _pack_value_in_coins(connection, pack_id)
    _upsert_bank_item(connection, user_id, "pack", quantity, value, pack_id=pack_id)
    return quantity


def _grant_welcome_bonus_if_needed(connection, user_id: int, level: int) -> bool:
    if level <= 0:
        return False
    cfg = _get_level_config(connection, level)
    if cfg is None:
        return False

    claimed = connection.execute(
        "SELECT id FROM creator_bonus_claims WHERE user_id = ? AND bonus_type = 'welcome' AND level = ?",
        (user_id, level),
    ).fetchone()
    if claimed:
        return False

    if cfg.welcome_coins > 0:
        _upsert_bank_item(connection, user_id, "currency", cfg.welcome_coins, 1, currency_code="coins")

    connection.execute(
        "INSERT INTO creator_bonus_claims (user_id, bonus_type, level) VALUES (?, 'welcome', ?)",
        (user_id, level),
    )
    return True


def _bank_item_from_row(row: Any) -> CreatorBankItem:
    if row["item_type"] == "currency":
        title = f"{row['currency_icon'] or ''} {row['currency_name'] or row['currency_code']}".strip()
    elif row["item_type"] == "pack":
        title = f"🎁 {row['pack_name'] or ('Пак #' + str(row['pack_id']))}"
    else:
        title = f"🃏 {row['card_name'] or 'Карточка'} {row['card_overall'] or ''} OVR".strip()

    return CreatorBankItem(
        id=int(row["id"]),
        item_type=row["item_type"],
        title=title,
        quantity=int(row["quantity"]),
        value_per_unit=int(row["value_per_unit"] or 0),
        currency_code=row["currency_code"],
        pack_id=int(row["pack_id"]) if row["pack_id"] is not None else None,
        user_card_id=int(row["user_card_id"]) if row["user_card_id"] is not None else None,
    )


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------

async def submit_application(user_id: int, channel: str, subscribers: int, description: str) -> tuple[bool, str]:
    channel = channel.strip()
    description = " ".join(description.strip().split())
    if len(channel) < 3 or len(channel) > 128:
        return False, "Укажи корректную ссылку на канал/чат."
    if subscribers < 0 or subscribers > 100_000_000:
        return False, "Некорректное число подписчиков."

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
        if creator and int(creator["is_creator"]):
            connection.rollback()
            return False, "Ты уже официальный креатор."
        pending = connection.execute(
            "SELECT id FROM creator_applications WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
        if pending is not None:
            connection.rollback()
            return False, "Твоя заявка уже на рассмотрении."
        connection.execute(
            "INSERT INTO creator_applications (user_id, channel, subscribers, description) VALUES (?, ?, ?, ?)",
            (user_id, channel, subscribers, description[:500]),
        )
        connection.commit()
    return True, "Заявка отправлена. Админы рассмотрят её и вручную назначат уровень после проверки."


async def get_pending_applications() -> list[CreatorApplication]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT a.id, a.user_id, u.nickname, u.telegram_id, a.channel, a.subscribers, a.description, a.status
            FROM creator_applications a
            JOIN users u ON u.id = a.user_id
            WHERE a.status = 'pending'
            ORDER BY a.created_at
            """
        ).fetchall()
    return [CreatorApplication(**dict(row)) for row in rows]


async def get_application(app_id: int) -> CreatorApplication | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT a.id, a.user_id, u.nickname, u.telegram_id, a.channel, a.subscribers, a.description, a.status
            FROM creator_applications a
            JOIN users u ON u.id = a.user_id
            WHERE a.id = ?
            """,
            (app_id,),
        ).fetchone()
    return CreatorApplication(**dict(row)) if row else None


async def get_creator_chat_invite_link() -> str:
    return (await get_setting("creator_chat_invite_link", "")).strip()


async def set_creator_chat_invite_link(value: str) -> None:
    await set_setting_value("creator_chat_invite_link", value.strip())


async def resolve_application(app_id: int, approve: bool) -> tuple[bool, str, int | None, str]:
    """Возвращает (ok, msg, telegram_id заявителя, ссылка на чат)."""
    chat_link = await get_creator_chat_invite_link()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT a.user_id, a.subscribers, a.channel, a.status, u.telegram_id
            FROM creator_applications a
            JOIN users u ON u.id = a.user_id
            WHERE a.id = ?
            """,
            (app_id,),
        ).fetchone()
        if row is None or row["status"] != "pending":
            connection.rollback()
            return False, "Заявка недоступна.", None, ""

        user_id = int(row["user_id"])
        telegram_id = int(row["telegram_id"])

        if not approve:
            connection.execute("UPDATE creator_applications SET status='rejected', resolved_at=CURRENT_TIMESTAMP WHERE id=?", (app_id,))
            connection.commit()
            return True, "Заявка отклонена.", telegram_id, ""

        if int(row["subscribers"]) < MIN_SUBSCRIBERS:
            connection.rollback()
            return False, f"Меньше {MIN_SUBSCRIBERS} подписчиков — минимум для программы не достигнут.", None, ""

        connection.execute(
            """
            UPDATE users
            SET is_creator = 1,
                creator_level = 1,
                creator_channel = ?,
                creator_subscribers = ?,
                creator_chat_link_sent = CASE WHEN ? != '' THEN 1 ELSE creator_chat_link_sent END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["channel"], int(row["subscribers"]), chat_link, user_id),
        )
        connection.execute("INSERT OR IGNORE INTO creator_inventory (user_id, coins) VALUES (?, 0)", (user_id,))
        _grant_welcome_bonus_if_needed(connection, user_id, 1)
        connection.execute("UPDATE creator_applications SET status='approved', resolved_at=CURRENT_TIMESTAMP WHERE id=?", (app_id,))
        connection.commit()
        return True, "Игрок назначен официальным креатором 1 уровня. Вступительный бонус 1 уровня добавлен в банк выдачи.", telegram_id, chat_link


# ---------------------------------------------------------------------------
# Статус, уровень, требования
# ---------------------------------------------------------------------------

async def is_creator(user_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and int(row["is_creator"]))


async def get_level_configs() -> list[CreatorLevelConfig]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM creator_level_settings ORDER BY level").fetchall()
    return [_row_to_level_config(row) for row in rows]


async def get_level_config(level: int) -> CreatorLevelConfig | None:
    with get_connection() as connection:
        return _get_level_config(connection, level)


async def get_total_distributed_value(user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COALESCE(SUM(value_coins), 0) AS total FROM creator_distributions WHERE creator_user_id = ?",
            (user_id,),
        ).fetchone()
    return int(row["total"] if row else 0)


async def set_creator_level(user_id: int, level: int) -> tuple[bool, str]:
    if level not in CREATOR_LEVELS:
        return False, "Уровень должен быть 1–5."
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT is_creator, creator_subscribers FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            connection.rollback()
            return False, "Игрок не найден."

        connection.execute(
            """
            UPDATE users
            SET creator_level = ?, is_creator = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (level, user_id),
        )
        connection.execute("INSERT OR IGNORE INTO creator_inventory (user_id, coins) VALUES (?, 0)", (user_id,))

        welcome_added = _grant_welcome_bonus_if_needed(connection, user_id, level)
        cfg = _get_level_config(connection, level)
        distributed = connection.execute(
            "SELECT COALESCE(SUM(value_coins), 0) AS total FROM creator_distributions WHERE creator_user_id = ?",
            (user_id,),
        ).fetchone()
        distributed_value = int(distributed["total"] if distributed else 0)
        connection.commit()

    note = "Уровень обновлён."
    if welcome_added:
        note += " Вступительный бонус этого уровня добавлен в банк выдачи."
    if cfg and (int(row["creator_subscribers"] or 0) < cfg.required_subscribers or distributed_value < cfg.required_distributed_value):
        note += " Внимание: по статистике креатор пока ниже требований уровня, но ручное назначение сохранено."
    return True, note


async def set_creator_subscribers(user_id: int, subscribers: int) -> tuple[bool, str]:
    if subscribers < 0:
        return False, "Количество подписчиков не может быть отрицательным."
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM users WHERE id = ? AND is_creator = 1", (user_id,)).fetchone()
        if row is None:
            return False, "Креатор не найден."
        connection.execute(
            "UPDATE users SET creator_subscribers = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (subscribers, user_id),
        )
        connection.commit()
    return True, "Количество подписчиков обновлено."


async def set_creator_author_code(user_id: int, code: str) -> tuple[bool, str]:
    clean = code.strip()
    if clean == "-":
        clean = ""
    if len(clean) > 32:
        return False, "Код автора должен быть короче 32 символов."
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM users WHERE id = ? AND is_creator = 1", (user_id,)).fetchone()
        if row is None:
            return False, "Креатор не найден."
        connection.execute(
            "UPDATE users SET creator_author_code = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (clean or None, user_id),
        )
        connection.commit()
    return True, "Код автора обновлён."


async def revoke_creator(user_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET is_creator = 0, creator_level = 1, creator_author_code = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user_id,),
        )
        connection.commit()
    return True, "Статус креатора снят. Банк выдачи не возвращается и остаётся в базе для истории."


# ---------------------------------------------------------------------------
# Банк креатора
# ---------------------------------------------------------------------------

async def get_panel(user_id: int) -> CreatorPanel:
    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT is_creator, creator_level, creator_channel, creator_subscribers
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        level = int(user["creator_level"]) if user else 0
        cfg = _get_level_config(connection, level)
        welcome = connection.execute(
            "SELECT id FROM creator_bonus_claims WHERE user_id = ? AND bonus_type = 'welcome' AND level = ?",
            (user_id, level),
        ).fetchone()
        distributed = connection.execute(
            "SELECT COALESCE(SUM(value_coins), 0) AS total FROM creator_distributions WHERE creator_user_id = ?",
            (user_id,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT
                cbi.*,
                cur.name AS currency_name,
                cur.icon AS currency_icon,
                p.name AS pack_name,
                c.name AS card_name,
                c.overall AS card_overall
            FROM creator_bank_items cbi
            LEFT JOIN currencies cur ON cur.code = cbi.currency_code
            LEFT JOIN packs p ON p.id = cbi.pack_id
            LEFT JOIN user_cards uc ON uc.id = cbi.user_card_id
            LEFT JOIN cards c ON c.id = uc.card_id
            WHERE cbi.user_id = ? AND cbi.status = 'available' AND cbi.quantity > 0
            ORDER BY cbi.item_type, cbi.created_at, cbi.id
            """,
            (user_id,),
        ).fetchall()

    return CreatorPanel(
        is_creator=bool(user and int(user["is_creator"])),
        level=level,
        level_title=f"{level} уровень" if level > 0 else "не назначен",
        channel=user["creator_channel"] if user else None,
        subscribers=int(user["creator_subscribers"] or 0) if user else 0,
        distributed_value=int(distributed["total"] if distributed else 0),
        required_subscribers=cfg.required_subscribers if cfg else 0,
        required_distributed_value=cfg.required_distributed_value if cfg else 0,
        welcome_claimed=bool(welcome),
        bank_items=[_bank_item_from_row(row) for row in rows],
        perks_text=cfg.perks_text if cfg else "",
        personal_rewards_text=cfg.personal_rewards_text if cfg else "",
    )


async def get_bank_item(user_id: int, item_id: int) -> CreatorBankItem | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                cbi.*,
                cur.name AS currency_name,
                cur.icon AS currency_icon,
                p.name AS pack_name,
                c.name AS card_name,
                c.overall AS card_overall
            FROM creator_bank_items cbi
            LEFT JOIN currencies cur ON cur.code = cbi.currency_code
            LEFT JOIN packs p ON p.id = cbi.pack_id
            LEFT JOIN user_cards uc ON uc.id = cbi.user_card_id
            LEFT JOIN cards c ON c.id = uc.card_id
            WHERE cbi.id = ? AND cbi.user_id = ? AND cbi.status = 'available' AND cbi.quantity > 0
            """,
            (item_id, user_id),
        ).fetchone()
    return _bank_item_from_row(row) if row else None


async def list_currencies_for_bank(user_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT cb.currency_code, cb.amount, c.name, c.icon
            FROM currency_balances cb
            JOIN currencies c ON c.code = cb.currency_code
            WHERE cb.user_id = ? AND cb.amount > 0 AND c.active = 1
            ORDER BY
                CASE cb.currency_code
                    WHEN 'coins' THEN 1
                    WHEN 'energy' THEN 2
                    WHEN 'rank_point' THEN 3
                    ELSE 99
                END,
                c.name
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) | {"value_per_unit": currency_value_per_unit(row["currency_code"])} for row in rows]


async def add_currency_to_bank(user_id: int, currency_code: str, amount: int) -> tuple[bool, str]:
    if amount <= 0:
        return False, "Сумма должна быть больше 0."
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
        if not creator or not int(creator["is_creator"]):
            connection.rollback()
            return False, "Пополнять банк могут только официальные креаторы."

        spent = connection.execute(
            """
            UPDATE currency_balances
            SET amount = amount - ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND currency_code = ? AND amount >= ?
            """,
            (amount, user_id, currency_code, amount),
        )
        if spent.rowcount != 1:
            connection.rollback()
            return False, "Недостаточно валюты на балансе."

        _upsert_bank_item(connection, user_id, "currency", amount, currency_value_per_unit(currency_code), currency_code=currency_code)
        connection.commit()
    return True, "Валюта добавлена в банк выдачи. Вывести её обратно нельзя."


async def list_packs_for_bank(user_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT up.pack_id, up.quantity, p.name, p.price_currency_code, p.price_amount
            FROM user_packs up
            JOIN packs p ON p.id = up.pack_id
            WHERE up.user_id = ? AND up.quantity > 0
            ORDER BY p.name
            """,
            (user_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["value_per_unit"] = int(row["price_amount"] or 0) * currency_value_per_unit(row["price_currency_code"])
        result.append(item)
    return result


async def add_pack_to_bank(user_id: int, pack_id: int, quantity: int = 1) -> tuple[bool, str]:
    if quantity <= 0:
        return False, "Количество должно быть больше 0."
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
        if not creator or not int(creator["is_creator"]):
            connection.rollback()
            return False, "Пополнять банк могут только официальные креаторы."
        spent = connection.execute(
            """
            UPDATE user_packs
            SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND pack_id = ? AND quantity >= ?
            """,
            (quantity, user_id, pack_id, quantity),
        )
        if spent.rowcount != 1:
            connection.rollback()
            return False, "Такого пака нет на балансе или количества недостаточно."
        _upsert_bank_item(connection, user_id, "pack", quantity, _pack_value_in_coins(connection, pack_id), pack_id=pack_id)
        name = _pack_title(connection, pack_id)
        connection.commit()
    return True, f"Пак «{name}» добавлен в банк выдачи. Вывести его обратно нельзя."


async def add_card_to_bank(user_id: int, user_card_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
        if not creator or not int(creator["is_creator"]):
            connection.rollback()
            return False, "Пополнять банк могут только официальные креаторы."
        row = connection.execute(
            """
            SELECT uc.id, uc.is_in_lineup, uc.trade_locked, c.name, c.overall
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE uc.id = ? AND uc.user_id = ?
            """,
            (user_card_id, user_id),
        ).fetchone()
        if row is None:
            connection.rollback()
            return False, "Карточка не найдена в твоей коллекции."
        if int(row["is_in_lineup"]):
            connection.rollback()
            return False, "Карта стоит в составе. Сначала убери её из состава."
        existing = connection.execute(
            "SELECT id FROM creator_bank_items WHERE user_card_id = ? AND status = 'available'",
            (user_card_id,),
        ).fetchone()
        if existing:
            connection.rollback()
            return False, "Эта карта уже находится в банке выдачи."

        price = quick_sell_price(int(row["overall"])) or 0
        connection.execute(
            """
            UPDATE user_cards
            SET trade_locked = 1, lock_reason = 'creator_bank', lock_until = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (user_card_id, user_id),
        )
        _upsert_bank_item(connection, user_id, "card", 1, price, user_card_id=user_card_id)
        connection.commit()
    return True, f"Карта {row['name']} {int(row['overall'])} OVR добавлена в банк выдачи. Вывести её обратно нельзя."


async def distribute_bank_item(creator_user_id: int, target_telegram_id: int, item_id: int, amount: int = 1) -> tuple[bool, str, int]:
    if amount <= 0:
        return False, "Количество должно быть больше 0.", 0

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (creator_user_id,)).fetchone()
        if not creator or not int(creator["is_creator"]):
            connection.rollback()
            return False, "Только официальные креаторы могут выдавать награды.", 0

        target = connection.execute("SELECT id, nickname FROM users WHERE telegram_id = ?", (target_telegram_id,)).fetchone()
        if target is None:
            connection.rollback()
            return False, "Игрок с таким ID не найден.", 0
        target_id = int(target["id"])
        if target_id == creator_user_id:
            connection.rollback()
            return False, "Нельзя выдавать награды самому себе.", 0

        row = connection.execute(
            """
            SELECT cbi.*, p.name AS pack_name, c.name AS card_name, c.overall AS card_overall
            FROM creator_bank_items cbi
            LEFT JOIN packs p ON p.id = cbi.pack_id
            LEFT JOIN user_cards uc ON uc.id = cbi.user_card_id
            LEFT JOIN cards c ON c.id = uc.card_id
            WHERE cbi.id = ? AND cbi.user_id = ? AND cbi.status = 'available' AND cbi.quantity > 0
            """,
            (item_id, creator_user_id),
        ).fetchone()
        if row is None:
            connection.rollback()
            return False, "Награда в банке не найдена.", 0

        item_type = row["item_type"]
        current_qty = int(row["quantity"])
        if item_type == "card":
            amount = 1
        if amount > current_qty:
            connection.rollback()
            return False, "В банке недостаточно количества этой награды.", 0

        value = amount * int(row["value_per_unit"] or 0)

        if item_type == "currency":
            currency_code = row["currency_code"]
            grant_currency(connection, target_id, currency_code, amount)
            reward_desc = f"{format_int(amount)} {currency_code}"
        elif item_type == "pack":
            pack_id = int(row["pack_id"])
            grant_pack(connection, target_id, pack_id, amount)
            reward_desc = f"Пак: {row['pack_name'] or pack_id} ×{amount}"
        else:
            user_card_id = int(row["user_card_id"])
            connection.execute(
                """
                UPDATE user_cards
                SET user_id = ?, is_in_lineup = 0, lineup_slot = NULL,
                    trade_locked = 0, lock_reason = NULL, lock_until = NULL,
                    obtained_from = 'creator_distribution', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (target_id, user_card_id, creator_user_id),
            )
            reward_desc = f"Карта: {row['card_name']} {row['card_overall']} OVR"

        new_qty = current_qty - amount
        connection.execute(
            """
            UPDATE creator_bank_items
            SET quantity = ?, status = CASE WHEN ? <= 0 THEN 'distributed' ELSE status END, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_qty, new_qty, item_id),
        )
        connection.execute(
            """
            INSERT INTO creator_distributions (
                creator_user_id, target_user_id, reward_desc, reward_type, value_coins, amount, source_item_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (creator_user_id, target_id, reward_desc, item_type, value, amount, item_id),
        )
        connection.commit()

    return True, f"Выдано игроку {target['nickname']}: {reward_desc}. В зачёт креатора добавлено {format_int(value)} монет.", value


# Совместимость со старой выдачей coins/паков.
async def distribute_coins(creator_user_id: int, target_telegram_id: int, amount: int) -> tuple[bool, str]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM creator_bank_items
            WHERE user_id = ? AND item_type = 'currency' AND currency_code = 'coins'
              AND status = 'available' AND quantity >= ?
            ORDER BY id LIMIT 1
            """,
            (creator_user_id, amount),
        ).fetchone()
    if not row:
        return False, "Недостаточно Coins в банке выдачи."
    ok, msg, _ = await distribute_bank_item(creator_user_id, target_telegram_id, int(row["id"]), amount)
    return ok, msg


async def distribute_pack(creator_user_id: int, target_telegram_id: int, pack_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM creator_bank_items
            WHERE user_id = ? AND item_type = 'pack' AND pack_id = ?
              AND status = 'available' AND quantity >= 1
            ORDER BY id LIMIT 1
            """,
            (creator_user_id, pack_id),
        ).fetchone()
    if not row:
        return False, "Такого пака нет в банке выдачи."
    ok, msg, _ = await distribute_bank_item(creator_user_id, target_telegram_id, int(row["id"]), 1)
    return ok, msg


async def get_distribution_history(user_id: int, limit: int = 10) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT d.reward_desc, d.value_coins, d.created_at, u.nickname AS target_nickname
            FROM creator_distributions d
            JOIN users u ON u.id = d.target_user_id
            WHERE d.creator_user_id = ?
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

async def list_creators() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                u.id, u.nickname, u.telegram_id, u.creator_level, u.creator_channel,
                u.creator_subscribers, u.creator_author_code,
                COALESCE(SUM(d.value_coins), 0) AS distributed_value
            FROM users u
            LEFT JOIN creator_distributions d ON d.creator_user_id = u.id
            WHERE u.is_creator = 1
            GROUP BY u.id
            ORDER BY u.creator_level DESC, distributed_value DESC, u.nickname
            """
        ).fetchall()
    return [dict(r) for r in rows]


async def get_creator_detail(user_id: int) -> dict | None:
    creators = await list_creators()
    return next((c for c in creators if int(c["id"]) == int(user_id)), None)


async def pay_weekly_rewards() -> WeeklyPayoutResult:
    """Начисляет недельные награды в банк выдачи всем активным креаторам уровня 1–5."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creators = connection.execute(
            "SELECT id, telegram_id, creator_level FROM users WHERE is_creator = 1 AND creator_level BETWEEN 1 AND 5"
        ).fetchall()

        total_coins = 0
        total_packs = 0
        telegram_ids: list[int] = []

        for creator in creators:
            user_id = int(creator["id"])
            level = int(creator["creator_level"])
            cfg = _get_level_config(connection, level)
            if cfg is None:
                continue

            if cfg.weekly_coins > 0:
                _upsert_bank_item(connection, user_id, "currency", cfg.weekly_coins, 1, currency_code="coins")
                total_coins += cfg.weekly_coins

            elite_pack_id = _find_pack_id_for_kind(connection, cfg.weekly_elite_pack_id, "elite")
            legendary_pack_id = _find_pack_id_for_kind(connection, cfg.weekly_legendary_pack_id, "legendary")
            total_packs += _grant_creator_bank_pack(connection, user_id, elite_pack_id, cfg.weekly_elite_packs)
            total_packs += _grant_creator_bank_pack(connection, user_id, legendary_pack_id, cfg.weekly_legendary_packs)

            connection.execute(
                "INSERT INTO creator_bonus_claims (user_id, bonus_type, level) VALUES (?, 'weekly', ?)",
                (user_id, level),
            )
            telegram_ids.append(int(creator["telegram_id"]))

        connection.commit()
    return WeeklyPayoutResult(len(creators), total_coins, total_packs, telegram_ids)


async def creator_weekly_rewards_loop(bot) -> None:
    while True:
        try:
            enabled = await get_bool_setting("creator_weekly_rewards_enabled", True)
            interval_hours = await get_int_setting("creator_weekly_rewards_interval_hours", 168, minimum=24)
            last_raw = await get_setting("creator_weekly_last_paid_at", "")
            now = datetime.now(timezone.utc)
            should_pay = enabled
            if last_raw:
                try:
                    last_dt = datetime.fromisoformat(last_raw)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    should_pay = should_pay and now - last_dt >= timedelta(hours=interval_hours)
                except ValueError:
                    should_pay = True

            if should_pay:
                result = await pay_weekly_rewards()
                await set_setting_value("creator_weekly_last_paid_at", now.isoformat())
                for telegram_id in result.telegram_ids:
                    try:
                        await bot.send_message(
                            chat_id=telegram_id,
                            text="🎁 Недельные бонусы креатора добавлены в твой банк выдачи.",
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        await asyncio.sleep(3600)


async def get_user_id_by_public_id(target_telegram_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM users WHERE telegram_id = ?", (target_telegram_id,)).fetchone()
    return int(row["id"]) if row else None


async def list_packs_for_picker(limit: int = 30) -> list[tuple[int, str]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT id, name FROM packs WHERE active = 1 ORDER BY name LIMIT ?", (limit,)).fetchall()
    return [(int(row["id"]), row["name"]) for row in rows]


async def update_level_config_from_text(level: int, text: str) -> tuple[bool, str]:
    """Формат: subs|distributed|welcome|weekly_coins|elite_qty|legendary_qty|elite_pack_id|legendary_pack_id|promo|author_bp|exclusive_rating"""
    parts = [part.strip() for part in text.split("|")]
    if len(parts) != 11:
        return False, "Нужно 11 значений через |."
    try:
        values = [int(part or "0") for part in parts]
    except ValueError:
        return False, "Все значения должны быть числами. Для пустого pack_id ставь 0."

    if level < 1 or level > 5:
        return False, "Уровень должен быть 1–5."

    required_subs, required_distributed, welcome, weekly, elite_qty, legendary_qty, elite_pack_id, legendary_pack_id, promo, author_bp, exclusive_rating = values
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE creator_level_settings
            SET required_subscribers = ?,
                required_distributed_value = ?,
                welcome_coins = ?,
                weekly_coins = ?,
                weekly_elite_packs = ?,
                weekly_legendary_packs = ?,
                weekly_elite_pack_id = NULLIF(?, 0),
                weekly_legendary_pack_id = NULLIF(?, 0),
                promo_codes_weekly = ?,
                author_code_percent_bp = ?,
                exclusive_card_rating = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE level = ?
            """,
            (
                required_subs,
                required_distributed,
                welcome,
                weekly,
                elite_qty,
                legendary_qty,
                elite_pack_id,
                legendary_pack_id,
                promo,
                author_bp,
                exclusive_rating,
                level,
            ),
        )
        connection.commit()
    return True, "Настройки уровня обновлены."


async def update_level_personal_rewards(level: int, text: str) -> tuple[bool, str]:
    if level < 1 or level > 5:
        return False, "Уровень должен быть 1–5."
    with get_connection() as connection:
        connection.execute(
            "UPDATE creator_level_settings SET personal_rewards_text = ?, updated_at = CURRENT_TIMESTAMP WHERE level = ?",
            (text.strip()[:1500], level),
        )
        connection.commit()
    return True, "Личные награды уровня обновлены."


def format_level_config_for_admin(cfg: CreatorLevelConfig) -> str:
    return (
        f"<b>{cfg.level} уровень</b>\n"
        f"👥 Подписчики: <b>{format_int(cfg.required_subscribers)}</b>\n"
        f"🎁 Разыграно: <b>{format_int(cfg.required_distributed_value)}</b> монет\n"
        f"🚀 Вступительные: <b>{format_int(cfg.welcome_coins)}</b> монет\n"
        f"📅 Неделя: <b>{format_int(cfg.weekly_coins)}</b> монет, "
        f"Elite ×{cfg.weekly_elite_packs}, Legendary ×{cfg.weekly_legendary_packs}\n"
        f"🎫 Промокоды/нед.: <b>{cfg.promo_codes_weekly}</b>\n"
        f"✍️ Код автора: <b>{cfg.author_code_percent_bp / 100:.2f}%</b>\n"
        f"🃏 Эксклюзивная карта: <b>{cfg.exclusive_card_rating or 'нет'}</b>\n"
        f"🏅 Личные награды: {escape(cfg.personal_rewards_text or '—', quote=False)}"
    )
