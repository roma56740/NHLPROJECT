"""Редактирование контента THE STRONGHOLD из admin-панели: Upgrade Chain, Fortress,
Missions, Season Track, Store, аналитика, массовые операции.

Отдельно от `stronghold_admin.py` (lifecycle/публикация/компенсации/аудит), чтобы файлы
не разрастались. Каждое изменение пишет запись в `stronghold_audit_log` (before/after).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field

from app.database.db import get_connection


def _audit(connection: sqlite3.Connection, *, event_id: int, admin_id: int, action: str, entity: str, entity_id: int, before: dict, after: dict, reason: str = "admin_edit") -> None:
    connection.execute(
        """
        INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, before, after, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, admin_id, action, entity, entity_id, json.dumps(before), json.dumps(after), reason),
    )


# ---------------------------------------------------------------------------
# Collection / Card Definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CardDefinitionAdminInfo:
    id: int
    name: str
    player_key: str
    position: str
    overall: int
    team: str
    country: str
    salary: int
    active: bool
    is_upgrade_chain_card: bool


async def list_collection_cards_admin(event_id: int, collection_code: str = "the_stronghold") -> list[CardDefinitionAdminInfo]:
    with get_connection() as connection:
        chain_card_ids = {
            int(row["id"])
            for row in connection.execute(
                """
                SELECT from_card_id AS id FROM stronghold_upgrade_steps WHERE event_id = ?
                UNION
                SELECT to_card_id AS id FROM stronghold_upgrade_steps WHERE event_id = ?
                """,
                (event_id, event_id),
            ).fetchall()
        }
        rows = connection.execute(
            """
            SELECT cards.* FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE collections.code = ?
            ORDER BY cards.overall DESC, cards.name
            """,
            (collection_code,),
        ).fetchall()
    return [
        CardDefinitionAdminInfo(
            id=int(r["id"]), name=r["name"], player_key=r["player_key"], position=r["position"],
            overall=int(r["overall"]), team=r["team"], country=r["country"], salary=int(r["salary"]),
            active=bool(r["active"]), is_upgrade_chain_card=int(r["id"]) in chain_card_ids,
        )
        for r in rows
    ]


