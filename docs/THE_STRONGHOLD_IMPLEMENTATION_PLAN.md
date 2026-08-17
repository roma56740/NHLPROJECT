# THE STRONGHOLD — план реализации

Сопровождающий документ к [THE_STRONGHOLD_SPEC.md](THE_STRONGHOLD_SPEC.md). Описывает
существующий стек, какие модули меняются, какие создаются, и порядок работ.

## Существующий стек (факт, по итогам аудита)

- Python 3, **aiogram 3.28.2** (long polling), без веб-фреймворка и без REST API.
- БД: **raw `sqlite3`** (stdlib), WAL, `BEGIN IMMEDIATE` для атомарных списаний. Нет ORM,
  нет Alembic. Схема — `app/database/schema.py` (`CREATE TABLE IF NOT EXISTS` +
  `CREATE INDEX IF NOT EXISTS`), миграции — `ensure_column()` в `app/database/db.py`.
- Слои: `app/services/*` (бизнес-логика, прямая работа с sqlite3), `app/handlers/*`
  (aiogram роутеры), `app/keyboards/*` (inline/reply клавиатуры), `app/texts/*`
  (текстовые константы), `app/states/*` (aiogram FSM `StatesGroup`).
- Admin-панель: не отдельное приложение, а Telegram-хендлеры `app/handlers/admin_*.py` с
  ролевой моделью `app/services/admin_permissions.py` (`bot_admins.role` →
  `ROLE_PERMISSIONS`).
- Фоновые задачи: `asyncio.create_task(...)` в `main.py`, паттерн
  `while True: try: ... except Exception: log; await asyncio.sleep(N)`.
- Деплой: Railway, `Procfile` → `railway_boot.py` → `main.py`, один процесс/worker,
  персистентный volume под `data/` и `assets/uploads`.
- Тесты: отсутствуют полностью — вводятся с нуля.

## Модули, которые будут изменены

| Файл | Изменение |
|---|---|
| `app/database/schema.py` | Добавляются `CREATE TABLE IF NOT EXISTS` для новых `stronghold_*` таблиц + запись `fortress_token` в `DEFAULT_CURRENCIES`. |
| `app/database/db.py` | Новые `ensure_column(...)` вызовы (на будущее развитие полей) + вызов `seed_stronghold_content()` из `init_database()`. |
| `app/services/matches.py` | Пост-хук после `save_match_result`: вызов `stronghold_fortress.apply_match_result(...)` / `stronghold_endless.apply_wave_result(...)`, через существующий пост-хук результата матча. Никакой новый движок симуляции не создаётся — используется существующий `build_simulation`/`play_quick_match`. |
| `app/services/lineup.py` | Точечное расширение: функция проверки "минимум 1 карта коллекции THE STRONGHOLD в составе" как отдельная функция `lineup_has_collection_card(user_id, collection_code)`, не меняющая существующее поведение обычных матчей. |
| `app/services/admin_permissions.py` | Новая permission-константа `PERMISSION_STRONGHOLD_MANAGE`, `PERMISSION_STRONGHOLD_SUPPORT`, назначение ролям `owner/senior_admin/economy_admin/content_admin`. |
| `app/handlers/menu.py`, `app/keyboards/menu.py` | Добавление пункта меню «🏰 THE STRONGHOLD» в главное меню пользователя (и admin-меню — пункт «🏰 Stronghold»). |
| `main.py` | Регистрация новых фоновых задач: `stronghold_lifecycle_loop`, `stronghold_conversion_loop`, `stronghold_reset_loop` (daily/weekly missions + endless weekly limit). |
| `README.md` | Раздел про THE STRONGHOLD (команды запуска/сид/тесты). |

## Новые сущности (таблицы, префикс `stronghold_`)

Полные DDL — в [THE_STRONGHOLD_DATABASE.md](THE_STRONGHOLD_DATABASE.md) (создаётся на
этапе данных). Список сущностей:

