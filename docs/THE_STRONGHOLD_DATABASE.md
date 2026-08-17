# THE STRONGHOLD — слой данных

Дополняет [THE_STRONGHOLD_SPEC.md](THE_STRONGHOLD_SPEC.md). Описывает фактическую схему,
миграции и сид, как они реализованы в коде.

## Миграции

Проект не использует Alembic/ORM. Схема — `app/database/schema.py`
(`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`, идемпотентны сами по себе).
Все новые таблицы THE STRONGHOLD добавлены в конец `SCHEMA_QUERIES` — на существующей
production-базе они создаются один раз при следующем запуске `init_database()`
(`main.py` вызывает его при старте), никакие существующие таблицы не пересоздаются и не
изменяются деструктивно. Новая валюта `fortress_token` добавлена записью в
`DEFAULT_CURRENCIES` (schema.py) — заводится через тот же `ON CONFLICT DO UPDATE`
паттерн, что и остальные валюты.

Если в будущем потребуется точечно добавить колонку в уже существующую `stronghold_*`
таблицу — использовать `ensure_column()` в `app/database/db.py:run_migrations()`, как это
сделано для всех остальных таблиц проекта.

## Таблицы (префикс `stronghold_`)

| Таблица | Назначение | Ключевые ограничения |
|---|---|---|
| `stronghold_events` | Конфигурация события, lifecycle-статус, даты | `UNIQUE(slug)` |
| `stronghold_upgrade_steps` | 7 шагов цепочки Хейсканена | `UNIQUE(event_id, step_order)`, `UNIQUE(event_id, from_card_id)` |
| `stronghold_upgrade_transactions` | Журнал апгрейдов, идемпотентность | `UNIQUE(user_id, request_id)` |
| `stronghold_currency_ledger` | История начислений/списаний FT и Coins в контексте события | индекс `(user_id, event_id, created_at)` |
| `stronghold_fortresses` | 15 крепостей | `UNIQUE(event_id, order_index)`, `UNIQUE(code)` |
| `stronghold_fortress_matches` | 6 матчей на крепость | `UNIQUE(fortress_id, order_index)` |
| `stronghold_user_fortress_progress` | Прогресс пользователя по крепости | `UNIQUE(user_id, fortress_id)` |
| `stronghold_user_fortress_match_progress` | Прогресс пользователя по матчу крепости | `UNIQUE(user_id, fortress_match_id)` |
| `stronghold_endless_config` | Параметры масштабирования Endless Siege | `UNIQUE(event_id)` |
| `stronghold_endless_waves` | Журнал волн (append-only) | индекс `(user_id, event_id, created_at)` |
| `stronghold_user_endless_progress` | Текущая/лучшая волна пользователя | `UNIQUE(user_id, event_id)` |
| `stronghold_endless_weekly_ft` | Недельный FT-лимит Endless Siege | `UNIQUE(user_id, event_id, week_key)` |
| `stronghold_leaderboard_entries` | Лидерборд Endless Siege | `UNIQUE(user_id, event_id)` |
| `stronghold_missions` | Определения Daily/Weekly/Seasonal миссий | `UNIQUE(event_id, code)` |
| `stronghold_user_mission_progress` | Прогресс миссии за период | `UNIQUE(user_id, mission_id, period_key)` |
| `stronghold_season_track_levels` | Уровни Season Track | `UNIQUE(event_id, level)` |
| `stronghold_user_season_progress` | Event XP пользователя | `UNIQUE(user_id, event_id)` |
| `stronghold_user_season_claims` | Полученные награды уровней | `UNIQUE(user_id, season_level_id)` |
| `stronghold_store_products` | Товары Event Store | `UNIQUE(event_id, code)` |
| `stronghold_store_purchases` | Журнал покупок, идемпотентность | `UNIQUE(user_id, request_id)` |
| `stronghold_audit_log` | Аудит всех административных и системных действий | — |
| `stronghold_analytics_event` | Событийный лог для аналитики | — |
| `stronghold_compensations` | Ручные компенсации админов | `UNIQUE(admin_id, request_id)` |
| `stronghold_ft_conversions` | Флаг завершённой автоконвертации FT->Coins | `UNIQUE(user_id, event_id)` |

Коллекция и Card Definition **не создают новых таблиц** — используются существующие
`collections`/`cards`/`user_cards` (см. спека, раздел 3). Апгрейд карты реализован как
`UPDATE user_cards SET card_id = ...` — новая строка `user_cards` не создаётся, поэтому
`lineup_slot`/`is_in_lineup`/история трейдов автоматически сохраняются при апгрейде.

## Инварианты, обеспеченные на уровне БД/кода

- Отрицательный баланс FT/Coins невозможен: списание — `UPDATE ... WHERE amount >= ?` +
  проверка `rowcount` (см. `app/services/stronghold_wallet.py:debit`), как в `shop.py`.
  Тест: `tests/test_stronghold_upgrade.py::test_insufficient_*`.
- `UNIQUE(user_id, request_id)` на `stronghold_upgrade_transactions` и
  `stronghold_store_purchases` — защита от двойного списания при повторной отправке.
- `UNIQUE(user_id, mission_id, period_key)` — дневной/недельный сброс без потери истории
  прошлых периодов, без дублей начислений.
- Время — UTC везде (`utc_now()`/`utc_now_text()` в `stronghold_common.py`, SQLite
  `CURRENT_TIMESTAMP`/`datetime('now')` также UTC).
- Мягкое удаление вместо физического: `active`/`status`-флаги на всех таблицах контента
  (`stronghold_fortresses.active`, `stronghold_missions.active`, `stronghold_store_products.active`).

## Сид (`app/services/stronghold_seed.py`)

`seed_stronghold_content(connection)` вызывается из `init_database()` внутри уже открытой
транзакции (после существующих `seed_default_*`). Повторный запуск не создаёт дублей:

- `cards` — поиск по `(player_key, overall, collection_id)` перед вставкой;
- остальные таблицы — `INSERT ... ON CONFLICT(...) DO UPDATE/DO NOTHING` по естественным
  бизнес-ключам (`event_id + code`, `event_id + order_index`, `event_id + step_order`, ...).

Сид программно проверяет (`assert`) итоговые суммы перед записью:

- Upgrade Chain: 375 FT, 4 050 000 Coins;
- Fortress: 220 FT суммарно по 15 крепостям;
- Daily Missions: 4 FT/день (→ 120 за 30 дней);
- Weekly Missions: 20 FT/неделю (→ 80 за 4 недели);
- Season Track: 50 FT.

Проверено тестами `tests/test_stronghold_schema.py` (миграции на пустой БД, повторный
запуск, суммы) и вручную (см. раздел «Проверка» ниже).

## Проверка

```powershell
$env:BOT_TOKEN = "test"
$env:ADMIN_IDS = "1"
$env:DATABASE_PATH = "data/stronghold_check.sqlite3"
python -c "import asyncio; from app.database.db import init_database; asyncio.run(init_database())"
python -c "import asyncio; from app.database.db import init_database; asyncio.run(init_database())"  # повторный запуск — идемпотентность
```

Ожидаемо: 23 карты в коллекции `the_stronghold`, 15 крепостей, 90 матчей крепостей,
7 шагов апгрейда, суммы FT/Coins как выше — без дублей при повторном запуске.
