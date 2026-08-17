"""RANKED MODE — Ranked Pass: 60 уровней, 3 линии (FREE/GOLD/PLATINUM), автоматический
XP (раздел PASS XP ТЗ: "не добавлять quests" — XP начисляется прямо в
`ranked_core.play_ranked_match()`/`ranked_packs.open_ranked_pack()`, не через квесты).

Смоделирован по образцу `app.services.hockey_pass.py` (см. план, раздел 0), но новые
таблицы, не общие строки: у существующего Pass жёсткий `CHECK(level BETWEEN 1 AND 40)`
и всего 2 линии (free/premium) — под 60 уровней/3 линии понадобилась бы та же
пересборка таблицы, что уже сделана один раз для `war2_cosmetic_items`
(`app/database/db.py:migrate_cosmetic_catalog_shared_types`); отдельные новые таблицы
проще и безопаснее для уже работающего Hockey Pass.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.card_distribution_policy import is_admin_only_card
from app.services.ranked_common import RankedError


def calculate_ranked_level(xp: int, points_per_level: int, levels_count: int) -> int:
    """Та же формула, что и app.services.hockey_pass.calculate_level(), но
    параметризована (там levels_count=40 зашит буквально)."""
    if points_per_level <= 0:
        return 1
    return min(levels_count, max(1, xp // points_per_level + 1))


@dataclass(frozen=True)
class RankedPass:
    id: int
    season_id: int | None
    title: str
    levels_count: int
    points_per_level: int
    gold_currency_code: str | None
    gold_price_amount: int
    platinum_currency_code: str | None
    platinum_price_amount: int
    upgrade_currency_code: str | None
    upgrade_price_amount: int


@dataclass(frozen=True)
class UserRankedPassState:
    gold_unlocked: bool
    platinum_unlocked: bool
    xp: int
    level: int


def _row_to_pass(row: sqlite3.Row) -> RankedPass:
    return RankedPass(
        id=int(row["id"]),
        season_id=int(row["season_id"]) if row["season_id"] is not None else None,
        title=row["title"],
        levels_count=int(row["levels_count"]),
        points_per_level=int(row["points_per_level"]),
        gold_currency_code=row["gold_currency_code"],
        gold_price_amount=int(row["gold_price_amount"]),
        platinum_currency_code=row["platinum_currency_code"],
        platinum_price_amount=int(row["platinum_price_amount"]),
        upgrade_currency_code=row["upgrade_currency_code"],
        upgrade_price_amount=int(row["upgrade_price_amount"]),
    )


async def get_active_pass() -> RankedPass | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM ranked_passes WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return _row_to_pass(row) if row is not None else None


def _season_xp(connection: sqlite3.Connection, season_id: int | None, user_id: int) -> int:
    if season_id is None:
        return 0
    row = connection.execute(
        "SELECT ranked_xp FROM ranked_player_stats WHERE season_id = ? AND user_id = ?", (season_id, user_id)
    ).fetchone()
    return int(row["ranked_xp"]) if row else 0


async def get_user_pass_state(user_id: int, pass_id: int) -> UserRankedPassState:
    with get_connection() as connection:
        pass_row = connection.execute("SELECT * FROM ranked_passes WHERE id = ?", (pass_id,)).fetchone()
        if pass_row is None:
            raise RankedError("PASS_NOT_FOUND", "Ranked Pass не найден.")
        user_row = connection.execute(
            "SELECT gold_unlocked, platinum_unlocked FROM user_ranked_passes WHERE user_id = ? AND pass_id = ?",
            (user_id, pass_id),
        ).fetchone()
        xp = _season_xp(connection, pass_row["season_id"], user_id)

    level = calculate_ranked_level(xp, int(pass_row["points_per_level"]), int(pass_row["levels_count"]))
    return UserRankedPassState(
        gold_unlocked=bool(user_row["gold_unlocked"]) if user_row else False,
        platinum_unlocked=bool(user_row["platinum_unlocked"]) if user_row else False,
        xp=xp,
        level=level,
    )


def _deliver_reward(connection: sqlite3.Connection, user_id: int, reward: sqlite3.Row) -> None:
    reward_type = reward["reward_type"]
    if reward_type == "currency" and reward["currency_code"]:
        connection.execute(
            """
            INSERT INTO currency_balances (user_id, currency_code, amount) VALUES (?, ?, ?)
            ON CONFLICT(user_id, currency_code) DO UPDATE SET amount = amount + excluded.amount, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, reward["currency_code"], int(reward["amount"])),
        )
    elif reward_type == "pack" and reward["pack_id"]:
        # ranked_pass_rewards.pack_id -> общий packs (та же семантика, что у
        # hockey_pass_rewards) — в отличие от ranked_league_rewards.pack_id, который
        # ссылается на тематические ranked_packs (см. ranked_core.py).
        connection.execute(
            """
            INSERT INTO user_packs (user_id, pack_id, quantity) VALUES (?, ?, 1)
            ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + 1, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, reward["pack_id"]),
        )
    elif reward_type == "card" and reward["card_id"]:
        if is_admin_only_card(connection, int(reward["card_id"])):
            raise RankedError("ADMIN_ONLY_COLLECTION", "Leaders выдаются только администрацией.")
        connection.execute(
            "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'ranked_pass')",
            (user_id, reward["card_id"]),
        )
    elif reward_type == "cosmetic" and reward["cosmetic_item_id"]:
        item = connection.execute(
            "SELECT type, rarity FROM war2_cosmetic_items WHERE id = ?", (reward["cosmetic_item_id"],)
        ).fetchone()
        if item is not None:
            connection.execute(
                """
                INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source)
                VALUES (?, ?, ?, ?, 'ranked_pass')
                """,
                (user_id, reward["cosmetic_item_id"], item["type"], item["rarity"]),
            )


async def claim_reward(user_id: int, reward_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        reward = connection.execute("SELECT * FROM ranked_pass_rewards WHERE id = ? AND active = 1", (reward_id,)).fetchone()
        if reward is None:
            connection.rollback()
            raise RankedError("REWARD_NOT_FOUND", "Награда не найдена.")

        pass_row = connection.execute("SELECT * FROM ranked_passes WHERE id = ?", (reward["pass_id"],)).fetchone()
        state_row = connection.execute(
            "SELECT gold_unlocked, platinum_unlocked FROM user_ranked_passes WHERE user_id = ? AND pass_id = ?",
            (user_id, reward["pass_id"]),
        ).fetchone()
        gold_unlocked = bool(state_row["gold_unlocked"]) if state_row else False
        platinum_unlocked = bool(state_row["platinum_unlocked"]) if state_row else False

        track = reward["track"]
        if track == "gold" and not gold_unlocked:
            connection.rollback()
            raise RankedError("GOLD_LOCKED", "Нужен Gold Pass, чтобы получить эту награду.")
        if track == "platinum" and not platinum_unlocked:
            connection.rollback()
            raise RankedError("PLATINUM_LOCKED", "Нужен Platinum Pass, чтобы получить эту награду.")

        xp = _season_xp(connection, pass_row["season_id"], user_id)
        level = calculate_ranked_level(xp, int(pass_row["points_per_level"]), int(pass_row["levels_count"]))
        if int(reward["level"]) > level:
            connection.rollback()
            raise RankedError("LEVEL_NOT_REACHED", f"Нужен уровень {reward['level']}, у вас {level}.")

        try:
            connection.execute(
                "INSERT INTO user_ranked_pass_rewards (user_id, reward_id) VALUES (?, ?)", (user_id, reward_id)
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise RankedError("ALREADY_CLAIMED", "Награда уже получена.") from error

        _deliver_reward(connection, user_id, reward)
        connection.commit()


async def purchase_gold(user_id: int, pass_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        pass_row = connection.execute("SELECT * FROM ranked_passes WHERE id = ? AND active = 1", (pass_id,)).fetchone()
        if pass_row is None:
            connection.rollback()
            raise RankedError("PASS_NOT_FOUND", "Ranked Pass не найден.")
        if not pass_row["gold_currency_code"]:
            connection.rollback()
            raise RankedError("PASS_NOT_PURCHASABLE", "Gold Pass недоступен для покупки.")

        state_row = connection.execute(
            "SELECT gold_unlocked FROM user_ranked_passes WHERE user_id = ? AND pass_id = ?", (user_id, pass_id)
        ).fetchone()
        if state_row and state_row["gold_unlocked"]:
            connection.rollback()
            raise RankedError("GOLD_ALREADY_UNLOCKED", "Gold Pass уже куплен.")

        price = int(pass_row["gold_price_amount"])
        balance_row = connection.execute(
            "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
            (user_id, pass_row["gold_currency_code"]),
        ).fetchone()
        balance = int(balance_row["amount"]) if balance_row else 0
        if balance < price:
            connection.rollback()
            raise RankedError("INSUFFICIENT_FUNDS", "Недостаточно средств для покупки Gold Pass.")

        connection.execute(
            "UPDATE currency_balances SET amount = amount - ? WHERE user_id = ? AND currency_code = ?",
            (price, user_id, pass_row["gold_currency_code"]),
        )
        connection.execute(
            """
            INSERT INTO user_ranked_passes (user_id, pass_id, gold_unlocked, purchased_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, pass_id) DO UPDATE SET gold_unlocked = 1, purchased_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, pass_id),
        )
        connection.commit()


