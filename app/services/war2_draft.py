"""CLAN WAR 2.0 — Draft Pool (24 карты, Base Collection) + Snake Draft (6 пиков).

24 CARD POOL: 3 GK + 6 DEF + 15 FWD, только из коллекций с `is_exclusive = 0`
(BASE_COLLECTION — раздел "COLLECTION SYSTEM" ТЗ). Пул снапшотится в
`war2_draft_pools.card_ids_json` в момент генерации, чтобы дальнейший драфт был
стабилен, даже если позже поменяется состояние живых `cards` (active/удаление).

Snake Draft: раунд 1 — user затем opponent, раунд 2 — opponent затем user, и т.д.
Только инициатор матча драфтит интерактивно (см. docs/CLAN_WAR_2_SPEC.md, раздел
"почему не оба игрока живьём") — соперник добирается `auto_pick_for_opponent()`
эвристикой сразу после каждого пика игрока.
"""

from __future__ import annotations

import json
import sqlite3

from app.database.db import get_connection
from app.services.bot_card_policy import (
    BOT_BLOCKED_COLLECTION_CODE,
    BOT_BLOCKED_COLLECTION_NAME,
    is_bot_card_allowed,
)
from app.services.lineup import LineupCard
from app.services.war2_common import War2Error

POOL_POSITION_QUOTAS: list[tuple[str, int]] = [("G", 3), ("D", 6), ("F", 15)]
POOL_SIZE = sum(count for _position, count in POOL_POSITION_QUOTAS)
PICKS_PER_SIDE = 6
ROSTER_POSITION_QUOTAS: dict[str, int] = {"F": 3, "D": 2, "G": 1}


def build_ephemeral_lineup_card(row: sqlite3.Row) -> LineupCard:
    """cards-строка (никогда не user_cards!) -> LineupCard для движка симуляции.

    `user_card_id` — отрицательный sentinel (никогда не реальный user_cards.id):
    карты драфт-пула не принадлежат игроку, это "одолженный" на один матч ростер.
    """
    return LineupCard(
        user_card_id=-int(row["id"]),
        card_id=int(row["id"]),
        name=row["name"],
        player_key=row["player_key"],
        position=row["position"],
        overall=int(row["overall"]),
        team=row["team"],
        country=row["country"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
        image_path=row["image_path"],
        lineup_slot=None,
        collection_code=row["collection_code"],
        salary=int(row["salary"] or 0),
    )


def compute_war2_lineup_ovr(cards: list[LineupCard]) -> int:
    """Простое среднее без бонуса химии. CLAN WAR использует тот же размер состава
    3 FWD / 2 DEF / 1 GK, но собственную матчевую механику без бонуса химии."""
    if not cards:
        return 0
    return round(sum(card.overall for card in cards) / len(cards))


def _fetch_cards_by_ids(connection: sqlite3.Connection, card_ids: list[int]) -> dict[int, sqlite3.Row]:
    if not card_ids:
        return {}
    placeholders = ", ".join("?" for _ in card_ids)
    rows = connection.execute(
        f"""
        SELECT cards.id, cards.name, cards.player_key, cards.position, cards.overall,
               cards.team, cards.country, cards.rarity, cards.image_path, cards.salary,
               collections.name AS collection_name, collections.code AS collection_code
        FROM cards
        JOIN collections ON collections.id = cards.collection_id
        WHERE cards.id IN ({placeholders})
        """,
        card_ids,
    ).fetchall()
    return {int(row["id"]): row for row in rows}


async def generate_draft_pool(match_id: int) -> list[sqlite3.Row]:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            "SELECT card_ids_json FROM war2_draft_pools WHERE match_id = ?", (match_id,)
        ).fetchone()
        if existing is not None:
            connection.rollback()
            pool_ids = json.loads(existing["card_ids_json"])
            rows_by_id = _fetch_cards_by_ids(connection, pool_ids)
            return [rows_by_id[card_id] for card_id in pool_ids if card_id in rows_by_id]

        pool_ids: list[int] = []
        for position, count in POOL_POSITION_QUOTAS:
            rows = connection.execute(
                """
                SELECT cards.id FROM cards
                JOIN collections ON collections.id = cards.collection_id
                WHERE collections.is_exclusive = 0 AND collections.active = 1
                  AND TRIM(collections.name) COLLATE NOCASE != ?
                  AND TRIM(COALESCE(collections.code, '')) COLLATE NOCASE != ?
                  AND cards.active = 1 AND cards.position = ?
                ORDER BY RANDOM() LIMIT ?
                """,
                (BOT_BLOCKED_COLLECTION_NAME, BOT_BLOCKED_COLLECTION_CODE, position, count),
            ).fetchall()
            if len(rows) < count:
                connection.rollback()
                raise War2Error(
                    "DRAFT_POOL_INSUFFICIENT_CARDS",
                    f"Недостаточно карт позиции {position} для формирования пула Draft "
                    f"(нужно {count}, доступно {len(rows)}). Обратитесь к администрации.",
                )
            pool_ids.extend(int(row["id"]) for row in rows)

        connection.execute(
            "INSERT INTO war2_draft_pools (match_id, card_ids_json) VALUES (?, ?)",
            (match_id, json.dumps(pool_ids)),
        )
        rows_by_id = _fetch_cards_by_ids(connection, pool_ids)
        connection.commit()

    return [rows_by_id[card_id] for card_id in pool_ids if card_id in rows_by_id]


