"""Безопасный DEV/QA seed для ручного тестирования THE STRONGHOLD.

- НЕ запускается автоматически (не вызывается из init_database()/main.py).
- Требует явного флага --confirm, иначе только печатает, что сделал бы.
- Не трогает существующих пользователей: создаёт/обновляет ровно одного тестового
  игрока по фиксированному Telegram ID, идемпотентен (повторный запуск не плодит дублей).
- Выдаёт стартовую Miro Heiskanen 92, немного FT и Coins для ручных проверок Upgrade
  Chain/Fortress/Store.

Использование:
    python scripts/stronghold_demo_seed.py --confirm
    python scripts/stronghold_demo_seed.py --confirm --telegram-id 900000001
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_DEMO_TELEGRAM_ID = 900_000_001


async def run(telegram_id: int, confirm: bool) -> None:
    from aiogram.types import User as TelegramUser

    from app.database.db import get_connection, init_database
    from app.services.stronghold_common import COINS_CURRENCY_CODE, FT_CURRENCY_CODE, get_active_event
    from app.services.stronghold_upgrade import ensure_starter_card
    from app.services.stronghold_wallet import credit
    from app.services.users import register_or_update_player

    if not confirm:
        print("DRY RUN (не применено). Повторите с флагом --confirm, чтобы создать demo-игрока.")
        print(f"  Telegram ID: {telegram_id}")
        print("  Будет выдано: стартовая карта Miro Heiskanen 92, 500 Fortress Token, 5 000 000 Coins.")
        return

    await init_database()

    telegram_user = TelegramUser(id=telegram_id, is_bot=False, first_name="Stronghold Demo")
    profile = await register_or_update_player(telegram_user)

    await ensure_starter_card(profile.id)

    event = await get_active_event()
    if event is None:
        print("⚠️ Событие THE STRONGHOLD не ACTIVE/GRACE_PERIOD — стартовая карта не выдана "
              "(активируйте событие через admin-панель THE STRONGHOLD -> Lifecycle -> ACTIVE).")
    else:
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            credit(connection, user_id=profile.id, event_id=event.id, currency_code=FT_CURRENCY_CODE, amount=500, reason="demo_seed")
            credit(connection, user_id=profile.id, event_id=event.id, currency_code=COINS_CURRENCY_CODE, amount=5_000_000, reason="demo_seed")
            connection.commit()

    print(f"✅ Demo-игрок готов: user_id={profile.id}, telegram_id={telegram_id}, nickname={profile.nickname}")
    print("   Откройте бота под этим Telegram ID (или используйте user_id в admin Support) для проверки THE STRONGHOLD.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-id", type=int, default=DEFAULT_DEMO_TELEGRAM_ID)
    parser.add_argument("--confirm", action="store_true", help="Реально применить (без флага — только dry-run)")
    args = parser.parse_args()
    asyncio.run(run(args.telegram_id, args.confirm))


if __name__ == "__main__":
    main()
