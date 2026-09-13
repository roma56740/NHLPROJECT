from __future__ import annotations

from datetime import datetime
import json
from zoneinfo import ZoneInfo

from app.database.db import get_connection

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
EVENT_CODE = "gift-week-r24"
STARTER_PLAYER_KEY = "daxon rudolph"
STARTER_OVR = 97
TOTAL_DAYS = 7

# Deliberately modest rewards: the event should feel generous without injecting
# enough liquid currency to distort the box/trade economy.
GIFT_WEEK_REWARDS: dict[int, tuple[dict[str, object], ...]] = {
    1: ({"type": "currency", "code": "coins", "amount": 10_000, "label": "10 000 Coins"},),
    2: ({"type": "box", "code": "ahl_box", "amount": 1, "label": "AHL Box ×1"},),
    3: ({"type": "currency", "code": "rank_point", "amount": 2, "label": "2 Rank Coins"},),
    4: ({"type": "currency", "code": "coins", "amount": 15_000, "label": "15 000 Coins"},),
    5: ({"type": "item", "code": "fireside_collectible", "amount": 1, "label": "Fireside Collectible ×1"},),
    6: ({"type": "box", "code": "common_box", "amount": 1, "label": "Common Box ×1"},),
    7: (
        {"type": "currency", "code": "coins", "amount": 25_000, "label": "25 000 Coins"},
        {"type": "currency", "code": "rank_point", "amount": 3, "label": "3 Rank Coins"},
    ),
}


def _today_moscow() -> str:
    return datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")


def _user_id(connection, telegram_id: int) -> int | None:
    row = connection.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    return int(row[0]) if row else None


def _event_row(connection):
    return connection.execute(
        "SELECT code,title,starts_at,ends_at FROM gift_week_events WHERE code = ?",
        (EVENT_CODE,),
    ).fetchone()


def _event_active(connection) -> bool:
    row = _event_row(connection)
    if row is None:
        return False
    active = connection.execute(
        "SELECT CASE WHEN datetime('now') >= datetime(?) AND datetime('now') < datetime(?) THEN 1 ELSE 0 END",
        (row["starts_at"], row["ends_at"]),
    ).fetchone()[0]
    return bool(active)


def _starter_card_id(connection) -> int | None:
    row = connection.execute(
        """
        SELECT c.id
        FROM cards c
        JOIN collections col ON col.id = c.collection_id
        WHERE col.code='gift-week-2026' AND lower(c.player_key)=? AND c.overall=?
        ORDER BY c.id DESC LIMIT 1
        """,
        (STARTER_PLAYER_KEY, STARTER_OVR),
    ).fetchone()
    return int(row[0]) if row else None


def _ensure_user_row(connection, user_id: int) -> None:
    connection.execute(
        """
        INSERT INTO gift_week_users(user_id,event_code,starter_granted,claims_count,last_claim_date)
        VALUES(?,?,0,0,NULL)
        ON CONFLICT(user_id,event_code) DO NOTHING
        """,
        (user_id, EVENT_CODE),
    )


def _grant_starter_if_needed(connection, user_id: int) -> bool:
    _ensure_user_row(connection, user_id)
    row = connection.execute(
        "SELECT starter_granted FROM gift_week_users WHERE user_id=? AND event_code=?",
        (user_id, EVENT_CODE),
    ).fetchone()
    if row is None or int(row[0] or 0):
        return False
    card_id = _starter_card_id(connection)
    if card_id is None:
        return False
    connection.execute(
        "INSERT INTO user_cards(user_id,card_id,obtained_from,is_in_lineup,trade_locked) VALUES(?,?,?,0,0)",
        (user_id, card_id, EVENT_CODE),
    )
    connection.execute(
        "UPDATE gift_week_users SET starter_granted=1,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND event_code=?",
        (user_id, EVENT_CODE),
    )
    return True


def _grant_currency(connection, user_id: int, code: str, amount: int) -> None:
    if amount <= 0:
        return
    connection.execute(
        """
        INSERT INTO currency_balances(user_id,currency_code,amount)
        VALUES(?,?,?)
        ON CONFLICT(user_id,currency_code) DO UPDATE SET
            amount=amount+excluded.amount,updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, code, amount),
    )


def _grant_item(connection, user_id: int, code: str, amount: int) -> None:
    if amount <= 0:
        return
    row = connection.execute("SELECT id FROM inventory_items WHERE code=? AND active=1", (code,)).fetchone()
    if row is None:
        raise RuntimeError(f"Gift Week inventory item is missing: {code}")
    connection.execute(
        """
        INSERT INTO user_items(user_id,item_id,quantity)
        VALUES(?,?,?)
        ON CONFLICT(user_id,item_id) DO UPDATE SET
            quantity=quantity+excluded.quantity,updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, int(row[0]), amount),
    )