async def build_ephemeral_lineup(card_ids: list[int]) -> list[LineupCard]:
    """Публичный хелпер: список card_id (drafted или Clone War) -> список LineupCard,
    готовый для build_simulation. Используется war2_core для обеих сторон матча."""
    with get_connection() as connection:
        rows_by_id = _fetch_cards_by_ids(connection, card_ids)
    return [build_ephemeral_lineup_card(rows_by_id[card_id]) for card_id in card_ids if card_id in rows_by_id]


async def get_pool_cards(match_id: int) -> list[sqlite3.Row]:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT card_ids_json FROM war2_draft_pools WHERE match_id = ?", (match_id,)
        ).fetchone()
        if row is None:
            return []
        pool_ids = json.loads(row["card_ids_json"])
        rows_by_id = _fetch_cards_by_ids(connection, pool_ids)
    return [rows_by_id[card_id] for card_id in pool_ids if card_id in rows_by_id]


def _picker_for(round_number: int, first: str) -> tuple[str, str]:
    """Snake order: нечётный раунд — first затем second, чётный — наоборот."""
    second = "opponent" if first == "user" else "user"
    if round_number % 2 == 1:
        return first, second
    return second, first


def _position_counts(pool: list[sqlite3.Row], card_ids: list[int]) -> dict[str, int]:
    selected = set(int(card_id) for card_id in card_ids)
    counts = {position: 0 for position in ROSTER_POSITION_QUOTAS}
    for row in pool:
        if int(row["id"]) in selected:
            position = str(row["position"]).upper()
            if position in counts:
                counts[position] += 1
    return counts


def allowed_remaining_for_picker(state: dict, picker: str) -> list[sqlite3.Row]:
    """Карты, которые ещё можно выбрать без нарушения 3F/2D/1G."""
    picks = state[f"{picker}_picks"]
    counts = _position_counts(state["pool"], picks)
    return [
        row for row in state["remaining"]
        if str(row["position"]).upper() in ROSTER_POSITION_QUOTAS
        and counts[str(row["position"]).upper()] < ROSTER_POSITION_QUOTAS[str(row["position"]).upper()]
    ]


def _validate_roster_positions(cards: list[LineupCard]) -> None:
    counts = {position: 0 for position in ROSTER_POSITION_QUOTAS}
    for card in cards:
        position = str(card.position).upper()
        if position in counts:
            counts[position] += 1
    if counts != ROSTER_POSITION_QUOTAS:
        raise War2Error(
            "DRAFT_INVALID_POSITIONS",
            "Состав CLAN WAR должен содержать 3 FWD, 2 DEF и 1 GK.",
        )


async def get_draft_state(match_id: int) -> dict:
    pool = await get_pool_cards(match_id)
    with get_connection() as connection:
        picks = connection.execute(
            "SELECT round_number, pick_order, picker, card_id FROM war2_draft_picks WHERE match_id = ? ORDER BY pick_order",
            (match_id,),
        ).fetchall()

    picked_ids = {int(p["card_id"]) for p in picks}
    user_picks = [int(p["card_id"]) for p in picks if p["picker"] == "user"]
    opponent_picks = [int(p["card_id"]) for p in picks if p["picker"] == "opponent"]
    remaining = [row for row in pool if int(row["id"]) not in picked_ids]

    total_picks = len(picks)
    current_round = total_picks // 2 + 1
    picker_first, picker_second = _picker_for(current_round, "user")
    picks_this_round = total_picks % 2
    current_picker = picker_first if picks_this_round == 0 else picker_second

    is_complete = len(user_picks) >= PICKS_PER_SIDE and len(opponent_picks) >= PICKS_PER_SIDE

    return {
        "pool": pool,
        "remaining": remaining,
        "user_picks": user_picks,
        "opponent_picks": opponent_picks,
        "current_round": current_round if not is_complete else PICKS_PER_SIDE,
        "current_picker": None if is_complete else current_picker,
        "is_complete": is_complete,
        "pick_order_next": total_picks + 1,
    }


