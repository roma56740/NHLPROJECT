"""Healthcheck THE STRONGHOLD: БД, конфигурация события, фоновые задачи.

Не раскрывает секреты (токены/пути БД не включаются в вывод), пригоден и для
`scripts/stronghold_healthcheck.py`, и для отображения в admin Dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.database.db import get_connection
from app.services.stronghold_common import STRONGHOLD_SLUG, utc_now


@dataclass(frozen=True)
class HealthCheckResult:
    ok: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)


async def get_health_status() -> HealthCheckResult:
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database_connection"] = True
    except Exception as error:  # noqa: BLE001 - healthcheck must never raise
        checks["database_connection"] = False
        details["database_connection"] = str(error)
        return HealthCheckResult(ok=False, checks=checks, details=details)

    with get_connection() as connection:
        event_row = connection.execute(
            "SELECT id, status, config_version FROM stronghold_events WHERE slug = ?", (STRONGHOLD_SLUG,)
        ).fetchone()
        checks["event_seeded"] = event_row is not None
        if event_row is not None:
            details["event_status"] = str(event_row["status"])
            details["config_version"] = str(event_row["config_version"])

            card_count = connection.execute(
                "SELECT COUNT(*) AS c FROM cards WHERE collection_id = (SELECT id FROM collections WHERE code = 'the_stronghold')"
            ).fetchone()["c"]
            checks["collection_complete"] = int(card_count) == 23

            step_row = connection.execute(
                "SELECT COUNT(*) AS c, SUM(ft_cost) AS ft, SUM(coins_cost) AS coins FROM stronghold_upgrade_steps WHERE event_id = ?",
                (event_row["id"],),
            ).fetchone()
            checks["upgrade_chain_complete"] = int(step_row["c"] or 0) == 7 and int(step_row["ft"] or 0) == 375 and int(step_row["coins"] or 0) == 4_050_000

            fortress_count = connection.execute(
                "SELECT COUNT(*) AS c FROM stronghold_fortresses WHERE event_id = ?", (event_row["id"],)
            ).fetchone()["c"]
            checks["fortress_count_complete"] = int(fortress_count) == 15

    if event_row is not None:
        from app.services.stronghold_admin_content import reconcile_ledger_vs_balance

        mismatches = await reconcile_ledger_vs_balance(int(event_row["id"]))
        checks["ledger_reconciled"] = len(mismatches) == 0
        if mismatches:
            details["ledger_mismatches"] = str(len(mismatches))

    checks["clock_ok"] = True
    details["server_time_utc"] = utc_now().isoformat()

    ok = all(checks.values())
    return HealthCheckResult(ok=ok, checks=checks, details=details)
