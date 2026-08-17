"""LiveOps/административные операции THE STRONGHOLD: lifecycle, публикация, компенсации, аудит.

Используется из `app/handlers/admin_stronghold.py`, защищённого существующей ролевой моделью
`app/services/admin_permissions.py` (см. docs/THE_STRONGHOLD_SPEC.md, раздел 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from app.database.db import get_connection
from app.services.rewards import grant_currency, grant_pack
from app.services.stronghold_common import StrongholdError, grace_ends_at_text, utc_now_text
from app.services.stronghold_wallet import credit

EXPECTED_UPGRADE_FT_TOTAL = 375
EXPECTED_UPGRADE_COINS_TOTAL = 4_050_000
EXPECTED_FORTRESS_COUNT = 15
EXPECTED_FORTRESS_MATCHES = 6
EXPECTED_FORTRESS_FT_TOTAL = 220
# Daily/Weekly миссии определены один раз и переиспользуются каждый период (period_key
# меняется автоматически) — поэтому здесь проверяется FT ЗА ОДИН ПЕРИОД, а не за все
# 30 дней/4 недели сразу: 4 FT/день * 30 дней = 120 итого, 20 FT/неделю * 4 недели = 80 итого.
EXPECTED_DAILY_FT_PER_DAY = 4
EXPECTED_WEEKLY_FT_PER_WEEK = 20
EXPECTED_SEASON_FT_TOTAL = 50


@dataclass(frozen=True)
class PublishValidationResult:
    ok: bool
    errors: list[str]


@dataclass(frozen=True)
class AuditLogEntry:
    id: int
    admin_id: int | None
    action: str
    entity: str
    entity_id: int | None
    reason: str | None
    request_id: str | None
    created_at: str


@dataclass(frozen=True)
class AuditLogPage:
    entries: list[AuditLogEntry]
    page: int
    pages_count: int
    total_count: int


def validate_event_config(event_id: int) -> PublishValidationResult:
    errors: list[str] = []
    with get_connection() as connection:
        steps = connection.execute(
            "SELECT ft_cost, coins_cost FROM stronghold_upgrade_steps WHERE event_id = ?", (event_id,)
        ).fetchall()
        ft_total = sum(int(row["ft_cost"]) for row in steps)
        coins_total = sum(int(row["coins_cost"]) for row in steps)
        if len(steps) != 7:
            errors.append(f"Upgrade Chain должен содержать 7 шагов, найдено {len(steps)}.")
        if ft_total != EXPECTED_UPGRADE_FT_TOTAL:
            errors.append(f"Сумма FT в Upgrade Chain должна быть {EXPECTED_UPGRADE_FT_TOTAL}, сейчас {ft_total}.")
        if coins_total != EXPECTED_UPGRADE_COINS_TOTAL:
            errors.append(f"Сумма Coins в Upgrade Chain должна быть {EXPECTED_UPGRADE_COINS_TOTAL}, сейчас {coins_total}.")

        fortresses = connection.execute(
            "SELECT id, first_completion_ft FROM stronghold_fortresses WHERE event_id = ? AND active = 1", (event_id,)
        ).fetchall()
        if len(fortresses) != EXPECTED_FORTRESS_COUNT:
            errors.append(f"Должно быть {EXPECTED_FORTRESS_COUNT} Fortress, найдено {len(fortresses)}.")
        fortress_ft_total = sum(int(row["first_completion_ft"]) for row in fortresses)
        if fortress_ft_total != EXPECTED_FORTRESS_FT_TOTAL:
            errors.append(f"Сумма FT за первое прохождение Fortress должна быть {EXPECTED_FORTRESS_FT_TOTAL}, сейчас {fortress_ft_total}.")

        for fortress in fortresses:
            match_count = connection.execute(
                "SELECT COUNT(*) AS c FROM stronghold_fortress_matches WHERE fortress_id = ? AND active = 1", (fortress["id"],)
            ).fetchone()["c"]
            if match_count != EXPECTED_FORTRESS_MATCHES:
                errors.append(f"Fortress id={fortress['id']} должен иметь {EXPECTED_FORTRESS_MATCHES} матчей, найдено {match_count}.")

        daily_total = connection.execute(
            "SELECT COALESCE(SUM(reward_ft), 0) AS total FROM stronghold_missions WHERE event_id = ? AND type = 'DAILY' AND active = 1",
            (event_id,),
        ).fetchone()["total"]
        weekly_total = connection.execute(
            "SELECT COALESCE(SUM(reward_ft), 0) AS total FROM stronghold_missions WHERE event_id = ? AND type = 'WEEKLY' AND active = 1",
            (event_id,),
        ).fetchone()["total"]
        season_total = connection.execute(
            "SELECT COALESCE(SUM(reward_ft), 0) AS total FROM stronghold_season_track_levels WHERE event_id = ?", (event_id,)
        ).fetchone()["total"]

        if int(daily_total) != EXPECTED_DAILY_FT_PER_DAY:
            errors.append(
                f"Сумма FT Daily Missions за один день должна быть {EXPECTED_DAILY_FT_PER_DAY} "
                f"(даёт 120 за 30 дней), сейчас {daily_total}."
            )
        if int(weekly_total) != EXPECTED_WEEKLY_FT_PER_WEEK:
            errors.append(
                f"Сумма FT Weekly Missions за одну неделю должна быть {EXPECTED_WEEKLY_FT_PER_WEEK} "
                f"(даёт 80 за 4 недели), сейчас {weekly_total}."
            )
        if int(season_total) != EXPECTED_SEASON_FT_TOTAL:
            errors.append(f"Сумма FT Season Track должна быть {EXPECTED_SEASON_FT_TOTAL}, сейчас {season_total}.")

        event_row = connection.execute("SELECT starts_at, ends_at FROM stronghold_events WHERE id = ?", (event_id,)).fetchone()
        if event_row is None or not event_row["starts_at"] or not event_row["ends_at"]:
            errors.append("Не заданы даты starts_at/ends_at события.")

    return PublishValidationResult(ok=not errors, errors=errors)


def schedule_event(event_id: int, starts_at_text: str, ends_at_text: str, *, admin_id: int, reason: str = "schedule") -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT status FROM stronghold_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise StrongholdError("EVENT_NOT_ACTIVE", "Событие не найдено.")
        grace_ends_at = grace_ends_at_text(ends_at_text)
        connection.execute(
            """
            UPDATE stronghold_events
            SET status = 'SCHEDULED', starts_at = ?, ends_at = ?, grace_ends_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (starts_at_text, ends_at_text, grace_ends_at, event_id),
        )
        connection.execute(
            "INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, reason) VALUES (?, ?, 'schedule', 'stronghold_events', ?, ?)",
            (event_id, admin_id, event_id, reason),
        )
        connection.commit()


