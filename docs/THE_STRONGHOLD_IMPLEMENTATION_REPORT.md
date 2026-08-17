# THE STRONGHOLD — отчёт о реализации

## Что реализовано

Полный вертикальный срез события THE STRONGHOLD внутри существующего Telegram-бота
(aiogram 3 + raw SQLite), без параллельной архитектуры:

- **Данные**: 24 новые таблицы (`stronghold_*`), новая валюта `fortress_token`,
  коллекция + 23 Card Definition в существующих `collections`/`cards`. Все миграции
  аддитивны, существующие таблицы не менялись деструктивно.
- **Экономика**: серверный wallet/ledger поверх существующей `currency_balances`,
  атомарный и идемпотентный Upgrade Chain Miro Heiskanen 92→99 (7 шагов, 375 FT +
  4 050 000 Coins), с проверками владения, блокировок, зарплатного потолка и Grace Period.
- **Fortress**: 15 крепостей × 6 матчей, последовательная разблокировка, звёзды,
  220 FT за первое полное прохождение (не повторяется), интеграция с существующим
  движком матчей (`matches.build_simulation`/`save_match_result` через новую обёртку
  `matches.play_stronghold_match`).
- **Endless Siege**: бесконечные волны после Fortress 15, конфигурируемая сложность,
  недельный лимит 20 FT (серверная ISO-неделя), лидерборд.
- **Missions**: Daily/Weekly/Seasonal, прогресс только от серверных пост-хуков,
  4 FT/день (→120 за 30 дней), 20 FT/неделю (→80 за 4 недели).
- **Season Track**: Event XP → 10 уровней → 50 FT суммарно + Coins.
- **Event Store**: Featured/Cards/Resources/Bundles, атомарная покупка с идемпотентностью
  и лимитами.
- **LiveOps/Admin**: Dashboard, Lifecycle-переходы, валидация публикации, Healthcheck,
  редакторы Upgrade Chain, Card Definition (зарплата/toggle), Fortress (награды, toggle,
  **создание крепости с авто-генерацией 6 матчей**, **добавление/toggle отдельных
  матчей**, OVR соперника), Missions (создание + правка + toggle), Season Track (правка),
  Store (**создание Bundle с произвольным числом наград** — несколько
  currency/card-предметов — + правка цены/лимита + toggle), аналитика (funnel по
  крепостям, FT earned/spent, claims/purchases), поиск пользователя, компенсации
  (одиночные и массовые), массовое отключение магазина, аудит-лог — под существующей
  ролевой моделью (`PERMISSION_STRONGHOLD`).
- **Безопасность/анти-чит**: IDOR-проверки (владение картой/прогрессом), сервер как
  единственный источник цены/награды, сверка `stronghold_currency_ledger` ↔
  `currency_balances` (`reconcile_ledger_vs_balance`, подключена к healthcheck),
  параметризованные запросы везде, клампинг пагинации.
- **Observability**: структурированное логирование критичных операций (Upgrade, Fortress,
  Endless, Store) с `action`/`user_id`/`result`/`duration_ms`/`error_code`
  (`stronghold_common.log_stronghold_operation`).
- **Фоновые задачи**: `stronghold_lifecycle_loop` (ACTIVE→GRACE_PERIOD→ARCHIVED по датам +
  автоконвертация FT→Coins после архивации), зарегистрирована в `main.py` по тому же
  паттерну, что и остальные `*_loop`.
- **Служебные скрипты**: healthcheck (`scripts/stronghold_healthcheck.py`), сквозной
  smoke-test (`scripts/stronghold_smoke_test.py`), безопасный dev-only demo-seed
  (`scripts/stronghold_demo_seed.py`, dry-run по умолчанию).
- **Frontend-структура**: пользовательский UI разделён на handlers/texts/keyboards
  (`app/handlers/stronghold.py` + `app/texts/stronghold.py` + `app/keyboards/stronghold.py`),
  как принято в проекте для остальных фич.
- **Тесты**: 76 тестов на реальной SQLite-БД (без моков), включая прямые smoke-тесты
  экранных text/keyboard-builders (единственный слой, реально исполняющий код
  `app/handlers/stronghold.py` — поймал и позволил исправить реальный `NameError` в
  одной из веток экрана до релиза, см. QA-отчёт). pytest + pytest-asyncio впервые
  введены в проект.
- **Внутренний API-контракт**: полный реестр публичных сервисных функций (аналог
  REST/OpenAPI для архитектуры без HTTP-слоя) — `THE_STRONGHOLD_API_REFERENCE.md`.

Документы: [SPEC](THE_STRONGHOLD_SPEC.md) ·
[IMPLEMENTATION_PLAN](THE_STRONGHOLD_IMPLEMENTATION_PLAN.md) ·
[DATABASE](THE_STRONGHOLD_DATABASE.md) · [API_REFERENCE](THE_STRONGHOLD_API_REFERENCE.md) ·
[QA_REPORT](THE_STRONGHOLD_QA_REPORT.md) ·
[RELEASE_CHECKLIST](THE_STRONGHOLD_RELEASE_CHECKLIST.md).

## Изменённые файлы

| Файл | Изменение |
|---|---|
| `app/database/schema.py` | +24 таблицы `stronghold_*`, +валюта `fortress_token` |
| `app/database/db.py` | Вызов `seed_stronghold_content()` из `init_database()` |
| `app/services/matches.py` | +`play_stronghold_match()` (обёртка над существующим движком) |
| `app/services/lineup.py` | +`lineup_has_collection_card()` |
| `app/services/salary.py` | +`STRONGHOLD_SALARY_CAP = 45000` |
| `app/services/admin_permissions.py` | +`PERMISSION_STRONGHOLD` во всех соответствующих реестрах |
| `app/keyboards/reply.py` | +кнопка «🏰 THE STRONGHOLD» в user- и admin-клавиатурах |
| `app/handlers/__init__.py` | Регистрация `stronghold.router` и `admin_stronghold.router` |
| `main.py` | Регистрация `stronghold_lifecycle_loop` |
| `README.md` | Раздел THE STRONGHOLD (запуск, тесты, скрипты) |