def _grant_box(connection, user_id: int, code: str, amount: int) -> None:
    if amount <= 0:
        return
    row = connection.execute("SELECT id FROM boxes WHERE code=? AND active=1", (code,)).fetchone()
    if row is None:
        raise RuntimeError(f"Gift Week box is missing: {code}")
    connection.execute(
        """
        INSERT INTO user_boxes(user_id,box_id,quantity)
        VALUES(?,?,?)
        ON CONFLICT(user_id,box_id) DO UPDATE SET
            quantity=quantity+excluded.quantity,updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, int(row[0]), amount),
    )


def _grant_reward(connection, user_id: int, reward: dict[str, object]) -> None:
    reward_type = str(reward["type"])
    code = str(reward["code"])
    amount = int(reward["amount"])
    if reward_type == "currency":
        _grant_currency(connection, user_id, code, amount)
    elif reward_type == "item":
        _grant_item(connection, user_id, code, amount)
    elif reward_type == "box":
        _grant_box(connection, user_id, code, amount)
    else:
        raise RuntimeError(f"Unsupported Gift Week reward type: {reward_type}")


def _serialize_status(connection, user_id: int, *, starter_just_granted: bool = False) -> dict[str, object]:
    event = _event_row(connection)
    if event is None:
        return {"active": False, "code": EVENT_CODE, "days": []}

    _ensure_user_row(connection, user_id)
    state = connection.execute(
        "SELECT starter_granted,claims_count,last_claim_date FROM gift_week_users WHERE user_id=? AND event_code=?",
        (user_id, EVENT_CODE),
    ).fetchone()
    claims_count = int(state["claims_count"] or 0)
    last_claim_date = state["last_claim_date"]
    next_day = min(TOTAL_DAYS, claims_count + 1)
    active = _event_active(connection)
    can_claim = bool(active and claims_count < TOTAL_DAYS and last_claim_date != _today_moscow())

    days = []
    for day in range(1, TOTAL_DAYS + 1):
        days.append(
            {
                "day": day,
                "claimed": day <= claims_count,
                "current": day == next_day and claims_count < TOTAL_DAYS,
                "rewards": [dict(item) for item in GIFT_WEEK_REWARDS[day]],
            }
        )

    return {
        "active": active,
        "code": str(event["code"]),
        "title": str(event["title"]),
        "starts_at": str(event["starts_at"]),
        "ends_at": str(event["ends_at"]),
        "starter": {
            "player": "Daxon Rudolph",
            "overall": STARTER_OVR,
            "position": "D",
            "image_path": "assets/release/gift_week/daxon_rudolph_97.png",
            "granted": bool(state["starter_granted"]),
            "just_granted": bool(starter_just_granted),
        },
        "claims_count": claims_count,
        "total_days": TOTAL_DAYS,
        "next_day": next_day if claims_count < TOTAL_DAYS else None,
        "can_claim": can_claim,
        "already_claimed_today": last_claim_date == _today_moscow(),
        "days": days,
    }


def get_status(telegram_id: int) -> dict[str, object]:
    with get_connection() as connection:
        user_id = _user_id(connection, telegram_id)
        if user_id is None:
            return {"active": False, "code": EVENT_CODE, "days": []}
        starter_just_granted = False
        if _event_active(connection):
            connection.execute("BEGIN IMMEDIATE")
            starter_just_granted = _grant_starter_if_needed(connection, user_id)
            connection.commit()
        return _serialize_status(connection, user_id, starter_just_granted=starter_just_granted)


def claim(telegram_id: int) -> tuple[bool, str, dict[str, object]]:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user_id = _user_id(connection, telegram_id)
        if user_id is None:
            connection.rollback()
            return False, "Профиль не найден.", {"active": False, "days": []}
        if not _event_active(connection):
            connection.rollback()
            return False, "Неделя подарков уже завершена.", _serialize_status(connection, user_id)

        _grant_starter_if_needed(connection, user_id)
        state = connection.execute(
            "SELECT claims_count,last_claim_date FROM gift_week_users WHERE user_id=? AND event_code=?",
            (user_id, EVENT_CODE),
        ).fetchone()
        claims_count = int(state["claims_count"] or 0)
        if claims_count >= TOTAL_DAYS:
            connection.rollback()
            return False, "Все подарки уже получены.", _serialize_status(connection, user_id)
        today = _today_moscow()
        if state["last_claim_date"] == today:
            connection.rollback()
            return False, "Сегодняшний подарок уже получен.", _serialize_status(connection, user_id)

        day = claims_count + 1
        rewards = GIFT_WEEK_REWARDS[day]
        try:
            connection.execute(
                "INSERT INTO gift_week_claims(user_id,event_code,day,rewards_json) VALUES(?,?,?,?)",
                (user_id, EVENT_CODE, day, json.dumps(rewards, ensure_ascii=False)),
            )
        except Exception:
            connection.rollback()
            raise
        for reward in rewards:
            _grant_reward(connection, user_id, reward)
        connection.execute(
            """
            UPDATE gift_week_users
            SET claims_count=?,last_claim_date=?,updated_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND event_code=?
            """,
            (day, today, user_id, EVENT_CODE),
        )
        connection.commit()
        labels = " + ".join(str(item["label"]) for item in rewards)
        return True, f"Подарок дня {day}: {labels}", _serialize_status(connection, user_id)
