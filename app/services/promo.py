from dataclasses import dataclass
from datetime import datetime

from app.database.db import get_connection
from app.services.rewards import grant_currency, grant_pack


@dataclass(frozen=True)
class PromoReward:
    coins: int
    rubles: int
    bp_points: int
    pack_name: str | None


@dataclass(frozen=True)
class PromoCodeInfo:
    id: int
    code: str
    coins: int
    rubles: int
    bp_points: int
    pack_id: int | None
    pack_name: str | None
    max_activations: int
    per_user_limit: int
    activations_count: int
    expires_at: str | None
    active: bool


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def normalize_code(value: str | None) -> str:
    return "".join((value or "").strip().upper().split())


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def grant_bp_points(connection, user_id: int, amount: int) -> None:
    if amount <= 0:
        return
    connection.execute(
        "UPDATE users SET bp_points = bp_points + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (amount, user_id),
    )


async def redeem_promo(user_id: int, code_text: str) -> tuple[PromoReward | None, str]:
    code = normalize_code(code_text)
    if not code:
        return None, "Введи промокод."

    now = utc_now()

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        promo = connection.execute(
            "SELECT * FROM promo_codes WHERE code = ?",
            (code,),
        ).fetchone()

        if promo is None or not int(promo["active"]):
            connection.rollback()
            return None, "Промокод не найден или отключён."

        expires = parse_dt(promo["expires_at"])
        if expires is not None and expires <= now:
            connection.rollback()
            return None, "Срок действия промокода истёк."

        max_act = int(promo["max_activations"])
        if max_act > 0 and int(promo["activations_count"]) >= max_act:
            connection.rollback()
            return None, "Лимит активаций промокода исчерпан."

        per_user = int(promo["per_user_limit"])
        used_by_user = int(connection.execute(
            "SELECT COUNT(*) AS n FROM promo_code_activations WHERE promo_code_id = ? AND user_id = ?",
            (int(promo["id"]), user_id),
        ).fetchone()["n"])
        if per_user > 0 and used_by_user >= per_user:
            connection.rollback()
            return None, "Ты уже активировал этот промокод."

        coins = int(promo["coins"] or 0)
        rubles = int(promo["rubles"] or 0)
        bp = int(promo["bp_points"] or 0)
        pack_id = promo["pack_id"]

        grant_currency(connection, user_id, "coins", coins)
        grant_currency(connection, user_id, "energy", rubles)  # energy = Рубли
        grant_bp_points(connection, user_id, bp)
        pack_name = None
        if pack_id is not None and grant_pack(connection, user_id, int(pack_id), 1):
            name_row = connection.execute("SELECT name FROM packs WHERE id = ?", (int(pack_id),)).fetchone()
            pack_name = name_row["name"] if name_row else None

        connection.execute(
            "INSERT INTO promo_code_activations (promo_code_id, user_id) VALUES (?, ?)",
            (int(promo["id"]), user_id),
        )
        connection.execute(
            "UPDATE promo_codes SET activations_count = activations_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(promo["id"]),),
        )
        connection.commit()

    return PromoReward(coins=coins, rubles=rubles, bp_points=bp, pack_name=pack_name), "ok"


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

def row_to_promo(row) -> PromoCodeInfo:
    return PromoCodeInfo(
        id=int(row["id"]),
        code=row["code"],
        coins=int(row["coins"] or 0),
        rubles=int(row["rubles"] or 0),
        bp_points=int(row["bp_points"] or 0),
        pack_id=row["pack_id"],
        pack_name=row["pack_name"] if "pack_name" in row.keys() else None,
        max_activations=int(row["max_activations"]),
        per_user_limit=int(row["per_user_limit"]),
        activations_count=int(row["activations_count"]),
        expires_at=row["expires_at"],
        active=bool(row["active"]),
    )


async def list_promos() -> list[PromoCodeInfo]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT pc.*, p.name AS pack_name
            FROM promo_codes pc
            LEFT JOIN packs p ON p.id = pc.pack_id
            ORDER BY pc.created_at DESC
            """
        ).fetchall()
    return [row_to_promo(row) for row in rows]


async def get_promo(promo_id: int) -> PromoCodeInfo | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT pc.*, p.name AS pack_name
            FROM promo_codes pc
            LEFT JOIN packs p ON p.id = pc.pack_id
            WHERE pc.id = ?
            """,
            (promo_id,),
        ).fetchone()
    return row_to_promo(row) if row else None


async def create_promo(code: str, coins: int, rubles: int, max_activations: int, per_user_limit: int) -> tuple[PromoCodeInfo | None, str]:
    clean = normalize_code(code)
    if len(clean) < 3 or len(clean) > 32:
        return None, "Код должен быть от 3 до 32 символов (буквы/цифры)."

    with get_connection() as connection:
        exists = connection.execute("SELECT id FROM promo_codes WHERE code = ?", (clean,)).fetchone()
        if exists is not None:
            return None, "Такой промокод уже существует."
        connection.execute(
            """
            INSERT INTO promo_codes (code, coins, rubles, max_activations, per_user_limit)
            VALUES (?, ?, ?, ?, ?)
            """,
            (clean, max(0, coins), max(0, rubles), max(0, max_activations), max(0, per_user_limit)),
        )
        connection.commit()
        row = connection.execute(
            "SELECT pc.*, NULL AS pack_name FROM promo_codes pc WHERE code = ?",
            (clean,),
        ).fetchone()
    return row_to_promo(row), "ok"


async def update_promo_field(promo_id: int, field: str, value: object) -> tuple[bool, str]:
    allowed = {"coins", "rubles", "bp_points", "max_activations", "per_user_limit", "pack_id", "expires_at"}
    if field not in allowed:
        return False, "Это поле нельзя изменить."

    if field in ("coins", "rubles", "bp_points", "max_activations", "per_user_limit"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False, "Нужно целое число."
        if value < 0 or value > 100000000:
            return False, "Значение вне диапазона."

    if field == "expires_at" and value is not None:
        if parse_dt(str(value)) is None:
            return False, "Формат даты: ГГГГ-ММ-ДД или ГГГГ-ММ-ДД ЧЧ:ММ:СС."

    with get_connection() as connection:
        exists = connection.execute("SELECT id FROM promo_codes WHERE id = ?", (promo_id,)).fetchone()
        if exists is None:
            return False, "Промокод не найден."
        if field == "pack_id" and value is not None:
            pack = connection.execute("SELECT id FROM packs WHERE id = ?", (value,)).fetchone()
            if pack is None:
                return False, "Пак не найден."
        connection.execute(
            f"UPDATE promo_codes SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, promo_id),
        )
        connection.commit()
    return True, "Сохранено."


async def toggle_promo_active(promo_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        row = connection.execute("SELECT active FROM promo_codes WHERE id = ?", (promo_id,)).fetchone()
        if row is None:
            return False, "Промокод не найден."
        new_value = 0 if int(row["active"]) else 1
        connection.execute(
            "UPDATE promo_codes SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_value, promo_id),
        )
        connection.commit()
    return True, "Промокод включён." if new_value else "Промокод отключён."


async def delete_promo(promo_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM promo_codes WHERE id = ?", (promo_id,)).fetchone()
        if row is None:
            return False, "Промокод не найден."
        connection.execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
        connection.commit()
    return True, "Промокод удалён."


async def list_packs_for_picker(limit: int = 30) -> list[tuple[int, str]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name FROM packs WHERE active = 1 ORDER BY name LIMIT ?",
            (limit,),
        ).fetchall()
    return [(int(row["id"]), row["name"]) for row in rows]
