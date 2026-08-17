"""Безопасный DEV/QA seed для ручного тестирования CLAN WAR 2.0.

- НЕ запускается автоматически (не вызывается из init_database()/main.py) — только
  структурный сид (коллекция/карты/паки/режимы) идёт через app/services/war2_seed.py
  на каждом старте, это отдельный скрипт для игровых тестовых данных.
- Требует явного флага --confirm, иначе только печатает, что сделал бы.
- Идемпотентен: создаёт/обновляет ровно двух фиксированных demo-игроков (в разных
  demo-кланах, чтобы можно было проверить подбор реального соперника), наполняет
  'free-cards' достаточным количеством карт для Draft Pool (3G/6D/15F) и Clone War
  (92-99 OVR), запускает активный сезон, если его ещё нет.

Использование:
    python scripts/war2_demo_seed.py --confirm
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEMO_TELEGRAM_ID_A = 900_000_101
DEMO_TELEGRAM_ID_B = 900_000_102
FILLER_PLAYER_KEY_PREFIX = "war2-demo-filler"


async def run(confirm: bool) -> None:
    from aiogram.types import User as TelegramUser

    from app.database.db import get_connection, init_database
    from app.services.users import register_or_update_player

    if not confirm:
        print("DRY RUN (не применено). Повторите с флагом --confirm.")
        print(f"  Будет создано: 2 demo-игрока ({DEMO_TELEGRAM_ID_A}, {DEMO_TELEGRAM_ID_B}) в разных demo-кланах,")
        print("  заполнение 'free-cards' филлер-картами для Draft Pool/Clone War, активный сезон CLAN WAR 2.0.")
        return

    await init_database()

    telegram_user_a = TelegramUser(id=DEMO_TELEGRAM_ID_A, is_bot=False, first_name="War2 Demo A")
    telegram_user_b = TelegramUser(id=DEMO_TELEGRAM_ID_B, is_bot=False, first_name="War2 Demo B")
    profile_a = await register_or_update_player(telegram_user_a)
    profile_b = await register_or_update_player(telegram_user_b)

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        # два demo-клана, чтобы find_war2_opponent() нашёл РЕАЛЬНОГО игрока
        for name, user_id in (("War2 Demo Clan A", profile_a.id), ("War2 Demo Clan B", profile_b.id)):
            clan_row = connection.execute("SELECT id FROM clans WHERE name = ?", (name,)).fetchone()
            if clan_row is None:
                cursor = connection.execute(
                    "INSERT INTO clans (name, created_by_user_id) VALUES (?, ?)", (name, user_id)
                )
                clan_id = int(cursor.lastrowid)
            else:
                clan_id = int(clan_row["id"])
            existing_member = connection.execute(
                "SELECT id FROM clan_members WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing_member is None:
                connection.execute(
                    "INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, 'leader')",
                    (clan_id, user_id),
                )

        # филлер-карты в 'free-cards' (BASE_COLLECTION) — достаточно с запасом для
        # Draft Pool (3G/6D/15F) и Clone War (92-99 OVR по всем позициям).
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        collection_id = int(collection["id"])
        existing_fillers = connection.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE player_key LIKE ?", (f"{FILLER_PLAYER_KEY_PREFIX}%",)
        ).fetchone()["n"]

        created = 0
        if int(existing_fillers) < 60:
            plan = [("G", 70, 10), ("D", 70, 15), ("F", 70, 30)]
            for overall in (92, 94, 96, 98, 99):
                plan.append(("G" if overall == 99 else "F", overall, 4))
            seq = 0
            for position, overall, count in plan:
                for _ in range(count):
                    seq += 1
                    key = f"{FILLER_PLAYER_KEY_PREFIX}-{position.lower()}-{overall}-{seq}"
                    row = connection.execute(
                        "SELECT id FROM cards WHERE player_key = ? AND collection_id = ?", (key, collection_id)
                    ).fetchone()
                    if row is None:
                        connection.execute(
                            """
                            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
                            VALUES (?, ?, ?, ?, 'War2 Demo Team', 'Demo Country', ?, 'Common', 'assets/uploads/test.png', ?, 1)
                            """,
                            (key.replace("-", " ").title(), key, position, overall, collection_id, overall * 100),
                        )
                        created += 1

        # активный сезон, если его ещё нет
        active_season = connection.execute("SELECT id FROM war2_seasons WHERE status = 'active'").fetchone()
        if active_season is None:
            last = connection.execute("SELECT MAX(season_number) AS n FROM war2_seasons").fetchone()
            next_number = int(last["n"] or 0) + 1
            starts_at = datetime.now(timezone.utc)
            ends_at = starts_at + timedelta(days=28)
            connection.execute(
                "INSERT INTO war2_seasons (season_number, status, starts_at, ends_at) VALUES (?, 'active', ?, ?)",
                (next_number, starts_at.strftime("%Y-%m-%d %H:%M:%S"), ends_at.strftime("%Y-%m-%d %H:%M:%S")),
            )

        connection.commit()

    print(f"✅ Demo-игроки готовы: A={profile_a.id} (tg={DEMO_TELEGRAM_ID_A}), B={profile_b.id} (tg={DEMO_TELEGRAM_ID_B})")
    print(f"   Создано филлер-карт в 'free-cards': {created} (пропущено, если уже было >=60).")
    print("   Сезон CLAN WAR 2.0 активен. Откройте бота под tg={} -> Кланы -> CLAN WAR 2.0 -> Найти матч.".format(DEMO_TELEGRAM_ID_A))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Реально применить (без флага — только dry-run)")
    args = parser.parse_args()
    asyncio.run(run(args.confirm))


if __name__ == "__main__":
    main()