## Новые файлы

**Сервисы** (`app/services/`): `stronghold_common.py`, `stronghold_wallet.py`,
`stronghold_upgrade.py`, `stronghold_fortress.py`, `stronghold_endless.py`,
`stronghold_missions.py`, `stronghold_season_track.py`, `stronghold_store.py`,
`stronghold_admin.py`, `stronghold_admin_content.py`, `stronghold_conversion.py`,
`stronghold_lifecycle.py`, `stronghold_health.py`, `stronghold_seed.py`.

**Хендлеры**: `app/handlers/stronghold.py` (пользователь), `app/handlers/admin_stronghold.py` (админ).

**Тексты**: `app/texts/stronghold.py`.

**Клавиатуры**: `app/keyboards/stronghold.py`.

**Скрипты**: `scripts/stronghold_healthcheck.py`, `scripts/stronghold_smoke_test.py`,
`scripts/stronghold_demo_seed.py`.

**Тесты** (`tests/`): `conftest.py`, `test_stronghold_schema.py`, `test_stronghold_upgrade.py`,
`test_stronghold_fortress.py`, `test_stronghold_endless.py`, `test_stronghold_missions.py`,
`test_stronghold_season_track.py`, `test_stronghold_store.py`, `test_stronghold_conversion.py`,
`test_stronghold_admin_content.py`, `test_stronghold_health.py`, `test_stronghold_security.py`,
`test_stronghold_handlers_smoke.py`, `test_regression_existing_systems.py`.

**Документация** (`docs/`): `THE_STRONGHOLD_SPEC.md`, `THE_STRONGHOLD_IMPLEMENTATION_PLAN.md`,
`THE_STRONGHOLD_DATABASE.md`, `THE_STRONGHOLD_API_REFERENCE.md`,
`THE_STRONGHOLD_QA_REPORT.md`, `THE_STRONGHOLD_RELEASE_CHECKLIST.md`, этот файл.

**Конфигурация**: `pytest.ini`, `requirements-dev.txt`.

## Результаты проверок

```
python -m py_compile <весь app/ + main.py + config.py + railway_boot.py + scripts/>  → без ошибок
python -c "import main"                                                              → без ошибок
python -m pytest tests/ -q                                                           → 76 passed
python scripts/stronghold_smoke_test.py                                              → PASSED
python scripts/stronghold_healthcheck.py                                             → OK (exit 0)
```

## Команды

**Локальный запуск** (сид THE STRONGHOLD выполняется автоматически):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # заполнить BOT_TOKEN, ADMIN_IDS
python main.py
```

**Тесты**:

```powershell
pip install -r requirements-dev.txt
pytest
```

**Служебные скрипты**:

```powershell
python scripts/stronghold_healthcheck.py
python scripts/stronghold_smoke_test.py
python scripts/stronghold_demo_seed.py --confirm
```

**Деплой**: без изменений (Railway, `railway_boot.py` → `main.py`, тот же `railway.json`).
Миграции и сид THE STRONGHOLD выполняются автоматически при старте процесса. Чек-лист
перед активацией на проде — [THE_STRONGHOLD_RELEASE_CHECKLIST.md](THE_STRONGHOLD_RELEASE_CHECKLIST.md).

## Известные ограничения

Полный список с обоснованием — [THE_STRONGHOLD_QA_REPORT.md](THE_STRONGHOLD_QA_REPORT.md#известные-ограничения).
Коротко:

1. Admin-редакторы контента охватывают правку существующих Fortress/Missions/Season
   Track/Store/Card Definition, создание новых Missions, создание Fortress (с
   авто-генерацией 6 матчей) и добавление отдельных матчей, создание Bundle-товаров
   с произвольным числом наград (currency/card). Не реализовано через UI: удаление
   (только toggle active — soft delete), создание Card Definition "с нуля", pack-контент
   в Bundle — делается через `stronghold_seed.py`/БД.
2. Пользовательский хендлер разделён на handlers/texts/keyboards (конвенция проекта).
   Admin-хендлер — один файл без такого разделения (динамические FSM-визарды дают
   меньше выгоды от разделения).
3. Нагрузочное тестирование не проводилось (неприменимо к single-process
   Telegram-боту с SQLite).
4. Тесты "конкурентности" в этом рантайме проверяют последовательную корректность
   (нет реальных точек приостановки в синхронном SQLite под `async def`), не
   классическую гонку потоков — см. пояснение в QA-отчёте.
5. Локализация (RU/EN) не добавлена — в проекте нет i18n-инфраструктуры вообще, добавлять
   её только для одного события значило бы создавать параллельную архитектуру.
6. Rate limiting — не отдельный механизм, а естественное ограничение Telegram UI +
   `match_guard`.

## Отличие от исходного ТЗ

Исходное ТЗ (10 промптов) было написано в терминах веб-приложения (REST API,
OpenAPI/Swagger, React-подобный frontend, браузерная RBAC admin-панель, k6). Реальный
проект — Telegram-бот. Экраны реализованы как Telegram-сообщения с inline-клавиатурами,
"API" — как внутренний слой Python-сервисов с типизированными dataclass-результатами и
единым набором кодов ошибок (см. THE_STRONGHOLD_API_REFERENCE.md), "admin panel" — как
Telegram admin-хендлеры под существующей ролевой моделью. Это осознанное решение, принятое
и подтверждённое в начале сессии, а не отклонение от задания.
