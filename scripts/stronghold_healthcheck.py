"""CLI healthcheck THE STRONGHOLD. Exit code 0 = здоров, 1 = проблема.

Использование:
    python scripts/stronghold_healthcheck.py

Не раскрывает секреты (сам healthcheck это гарантирует, см. app/services/stronghold_health.py).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database.db import init_database
from app.services.stronghold_health import get_health_status


async def main() -> int:
    await init_database()
    result = await get_health_status()

    print(f"THE STRONGHOLD healthcheck: {'OK' if result.ok else 'FAILED'}")
    for name, passed in result.checks.items():
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")
    for key, value in result.details.items():
        print(f"  {key}: {value}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