async def record_pick(match_id: int, picker: str, card_id: int) -> None:
    state = await get_draft_state(match_id)
    if state["is_complete"]:
        raise War2Error("DRAFT_ALREADY_COMPLETE", "Драфт уже завершён.")
    if state["current_picker"] != picker:
        raise War2Error("DRAFT_NOT_YOUR_TURN", "Сейчас не ваш пик.")

    pool_ids = {int(row["id"]) for row in state["pool"]}
    if card_id not in pool_ids:
        raise War2Error("DRAFT_CARD_NOT_IN_POOL", "Эта карта не входит в пул драфта.")
    if card_id in set(state["user_picks"]) | set(state["opponent_picks"]):
        raise War2Error("DRAFT_CARD_ALREADY_PICKED", "Эта карта уже выбрана.")

    allowed_ids = {int(row["id"]) for row in allowed_remaining_for_picker(state, picker)}
    if card_id not in allowed_ids:
        raise War2Error(
            "DRAFT_POSITION_QUOTA_REACHED",
            "Эта позиция уже заполнена. Нужно собрать 3 FWD, 2 DEF и 1 GK.",
        )

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "INSERT INTO war2_draft_picks (match_id, round_number, pick_order, picker, card_id) VALUES (?, ?, ?, ?, ?)",
                (match_id, state["current_round"], state["pick_order_next"], picker, card_id),
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise War2Error("DRAFT_CARD_ALREADY_PICKED", "Эта карта уже выбрана.") from error
        connection.commit()


async def redo_last_round(match_id: int) -> int:
    """SALARY_WAR: при превышении лимита после полного драфта — вместо отмены всего
    матча удаляем ВСЕ пики последнего раунда (и игрока, и соперника) и даём
    переиграть его. Удалять только пик игрока нельзя: opponent's раунд-N пик уже
    вставлен со своим pick_order/round_number, а current_round/current_picker в
    get_draft_state() вычисляются из ОБЩЕГО количества пиков — рассинхронизация
    сломала бы порядок snake draft. Полный раунд назад — минимальный откат, который
    не портит инвариант."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        max_round_row = connection.execute(
            "SELECT MAX(round_number) AS n FROM war2_draft_picks WHERE match_id = ?", (match_id,)
        ).fetchone()
        max_round = max_round_row["n"]
        if max_round is None:
            connection.rollback()
            raise War2Error("DRAFT_NO_PICKS_YET", "Ещё не сделано ни одного пика.")
        connection.execute(
            "DELETE FROM war2_draft_picks WHERE match_id = ? AND round_number = ?", (match_id, int(max_round))
        )
        connection.commit()
    return int(max_round)


async def auto_pick_for_opponent(match_id: int) -> int | None:
    """Автопик соперника соблюдает тот же состав 3F/2D/1G и берёт лучший OVR
    среди допустимых оставшихся карт."""
    state = await get_draft_state(match_id)
    if state["current_picker"] != "opponent" or not state["remaining"]:
        return None

    candidates = [
        row for row in allowed_remaining_for_picker(state, "opponent")
        if is_bot_card_allowed(row)
    ]
    if not candidates:
        raise War2Error(
            "DRAFT_NO_VALID_CARD",
            "Не удалось добрать корректный состав 3 FWD / 2 DEF / 1 GK.",
        )
    best = max(candidates, key=lambda row: int(row["overall"]))
    await record_pick(match_id, "opponent", int(best["id"]))
    return int(best["id"])


async def finalize_lineup_for(match_id: int, picker: str) -> list[LineupCard]:
    with get_connection() as connection:
        picks = connection.execute(
            "SELECT card_id FROM war2_draft_picks WHERE match_id = ? AND picker = ? ORDER BY round_number",
            (match_id, picker),
        ).fetchall()
        card_ids = [int(p["card_id"]) for p in picks]
        rows_by_id = _fetch_cards_by_ids(connection, card_ids)

    if len(card_ids) != PICKS_PER_SIDE:
        raise War2Error("DRAFT_INCOMPLETE", f"Драфт не завершён: выбрано {len(card_ids)} из {PICKS_PER_SIDE} карт.")

    cards = [build_ephemeral_lineup_card(rows_by_id[card_id]) for card_id in card_ids if card_id in rows_by_id]
    _validate_roster_positions(cards)
    return cards