async def upgrade_gold_to_platinum(user_id: int, pass_id: int) -> int:
    """PASS PURCHASE ТЗ: "После покупки: выдать все уже открытые Platinum rewards" —
    ретроактивная выдача всех уровней <= текущего по линии 'platinum', ещё не
    полученных. Возвращает количество выданных наград (для UI-подтверждения)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        pass_row = connection.execute("SELECT * FROM ranked_passes WHERE id = ? AND active = 1", (pass_id,)).fetchone()
        if pass_row is None:
            connection.rollback()
            raise RankedError("PASS_NOT_FOUND", "Ranked Pass не найден.")

        state_row = connection.execute(
            "SELECT gold_unlocked, platinum_unlocked FROM user_ranked_passes WHERE user_id = ? AND pass_id = ?",
            (user_id, pass_id),
        ).fetchone()
        if not state_row or not state_row["gold_unlocked"]:
            connection.rollback()
            raise RankedError("GOLD_REQUIRED", "Сначала нужен Gold Pass.")
        if state_row["platinum_unlocked"]:
            connection.rollback()
            raise RankedError("PLATINUM_ALREADY_UNLOCKED", "Platinum Pass уже куплен.")

        if not pass_row["upgrade_currency_code"]:
            connection.rollback()
            raise RankedError("UPGRADE_NOT_AVAILABLE", "Апгрейд до Platinum недоступен.")
        price = int(pass_row["upgrade_price_amount"])
        balance_row = connection.execute(
            "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
            (user_id, pass_row["upgrade_currency_code"]),
        ).fetchone()
        balance = int(balance_row["amount"]) if balance_row else 0
        if balance < price:
            connection.rollback()
            raise RankedError("INSUFFICIENT_FUNDS", "Недостаточно средств для апгрейда до Platinum.")

        connection.execute(
            "UPDATE currency_balances SET amount = amount - ? WHERE user_id = ? AND currency_code = ?",
            (price, user_id, pass_row["upgrade_currency_code"]),
        )
        connection.execute(
            """
            UPDATE user_ranked_passes
            SET platinum_unlocked = 1, platinum_purchased_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND pass_id = ?
            """,
            (user_id, pass_id),
        )

        xp = _season_xp(connection, pass_row["season_id"], user_id)
        current_level = calculate_ranked_level(xp, int(pass_row["points_per_level"]), int(pass_row["levels_count"]))

        platinum_rewards = connection.execute(
            "SELECT * FROM ranked_pass_rewards WHERE pass_id = ? AND track = 'platinum' AND level <= ? AND active = 1",
            (pass_id, current_level),
        ).fetchall()
        granted = 0
        for reward in platinum_rewards:
            try:
                connection.execute(
                    "INSERT INTO user_ranked_pass_rewards (user_id, reward_id) VALUES (?, ?)", (user_id, reward["id"])
                )
            except sqlite3.IntegrityError:
                continue  # уже получена раньше (например, в free/gold-дубле того же уровня)
            _deliver_reward(connection, user_id, reward)
            granted += 1

        connection.commit()

    return granted