def force_transition(event_id: int, new_status: str, *, admin_id: int, reason: str) -> None:
    if new_status not in ("ACTIVE", "GRACE_PERIOD", "ARCHIVED", "DRAFT"):
        raise ValueError("invalid status")
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM stronghold_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise StrongholdError("EVENT_NOT_ACTIVE", "Событие не найдено.")

        updates = {"status": new_status}
        if new_status == "ACTIVE" and not row["starts_at"]:
            updates["starts_at"] = utc_now_text()
        if new_status == "GRACE_PERIOD" and not row["ends_at"]:
            now_text = utc_now_text()
            updates["ends_at"] = now_text
            updates["grace_ends_at"] = grace_ends_at_text(now_text)

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        connection.execute(
            f"UPDATE stronghold_events SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*updates.values(), event_id),
        )
        connection.execute(
            "INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, before, after, reason) VALUES (?, ?, 'force_transition', 'stronghold_events', ?, ?, ?, ?)",
            (event_id, admin_id, event_id, row["status"], new_status, reason),
        )
        connection.commit()


async def grant_compensation(
    *,
    admin_id: int,
    target_user_id: int,
    event_id: int,
    compensation_type: str,
    amount: int,
    pack_id: int | None,
    card_id: int | None,
    reason: str,
    request_id: str,
) -> bool:
    """Возвращает True если применена сейчас, False если это был повтор (идемпотентность)."""
    from app.services.stronghold_common import COINS_CURRENCY_CODE, FT_CURRENCY_CODE

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            "SELECT 1 FROM stronghold_compensations WHERE admin_id = ? AND request_id = ?", (admin_id, request_id)
        ).fetchone()
        if existing is not None:
            connection.rollback()
            return False

        if compensation_type == "coins":
            credit(connection, user_id=target_user_id, event_id=event_id, currency_code=COINS_CURRENCY_CODE,
                   amount=amount, reason="admin_compensation", reference_type="compensation")
        elif compensation_type == "fortress_token":
            credit(connection, user_id=target_user_id, event_id=event_id, currency_code=FT_CURRENCY_CODE,
                   amount=amount, reason="admin_compensation", reference_type="compensation")
        elif compensation_type == "pack" and pack_id is not None:
            grant_pack(connection, target_user_id, pack_id, max(amount, 1))
        elif compensation_type == "card" and card_id is not None:
            for _ in range(max(amount, 1)):
                connection.execute(
                    "INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked) VALUES (?, ?, 'stronghold_compensation', 0, 0)",
                    (target_user_id, card_id),
                )
        elif compensation_type == "season_xp":
            connection.execute(
                """
                INSERT INTO stronghold_user_season_progress (user_id, event_id, xp)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, event_id) DO UPDATE SET xp = xp + excluded.xp, updated_at = CURRENT_TIMESTAMP
                """,
                (target_user_id, event_id, amount),
            )
        else:
            raise StrongholdError("INVALID_PRODUCT_CONFIGURATION", "Некорректный тип компенсации.")

        connection.execute(
            """
            INSERT INTO stronghold_compensations (event_id, admin_id, target_user_id, compensation_type, amount, pack_id, card_id, reason, request_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, admin_id, target_user_id, compensation_type, amount, pack_id, card_id, reason, request_id),
        )
        connection.execute(
            """
            INSERT INTO stronghold_audit_log (event_id, admin_id, action, entity, entity_id, reason, request_id)
            VALUES (?, ?, 'compensation', 'users', ?, ?, ?)
            """,
            (event_id, admin_id, target_user_id, reason, request_id),
        )
        connection.commit()
    return True


def list_audit_log(event_id: int, page: int = 1, per_page: int = 20) -> AuditLogPage:
    with get_connection() as connection:
        total_count = int(
            connection.execute("SELECT COUNT(*) AS c FROM stronghold_audit_log WHERE event_id = ?", (event_id,)).fetchone()["c"]
        )
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            """
            SELECT id, admin_id, action, entity, entity_id, reason, request_id, created_at
            FROM stronghold_audit_log
            WHERE event_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (event_id, per_page, offset),
        ).fetchall()

    entries = [
        AuditLogEntry(
            id=int(row["id"]),
            admin_id=row["admin_id"],
            action=row["action"],
            entity=row["entity"],
            entity_id=row["entity_id"],
            reason=row["reason"],
            request_id=row["request_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return AuditLogPage(entries=entries, page=safe_page, pages_count=pages_count, total_count=total_count)