async def update_card_salary(card_id: int, *, salary: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"salary": row["salary"]}
        connection.execute("UPDATE cards SET salary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (salary, card_id))
        _audit(connection, event_id=0, admin_id=admin_id, action="update_card_salary", entity="cards", entity_id=card_id, before=before, after={"salary": salary})
        connection.commit()


async def toggle_card_active(card_id: int, admin_id: int) -> bool:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            connection.rollback()
            return False
        new_active = 0 if bool(row["active"]) else 1
        connection.execute("UPDATE cards SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_active, card_id))
        _audit(connection, event_id=0, admin_id=admin_id, action="toggle_card_active", entity="cards", entity_id=card_id, before={"active": bool(row["active"])}, after={"active": bool(new_active)})
        connection.commit()
    return bool(new_active)


# ---------------------------------------------------------------------------
# Upgrade Chain
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UpgradeStepAdminInfo:
    id: int
    step_order: int
    from_overall: int
    to_overall: int
    ft_cost: int
    coins_cost: int


async def list_upgrade_steps(event_id: int) -> list[UpgradeStepAdminInfo]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT s.id, s.step_order, s.ft_cost, s.coins_cost, fc.overall AS from_overall, tc.overall AS to_overall
            FROM stronghold_upgrade_steps s
            JOIN cards fc ON fc.id = s.from_card_id
            JOIN cards tc ON tc.id = s.to_card_id
            WHERE s.event_id = ?
            ORDER BY s.step_order
            """,
            (event_id,),
        ).fetchall()
    return [
        UpgradeStepAdminInfo(id=int(r["id"]), step_order=int(r["step_order"]), from_overall=int(r["from_overall"]), to_overall=int(r["to_overall"]), ft_cost=int(r["ft_cost"]), coins_cost=int(r["coins_cost"]))
        for r in rows
    ]


async def update_upgrade_step_costs(step_id: int, *, ft_cost: int, coins_cost: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_upgrade_steps WHERE id = ?", (step_id,)).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"ft_cost": row["ft_cost"], "coins_cost": row["coins_cost"]}
        connection.execute(
            "UPDATE stronghold_upgrade_steps SET ft_cost = ?, coins_cost = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (ft_cost, coins_cost, step_id),
        )
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="update_upgrade_step", entity="stronghold_upgrade_steps", entity_id=step_id, before=before, after={"ft_cost": ft_cost, "coins_cost": coins_cost})
        connection.commit()


# ---------------------------------------------------------------------------
# Fortress
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FortressAdminInfo:
    id: int
    order_index: int
    title: str
    first_completion_ft: int
    repeat_coins_reward: int
    active: bool


@dataclass(frozen=True)
class FortressMatchAdminInfo:
    id: int
    order_index: int
    opponent_name: str
    opponent_ovr: int
    active: bool


async def list_fortresses_admin(event_id: int) -> list[FortressAdminInfo]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM stronghold_fortresses WHERE event_id = ? ORDER BY order_index", (event_id,)
        ).fetchall()
    return [
        FortressAdminInfo(id=int(r["id"]), order_index=int(r["order_index"]), title=r["title"], first_completion_ft=int(r["first_completion_ft"]), repeat_coins_reward=int(r["repeat_coins_reward"]), active=bool(r["active"]))
        for r in rows
    ]


async def get_fortress_matches_admin(fortress_id: int) -> list[FortressMatchAdminInfo]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM stronghold_fortress_matches WHERE fortress_id = ? ORDER BY order_index", (fortress_id,)
        ).fetchall()
    return [
        FortressMatchAdminInfo(id=int(r["id"]), order_index=int(r["order_index"]), opponent_name=r["opponent_name"], opponent_ovr=int(r["opponent_ovr"]), active=bool(r["active"]))
        for r in rows
    ]


async def update_fortress_reward(fortress_id: int, *, first_completion_ft: int, repeat_coins_reward: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_fortresses WHERE id = ?", (fortress_id,)).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"first_completion_ft": row["first_completion_ft"], "repeat_coins_reward": row["repeat_coins_reward"]}
        connection.execute(
            "UPDATE stronghold_fortresses SET first_completion_ft = ?, repeat_coins_reward = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (first_completion_ft, repeat_coins_reward, fortress_id),
        )
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="update_fortress", entity="stronghold_fortresses", entity_id=fortress_id, before=before, after={"first_completion_ft": first_completion_ft, "repeat_coins_reward": repeat_coins_reward})
        connection.commit()


async def toggle_fortress_active(fortress_id: int, admin_id: int) -> bool:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_fortresses WHERE id = ?", (fortress_id,)).fetchone()
        if row is None:
            connection.rollback()
            return False
        new_active = 0 if bool(row["active"]) else 1
        connection.execute("UPDATE stronghold_fortresses SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_active, fortress_id))
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="toggle_fortress_active", entity="stronghold_fortresses", entity_id=fortress_id, before={"active": bool(row["active"])}, after={"active": bool(new_active)})
        connection.commit()
    return bool(new_active)


async def update_fortress_match_ovr(match_id: int, *, opponent_ovr: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT m.*, f.event_id AS event_id FROM stronghold_fortress_matches m JOIN stronghold_fortresses f ON f.id = m.fortress_id WHERE m.id = ?",
            (match_id,),
        ).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"opponent_ovr": row["opponent_ovr"]}
        opponent_ovr = max(1, min(99, opponent_ovr))
        connection.execute("UPDATE stronghold_fortress_matches SET opponent_ovr = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (opponent_ovr, match_id))
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="update_fortress_match", entity="stronghold_fortress_matches", entity_id=match_id, before=before, after={"opponent_ovr": opponent_ovr})
        connection.commit()


DEFAULT_MATCH_STAR_RULES = json.dumps([
    {"type": "win"},
    {"type": "goal_diff", "min": 2},
    {"type": "clean_sheet", "max_allowed": 1},
])


async def create_fortress(event_id: int, *, title: str, description: str, first_completion_ft: int, repeat_coins_reward: int, admin_id: int) -> int:
    """Создаёт новую крепость со стандартными 6 матчами (звёзды/OVR — конфигурация по
    умолчанию, редактируемая после создания через update_fortress_match_ovr)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        max_order_row = connection.execute("SELECT COALESCE(MAX(order_index), 0) AS m FROM stronghold_fortresses WHERE event_id = ?", (event_id,)).fetchone()
        order_index = int(max_order_row["m"]) + 1
        code = f"custom-fortress-{uuid.uuid4().hex[:10]}"

        cursor = connection.execute(
            """
            INSERT INTO stronghold_fortresses (event_id, order_index, code, title, description, is_boss, first_completion_ft, repeat_coins_reward, active)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1)
            """,
            (event_id, order_index, code, title, description, first_completion_ft, repeat_coins_reward),
        )
        fortress_id = int(cursor.lastrowid)

        base_ovr = min(65 + (order_index - 1) * 2, 90)
        for match_order in range(1, 7):
            opponent_ovr = min(base_ovr + match_order, 99)
            connection.execute(
                """
                INSERT INTO stronghold_fortress_matches (fortress_id, order_index, opponent_name, opponent_ovr, star_rules, active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (fortress_id, match_order, f"{title} Guard {match_order}", opponent_ovr, DEFAULT_MATCH_STAR_RULES),
            )

        _audit(connection, event_id=event_id, admin_id=admin_id, action="create_fortress", entity="stronghold_fortresses", entity_id=fortress_id, before={}, after={"code": code, "title": title, "order_index": order_index})
        connection.commit()
    return fortress_id


async def add_fortress_match(fortress_id: int, *, opponent_name: str, opponent_ovr: int, admin_id: int) -> int:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        fortress_row = connection.execute("SELECT event_id FROM stronghold_fortresses WHERE id = ?", (fortress_id,)).fetchone()
        if fortress_row is None:
            connection.rollback()
            return 0
        max_order_row = connection.execute("SELECT COALESCE(MAX(order_index), 0) AS m FROM stronghold_fortress_matches WHERE fortress_id = ?", (fortress_id,)).fetchone()
        order_index = int(max_order_row["m"]) + 1
        opponent_ovr = max(1, min(99, opponent_ovr))
        cursor = connection.execute(
            """
            INSERT INTO stronghold_fortress_matches (fortress_id, order_index, opponent_name, opponent_ovr, star_rules, active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (fortress_id, order_index, opponent_name, opponent_ovr, DEFAULT_MATCH_STAR_RULES),
        )
        match_id = int(cursor.lastrowid)
        _audit(connection, event_id=int(fortress_row["event_id"]), admin_id=admin_id, action="add_fortress_match", entity="stronghold_fortress_matches", entity_id=match_id, before={}, after={"order_index": order_index, "opponent_name": opponent_name, "opponent_ovr": opponent_ovr})
        connection.commit()
    return match_id


async def toggle_fortress_match_active(match_id: int, admin_id: int) -> bool:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT m.*, f.event_id AS event_id FROM stronghold_fortress_matches m JOIN stronghold_fortresses f ON f.id = m.fortress_id WHERE m.id = ?",
            (match_id,),
        ).fetchone()
        if row is None:
            connection.rollback()
            return False
        new_active = 0 if bool(row["active"]) else 1
        connection.execute("UPDATE stronghold_fortress_matches SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_active, match_id))
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="toggle_fortress_match_active", entity="stronghold_fortress_matches", entity_id=match_id, before={"active": bool(row["active"])}, after={"active": bool(new_active)})
        connection.commit()
    return bool(new_active)


# ---------------------------------------------------------------------------
# Missions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionAdminInfo:
    id: int
    code: str
    type: str
    title: str
    condition_type: str
    target_value: int
    reward_ft: int
    reward_coins: int
    reward_xp: int
    active: bool


MISSION_CONDITION_TYPES = [
    "play_matches", "win_matches", "fortress_match_complete", "fortress_complete",
    "earn_stars", "use_collection_card", "upgrade_heiskanen", "endless_wave_complete",
    "spend_coins", "spend_ft", "goals_scored", "clean_sheet", "season_level_reached",
]
MISSION_TYPES = ["DAILY", "WEEKLY", "SEASONAL"]


async def list_missions_admin(event_id: int) -> list[MissionAdminInfo]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM stronghold_missions WHERE event_id = ? ORDER BY type, sort_order, id", (event_id,)).fetchall()
    return [
        MissionAdminInfo(id=int(r["id"]), code=r["code"], type=r["type"], title=r["title"], condition_type=r["condition_type"], target_value=int(r["target_value"]), reward_ft=int(r["reward_ft"]), reward_coins=int(r["reward_coins"]), reward_xp=int(r["reward_xp"]), active=bool(r["active"]))
        for r in rows
    ]


async def create_mission(event_id: int, *, type: str, title: str, condition_type: str, target_value: int, reward_ft: int, reward_coins: int, reward_xp: int, admin_id: int) -> int:
    code = f"custom_{uuid.uuid4().hex[:10]}"
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            INSERT INTO stronghold_missions (event_id, code, type, title, description, condition_type, target_value, reward_ft, reward_coins, reward_xp, active, sort_order)
            VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, 1, 999)
            """,
            (event_id, code, type, title, condition_type, target_value, reward_ft, reward_coins, reward_xp),
        )
        mission_id = int(cursor.lastrowid)
        _audit(connection, event_id=event_id, admin_id=admin_id, action="create_mission", entity="stronghold_missions", entity_id=mission_id, before={}, after={"code": code, "type": type, "title": title})
        connection.commit()
    return mission_id


async def toggle_mission_active(mission_id: int, admin_id: int) -> bool:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_missions WHERE id = ?", (mission_id,)).fetchone()
        if row is None:
            connection.rollback()
            return False
        new_active = 0 if bool(row["active"]) else 1
        connection.execute("UPDATE stronghold_missions SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_active, mission_id))
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="toggle_mission_active", entity="stronghold_missions", entity_id=mission_id, before={"active": bool(row["active"])}, after={"active": bool(new_active)})
        connection.commit()
    return bool(new_active)


async def update_mission_rewards(mission_id: int, *, target_value: int, reward_ft: int, reward_coins: int, reward_xp: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_missions WHERE id = ?", (mission_id,)).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"target_value": row["target_value"], "reward_ft": row["reward_ft"], "reward_coins": row["reward_coins"], "reward_xp": row["reward_xp"]}
        connection.execute(
            "UPDATE stronghold_missions SET target_value = ?, reward_ft = ?, reward_coins = ?, reward_xp = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target_value, reward_ft, reward_coins, reward_xp, mission_id),
        )
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="update_mission", entity="stronghold_missions", entity_id=mission_id, before=before, after={"target_value": target_value, "reward_ft": reward_ft, "reward_coins": reward_coins, "reward_xp": reward_xp})
        connection.commit()


# ---------------------------------------------------------------------------
# Season Track
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeasonLevelAdminInfo:
    id: int
    level: int
    xp_threshold: int
    reward_ft: int
    reward_coins: int


async def list_season_levels_admin(event_id: int) -> list[SeasonLevelAdminInfo]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM stronghold_season_track_levels WHERE event_id = ? ORDER BY level", (event_id,)).fetchall()
    return [
        SeasonLevelAdminInfo(id=int(r["id"]), level=int(r["level"]), xp_threshold=int(r["xp_threshold"]), reward_ft=int(r["reward_ft"]), reward_coins=int(r["reward_coins"]))
        for r in rows
    ]


async def update_season_level(level_id: int, *, xp_threshold: int, reward_ft: int, reward_coins: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_season_track_levels WHERE id = ?", (level_id,)).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"xp_threshold": row["xp_threshold"], "reward_ft": row["reward_ft"], "reward_coins": row["reward_coins"]}
        connection.execute(
            "UPDATE stronghold_season_track_levels SET xp_threshold = ?, reward_ft = ?, reward_coins = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (xp_threshold, reward_ft, reward_coins, level_id),
        )
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="update_season_level", entity="stronghold_season_track_levels", entity_id=level_id, before=before, after={"xp_threshold": xp_threshold, "reward_ft": reward_ft, "reward_coins": reward_coins})
        connection.commit()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StoreProductAdminInfo:
    id: int
    code: str
    category: str
    title: str
    price_currency_code: str
    price_amount: int
    purchase_limit: int
    active: bool


async def list_store_products_admin(event_id: int) -> list[StoreProductAdminInfo]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM stronghold_store_products WHERE event_id = ? ORDER BY category, sort_order, id", (event_id,)).fetchall()
    return [
        StoreProductAdminInfo(id=int(r["id"]), code=r["code"], category=r["category"], title=r["title"], price_currency_code=r["price_currency_code"], price_amount=int(r["price_amount"]), purchase_limit=int(r["purchase_limit"]), active=bool(r["active"]))
        for r in rows
    ]


async def get_product_contents(product_id: int) -> list[dict]:
    with get_connection() as connection:
        row = connection.execute("SELECT contents FROM stronghold_store_products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        return []
    return json.loads(row["contents"] or "[]")


def validate_product_contents(contents: list[dict]) -> list[str]:
    """Проверка структуры Bundle перед публикацией (см. INVALID_PRODUCT_CONFIGURATION
    в stronghold_store.py:purchase — та же схема item'ов)."""
    errors: list[str] = []
    if not contents:
        errors.append("Товар должен содержать хотя бы одну награду.")
    for index, item in enumerate(contents):
        item_type = item.get("type")
        if item_type == "currency":
            if item.get("currency_code") not in ("coins", "fortress_token"):
                errors.append(f"Элемент {index + 1}: некорректная валюта.")
            if int(item.get("amount", 0)) <= 0:
                errors.append(f"Элемент {index + 1}: количество должно быть больше 0.")
        elif item_type == "card":
            if not item.get("card_id"):
                errors.append(f"Элемент {index + 1}: не указан card_id.")
        elif item_type == "pack":
            if not item.get("pack_id"):
                errors.append(f"Элемент {index + 1}: не указан pack_id.")
        else:
            errors.append(f"Элемент {index + 1}: неизвестный тип '{item_type}'.")
    return errors


async def create_store_product(
    event_id: int,
    *,
    category: str,
    title: str,
    description: str,
    price_currency_code: str,
    price_amount: int,
    purchase_limit: int,
    contents: list[dict],
    admin_id: int,
) -> int:
    errors = validate_product_contents(contents)
    if errors:
        raise ValueError("; ".join(errors))

    code = f"custom_{uuid.uuid4().hex[:10]}"
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            INSERT INTO stronghold_store_products (event_id, code, category, title, description, price_currency_code, price_amount, purchase_limit, contents, active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 999)
            """,
            (event_id, code, category, title, description, price_currency_code, price_amount, purchase_limit, json.dumps(contents)),
        )
        product_id = int(cursor.lastrowid)
        _audit(connection, event_id=event_id, admin_id=admin_id, action="create_store_product", entity="stronghold_store_products", entity_id=product_id, before={}, after={"code": code, "title": title, "contents_count": len(contents)})
        connection.commit()
    return product_id


async def toggle_store_product_active(product_id: int, admin_id: int) -> bool:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_store_products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            connection.rollback()
            return False
        new_active = 0 if bool(row["active"]) else 1
        connection.execute("UPDATE stronghold_store_products SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_active, product_id))
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="toggle_store_product_active", entity="stronghold_store_products", entity_id=product_id, before={"active": bool(row["active"])}, after={"active": bool(new_active)})
        connection.commit()
    return bool(new_active)


async def update_store_product_price(product_id: int, *, price_amount: int, purchase_limit: int, admin_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_store_products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            connection.rollback()
            return
        before = {"price_amount": row["price_amount"], "purchase_limit": row["purchase_limit"]}
        connection.execute(
            "UPDATE stronghold_store_products SET price_amount = ?, purchase_limit = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (price_amount, purchase_limit, product_id),
        )
        _audit(connection, event_id=int(row["event_id"]), admin_id=admin_id, action="update_store_product", entity="stronghold_store_products", entity_id=product_id, before=before, after={"price_amount": price_amount, "purchase_limit": purchase_limit})
        connection.commit()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalyticsSummary:
    active_participants: int
    total_upgrades: int
    ft_earned: int
    ft_spent: int
    coins_spent_in_store: int
    fortress_completions: dict[int, int] = field(default_factory=dict)
    mission_claims: int = 0
    store_purchases: int = 0


async def get_analytics_summary(event_id: int) -> AnalyticsSummary:
    with get_connection() as connection:
        active_participants = connection.execute(
            "SELECT COUNT(DISTINCT user_id) AS c FROM stronghold_currency_ledger WHERE event_id = ?", (event_id,)
        ).fetchone()["c"]
        total_upgrades = connection.execute(
            "SELECT COUNT(*) AS c FROM stronghold_upgrade_transactions WHERE event_id = ? AND status = 'success'", (event_id,)
        ).fetchone()["c"]
        ft_earned = connection.execute(
            "SELECT COALESCE(SUM(delta), 0) AS s FROM stronghold_currency_ledger WHERE event_id = ? AND currency_code = 'fortress_token' AND delta > 0",
            (event_id,),
        ).fetchone()["s"]
        ft_spent = connection.execute(
            "SELECT COALESCE(SUM(-delta), 0) AS s FROM stronghold_currency_ledger WHERE event_id = ? AND currency_code = 'fortress_token' AND delta < 0",
            (event_id,),
        ).fetchone()["s"]
        coins_spent_store = connection.execute(
            "SELECT COALESCE(SUM(price_amount), 0) AS s FROM stronghold_store_purchases WHERE event_id = ? AND price_currency_code = 'coins' AND status = 'success'",
            (event_id,),
        ).fetchone()["s"]
        fortress_rows = connection.execute(
            """
            SELECT f.order_index, COUNT(*) AS c
            FROM stronghold_user_fortress_progress p
            JOIN stronghold_fortresses f ON f.id = p.fortress_id
            WHERE p.event_id = ? AND p.status = 'COMPLETED'
            GROUP BY f.order_index
            """,
            (event_id,),
        ).fetchall()
        mission_claims = connection.execute(
            """
            SELECT COUNT(*) AS c FROM stronghold_user_mission_progress ump
            JOIN stronghold_missions m ON m.id = ump.mission_id
            WHERE m.event_id = ? AND ump.reward_claimed = 1
            """,
            (event_id,),
        ).fetchone()["c"]
        store_purchases = connection.execute(
            "SELECT COUNT(*) AS c FROM stronghold_store_purchases WHERE event_id = ? AND status = 'success'", (event_id,)
        ).fetchone()["c"]

    return AnalyticsSummary(
        active_participants=int(active_participants),
        total_upgrades=int(total_upgrades),
        ft_earned=int(ft_earned),
        ft_spent=int(ft_spent),
        coins_spent_in_store=int(coins_spent_store),
        fortress_completions={int(r["order_index"]): int(r["c"]) for r in fortress_rows},
        mission_claims=int(mission_claims),
        store_purchases=int(store_purchases),
    )


# ---------------------------------------------------------------------------
# Mass operations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MassOpResult:
    affected: int
    errors: list[str]


async def mass_disable_store(event_id: int, admin_id: int, reason: str) -> MassOpResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute("SELECT id FROM stronghold_store_products WHERE event_id = ? AND active = 1", (event_id,)).fetchall()
        connection.execute("UPDATE stronghold_store_products SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE event_id = ?", (event_id,))
        _audit(connection, event_id=event_id, admin_id=admin_id, action="mass_disable_store", entity="stronghold_store_products", entity_id=0, before={"active_count": len(rows)}, after={"active_count": 0}, reason=reason)
        connection.commit()
    return MassOpResult(affected=len(rows), errors=[])


# ---------------------------------------------------------------------------
# Целостность / анти-чит
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LedgerMismatch:
    user_id: int
    currency_code: str
    ledger_sum: int
    wallet_balance: int


async def reconcile_ledger_vs_balance(event_id: int) -> list[LedgerMismatch]:
    """Сверяет `stronghold_currency_ledger` (сумма delta) с фактическим `currency_balances`.

    Несовпадение означает либо баг в коде экономики, либо прямое вмешательство в БД
    в обход сервисного слоя — оба случая требуют внимания администратора. Полезно
    гонять периодически (например, в рамках healthcheck/аналитики) — не запускается
    автоматически, чтобы не создавать нагрузку на каждый запрос.
    """
    with get_connection() as connection:
        ledger_rows = connection.execute(
            """
            SELECT user_id, currency_code, SUM(delta) AS ledger_sum
            FROM stronghold_currency_ledger
            WHERE event_id = ?
            GROUP BY user_id, currency_code
            """,
            (event_id,),
        ).fetchall()

        mismatches: list[LedgerMismatch] = []
        for row in ledger_rows:
            balance_row = connection.execute(
                "SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?",
                (row["user_id"], row["currency_code"]),
            ).fetchone()
            wallet_balance = int(balance_row["amount"]) if balance_row else 0
            ledger_sum = int(row["ledger_sum"])
            # ledger хранит только движения В КОНТЕКСТЕ события; общий баланс мог
            # получать начисления и из других систем бота (например Coins из обычных
            # матчей) — поэтому сверяем только currency-специфичную для события FT
            # (для неё ledger должен быть единственным источником движений), для Coins
            # сверка информативная, а не строгая.
            if row["currency_code"] == "fortress_token" and ledger_sum != wallet_balance:
                mismatches.append(LedgerMismatch(user_id=int(row["user_id"]), currency_code=row["currency_code"], ledger_sum=ledger_sum, wallet_balance=wallet_balance))

    return mismatches


async def mass_compensate(event_id: int, admin_id: int, user_ids: list[int], *, compensation_type: str, amount: int, reason: str) -> MassOpResult:
    from app.services.stronghold_admin import grant_compensation

    affected = 0
    errors: list[str] = []
    batch_request_id = uuid.uuid4().hex
    for target_user_id in user_ids:
        try:
            applied = await grant_compensation(
                admin_id=admin_id,
                target_user_id=target_user_id,
                event_id=event_id,
                compensation_type=compensation_type,
                amount=amount,
                pack_id=None,
                card_id=None,
                reason=reason,
                request_id=f"mass-{batch_request_id}-{target_user_id}",
            )
            if applied:
                affected += 1
        except Exception as error:  # noqa: BLE001 - собираем в отчёт, не прерываем пакет
            errors.append(f"user_id={target_user_id}: {error}")
    return MassOpResult(affected=affected, errors=errors)