1. `stronghold_events` — конфигурация события(й), lifecycle-статус, даты, флаги (`store_available_in_grace` и т.п.), `config_version`.
2. `stronghold_upgrade_steps` — 7 шагов цепочки Хейсканена (`from_card_id`, `to_card_id`, `ft_cost`, `coins_cost`, `step_order`).
3. `stronghold_upgrade_transactions` — журнал апгрейдов, `UNIQUE(user_id, request_id)`, статус `pending/success/failed`.
4. `stronghold_currency_ledger` — движения FT/Coins в контексте события (`reason` enum, `delta`, `balance_after`).
5. `stronghold_fortresses` — 15 записей, `order_index`, конфигурация звёзд/наград/boss.
6. `stronghold_fortress_matches` — 6 на Fortress, `star_rules` JSON, `opponent_ovr`.
7. `stronghold_user_fortress_progress` — статус Fortress на пользователя.
8. `stronghold_user_fortress_match_progress` — статус матча на пользователя (+ звёзды, `match_id` FK на `matches`).
9. `stronghold_endless_config` — параметры масштабирования сложности (singleton-строка или версионируемая).
10. `stronghold_endless_waves` — журнал волн пользователя.
11. `stronghold_endless_weekly_ft` — `UNIQUE(user_id, week_key)`, накопленный FT за неделю.
12. `stronghold_leaderboard_entries` — материализованное лучшее достижение на пользователя (`UNIQUE(user_id)`, обновляется при новом рекорде).
13. `stronghold_missions` — определения миссий (`type`, `condition_type`, `target_value`, `reward_ft`, `reward_coins`, `period_key_template`).
14. `stronghold_user_mission_progress` — `UNIQUE(user_id, mission_id, period_key)`.
15. `stronghold_season_track_levels` — уровни трека, XP-пороги, награды.
16. `stronghold_user_season_progress` — XP пользователя + `UNIQUE` claimed-уровни (отдельная таблица `stronghold_user_season_claims`).
17. `stronghold_store_products` — товары (категория, цена, валюта, лимиты, даты, `contents` JSON).
18. `stronghold_store_purchases` — `UNIQUE(user_id, request_id)`, журнал покупок.
19. `stronghold_audit_log` — `admin_id, action, entity, entity_id, before, after, reason, request_id, created_at`.
20. `stronghold_analytics_event` — событийный лог для аналитики (`event_code`, `user_id`, `payload` JSON, `created_at`).
21. `stronghold_compensations` — ручные компенсации (`admin_id`, `target_user_id`, `type`, `amount`, `reason`, `request_id`).
22. `stronghold_ft_conversions` — `UNIQUE(user_id)` per событие, флаг завершённой автоконвертации.

Card Definition (23 шт.) и коллекция создаются через **существующие** таблицы `cards`/
`collections` — новая таблица не нужна (см. спека, раздел 3). `user_cards` тоже переиспользуется
без изменений схемы — Upgrade это `UPDATE card_id`, не новая строка.

## API (внутренний слой сервисов, эквивалент "endpoint")

Вместо REST-путей — публичные async-функции в `app/services/stronghold_*.py`, каждая с
чёткой сигнатурой, возвращающая dataclass или бросающая `StrongholdError`:

- `stronghold_event.py`: `get_active_event()`, `get_event_state(event_id)`, lifecycle-переходы.
- `stronghold_wallet.py`: `get_wallet(user_id, event_id)`, `get_currency_history(user_id, event_id, page)`.
- `stronghold_upgrade.py`: `preview_upgrade(user_id, user_card_id)`, `confirm_upgrade(user_id, user_card_id, request_id)`.
- `stronghold_fortress.py`: `list_fortresses(user_id)`, `get_fortress(user_id, fortress_id)`, `start_match(user_id, match_id)`, `submit_match_result(...)` (вызывается из пост-хука `matches.py`, не напрямую пользователем).
- `stronghold_endless.py`: `get_status(user_id)`, `start_wave(user_id)`, `resolve_wave(...)`, `get_leaderboard(page)`.
- `stronghold_missions.py`: `list_missions(user_id, type)`, `claim_mission(user_id, mission_id)`.
- `stronghold_season_track.py`: `get_track(user_id)`, `claim_level(user_id, level)`.
- `stronghold_store.py`: `list_products(user_id, category)`, `purchase(user_id, product_id, request_id)`.
- `stronghold_admin.py`: lifecycle-управление, editors, compensation, audit-запросы.

## Frontend-экраны → Telegram screens

