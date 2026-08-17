"""RANKED MODE — открытие Ranked-паков: карты/валюта/XP/косметика за слот (раздел
RANKED PACK ТЗ). Параллельная, Ranked-специфичная система — не расширение
app.services.packs.py, у которого слот умеет выдавать только карту (см. план,
раздел 0: расширять общий, активно используемый пак-движок ради одной фичи —
непропорциональный риск)."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.db import get_connection
from app.services.ranked_common import RankedError


@dataclass(frozen=True)
class RankedPackRewardItem:
    reward_type: str
    title: str
    amount: int = 0
    card_id: int | None = None


@dataclass(frozen=True)
class RankedPackOpeningResult:
    pack_code: str
    rewards: list[RankedPackRewardItem]


async def grant_ranked_pack(user_id: int, pack_id: int, quantity: int = 1) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_ranked_packs (user_id, pack_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + excluded.quantity, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, pack_id, quantity),
        )
        connection.commit()


async def open_ranked_pack(user_id: int, pack_id: int) -> RankedPackOpeningResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        pack_row = connection.execute("SELECT * FROM ranked_packs WHERE id = ? AND active = 1", (pack_id,)).fetchone()
        if pack_row is None:
            connection.rollback()
            raise RankedError("PACK_NOT_FOUND", "Пак не найден.")

        owned = connection.execute(
            "SELECT quantity FROM user_ranked_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()
        if owned is None or int(owned["quantity"]) <= 0:
            connection.rollback()
            raise RankedError("PACK_NOT_OWNED", "Этого пака пока нет в вашей коллекции.")

        slots = connection.execute(
            "SELECT * FROM ranked_pack_slots WHERE pack_id = ? AND active = 1 ORDER BY slot_number", (pack_id,)
        ).fetchall()
        if not slots:
            connection.rollback()
            raise RankedError("PACK_NOT_CONFIGURED", "Пак ещё не настроен администрацией.")

        active_season_row = connection.execute("SELECT id FROM ranked_seasons WHERE status = 'active'").fetchone()
        active_season_id = int(active_season_row["id"]) if active_season_row is not None else None

        rewards: list[RankedPackRewardItem] = []
        for slot in slots:
            reward_type = slot["reward_type"]

            if reward_type == "card":
                card_row = connection.execute(
                    """
                    SELECT cards.id, cards.name FROM ranked_pack_cards
                    JOIN cards ON cards.id = ranked_pack_cards.card_id
                    JOIN collections ON collections.id = cards.collection_id
                    WHERE ranked_pack_cards.pack_id = ? AND cards.active = 1
                      AND LOWER(TRIM(collections.name)) != 'leaders'
                      AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders'
                    ORDER BY RANDOM() LIMIT 1
                    """,
                    (pack_id,),
                ).fetchone()
                if card_row is None:
                    continue
                connection.execute(
                    "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, ?)",
                    (user_id, card_row["id"], pack_row["code"]),
                )
                rewards.append(RankedPackRewardItem(reward_type="card", title=card_row["name"], card_id=int(card_row["id"])))

            elif reward_type == "currency" and slot["currency_code"]:
                amount = int(slot["amount"])
                connection.execute(
                    """
                    INSERT INTO currency_balances (user_id, currency_code, amount) VALUES (?, ?, ?)
                    ON CONFLICT(user_id, currency_code) DO UPDATE SET amount = amount + excluded.amount, updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, slot["currency_code"], amount),
                )
                rewards.append(RankedPackRewardItem(reward_type="currency", title=slot["currency_code"], amount=amount))

            elif reward_type == "xp":
                amount = int(slot["amount"])
                if active_season_id is not None:
                    connection.execute(
                        """
                        INSERT INTO ranked_player_stats (season_id, user_id, ranked_xp) VALUES (?, ?, ?)
                        ON CONFLICT(season_id, user_id) DO UPDATE SET ranked_xp = ranked_xp + excluded.ranked_xp, updated_at = CURRENT_TIMESTAMP
                        """,
                        (active_season_id, user_id, amount),
                    )
                rewards.append(RankedPackRewardItem(reward_type="xp", title="Ranked XP", amount=amount))

            elif reward_type == "cosmetic" and slot["cosmetic_item_id"]:
                item = connection.execute(
                    "SELECT type, rarity, title FROM war2_cosmetic_items WHERE id = ?", (slot["cosmetic_item_id"],)
                ).fetchone()
                if item is not None:
                    connection.execute(
                        """
                        INSERT INTO user_cosmetic_items (owner_id, cosmetic_item_id, type, rarity, source)
                        VALUES (?, ?, ?, ?, 'ranked_pack')
                        """,
                        (user_id, slot["cosmetic_item_id"], item["type"], item["rarity"]),
                    )
                    rewards.append(RankedPackRewardItem(reward_type="cosmetic", title=item["title"]))

        connection.execute(
            "UPDATE user_ranked_packs SET quantity = quantity - 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND pack_id = ?",
            (user_id, pack_id),
        )
        connection.commit()

    return RankedPackOpeningResult(pack_code=pack_row["code"], rewards=rewards)