`app/handlers/stronghold.py` (пользовательский роутер) реализует главное меню и экраны:
Overview, Fortress Map, Fortress Details/Match, Endless Siege + Leaderboard, Upgrade Chain,
Missions, Season Track, Store + Product Details, Wallet History. Навигация — inline-кнопки
с `callback_data = "stg:<screen>:<id>:<page>"`, редактирование одного сообщения
(`edit_or_send`, как в `admin_panel.py`) вместо спама новых сообщений.

## Административные экраны → Telegram admin screens

`app/handlers/admin_stronghold.py`: Dashboard, Lifecycle, Collection/Upgrade editor,
Fortress editor, Endless editor, Missions editor, Season Track editor, Store editor,
User Support (поиск по `user_id`/`nickname`), Compensation, Audit Log, Analytics.
FSM-визард по образцу `EventAdminStates` (`app/states/events.py`).

## Тестовая стратегия

Вводится `pytest` + `pytest-asyncio`. `tests/conftest.py` подменяет `DATABASE_PATH` на
временный файл на каждый тест (через `tmp_path` + monkeypatch `config.settings`), вызывает
`init_database()` — таким образом каждый тест получает чистую, но полностью реальную схему
+ сиды. Слои тестов:

- `tests/test_stronghold_schema.py` — миграции на пустой БД и поверх "старой" БД без новых таблиц.
- `tests/test_stronghold_seed.py` — повторный запуск сида не создаёт дублей, суммы FT/Coins сходятся.
- `tests/test_stronghold_upgrade.py` — полная цепочка 92→99, недостаток средств, повтор `request_id`, блокировки (lineup/lock).
- `tests/test_stronghold_fortress.py` — прохождение Fortress, звёзды, повторное прохождение, unlock следующей.
- `tests/test_stronghold_endless.py` — недельный лимit FT, продолжение волн после лимита.
- `tests/test_stronghold_missions.py` — daily reset, claim, двойной claim.
- `tests/test_stronghold_store.py` — покупка, лимит, недостаток валюты, повтор `request_id`.
- `tests/test_stronghold_concurrency.py` — параллельные confirm/claim/purchase через `asyncio.gather`, проверка что применяется только один.

## Риски совместимости

- SQLite не имеет row-level locking → все Stronghold-транзакции используют `BEGIN IMMEDIATE`
  (эксклюзивный лок на файл БД). Для одного бот-процесса это безопасно, но long-running
  транзакции надо держать короткими, чтобы не блокировать остальной бот (пакеты/паки/трейды).
- Переиспользование `user_cards.card_id` для апгрейда меняет смысл поля "истории": если
  где-то в проекте есть код, ожидающий что `card_id` неизменен для конкретного `user_cards.id`
  (например, кэш рендера по `user_card_id`) — нужно инвалидировать кэш при апгрейде
  (`app/services/renders.py` кэширует по `card_id`+`user_id`, не по `user_cards.id` — риска нет,
  но кэш апгрейднутой карты нужно явно не переиспользовать старый).
- `matches.py:save_match_result` уже вызывает несколько пост-хуков — добавление ещё двух
  (`fortress`, `endless`) увеличивает время внутри уже существующей транзакции; хуки должны
  быть best-effort (try/except + лог), чтобы сбой в Stronghold не ронял обычный матч.
- `ADMIN_IDS`/роли: новая permission должна быть добавлена в `ROLE_PERMISSIONS` без изменения
  поведения существующих ролей на остальные permission.

## Порядок реализации

1. Данные: схема + миграции + сид (эта работа + `THE_STRONGHOLD_DATABASE.md`).
2. Экономика: wallet/ledger + Upgrade Chain (атомарность, идемпотентность).
3. Fortress + Endless Siege, интеграция с `matches.py`.
4. Missions + Season Track + Store.
5. Пользовательские Telegram-экраны.
6. Admin-экраны + LiveOps.
7. Тесты (пишутся параллельно с каждым сервисом, не откладываются в конец).
8. Фоновые задачи (lifecycle, conversion, resets) + регистрация в `main.py`.
9. Финальная проверка: миграции на реальной БД, сид, тесты, README/отчёты.

Каждый этап оставляет проект в рабочем состоянии (`python -c "import main"` не падает,
существующие функции не сломаны) — это проверяется после каждого шага, не только в конце.
