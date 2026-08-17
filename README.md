# NHL Telegram Card Bot — стартовый каркас

## Что уже готово

- запуск бота через `main.py`;
- переменные окружения через `.env`;
- `BOT_TOKEN` из env;
- `ADMIN_IDS` через запятую;
- команда `/start`;
- отдельная reply-клавиатура пользователя;
- отдельная reply-клавиатура администратора;
- заглушки под все основные разделы;
- Inline-кнопка возврата в главное меню;
- структура под будущие модули, БД и Railway.

## Как запустить локально

1. Создайте `.env` из примера:

```powershell
Copy-Item .env.example .env
```

2. Заполните `.env`:

```env
BOT_TOKEN=токен_бота
ADMIN_IDS=123456789,987654321
```

3. Установите зависимости:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. Запустите бота:

```powershell
python main.py
```

## Railway

В Railway нужно добавить переменные:

```env
BOT_TOKEN=токен_бота
ADMIN_IDS=123456789,987654321
```

Команда запуска уже указана в `railway.json`:

```bash
python main.py
```

## Надёжность турниров и инфраструктуры

Реализовано по ТЗ «комплексное повышение надёжности» (Этап 1 — критические фиксы турнирного
движка, Этап 2 — эксплуатация, Этап 3 — миграции/audit log/журнал ошибок). Подробности и
архитектурные решения — [docs/TOURNAMENT_RELIABILITY_SPEC.md](docs/TOURNAMENT_RELIABILITY_SPEC.md).

**Миграции, аудит, ошибки**: таблица `database_migrations` трекает новые структурные
изменения (старые ~30 аддитивных миграций в `db.py` не переписаны — они и так идемпотентны);
общий `audit_log` фиксирует турнирные действия, смену ролей администраторов и действия из
`/diagnostics`; `application_errors` собирает необработанные исключения хендлеров и краши
движка матчей — последняя ошибка и их количество за 24ч видны в `/diagnostics`.

**Турниры создателей**: состояния матчей (`waiting/playing/completed/failed/cancelled`),
восстановление после зависаний (кнопка «⚠️ Требуют внимания» в турнире — restart/force-sim/
cancel), идемпотентное завершение турнира и начисление наград, исправлен матч за 3-е место,
ручной ввод результата переживает перезапуск Railway (хранится в БД, а не в памяти).

**Backup**: автоматический ежедневный backup (`data/backups`, хранится 1 копия) и predeploy
backup перед изменением схемы (`data/predeploy_backups`, хранится 1 копия) — оба создаются
только если исходная БД проходит `PRAGMA quick_check`, и сами проверяются после создания.
Ручной backup (retention 2) доступен из `/diagnostics`.

**Render cache**: временный кэш рендера карточек больше не хранится на persistent Volume —
по умолчанию `/app/cache/render_cache` (настраивается через `RENDER_CACHE_PATH`, см.
`.env.example`); старый кэш на Volume удаляется автоматически при первом запуске после
обновления.

**Команды администратора**:

- `/version` — версия сборки, коммит (на Railway), время запуска, версия схемы БД;
- `/diagnostics` — состояние БД (`quick_check`, размер, WAL), свободное место на Volume,
  разбивка хранилища (uploads/backups/render cache), активные турниры и зависшие матчи;
  кнопки: проверить БД, очистить кэш, удалить старые бэкапы, создать backup вручную.

**Health-check**: фоновая проверка каждые 5 минут — БД (`quick_check`), заполнение Volume
(предупреждение <30%, автоочистка кэша <20%, автоудаление старых backup <15%, критический
алерт админам <10%) и зависшие матчи; повторные алерты одного типа подавляются cooldown'ом
30 минут, чтобы не спамить админов.

Известное ограничение: жёсткая блокировка миграций при <10% свободного места (раздел 13 ТЗ)
не реализована — только реактивные предупреждения/автоочистка через health-check выше.

## THE STRONGHOLD

Сезонное событие: коллекция из 23 карт, Upgrade Chain Miro Heiskanen 92→99, 15 Fortress
(по 6 матчей), Endless Siege, Daily/Weekly/Seasonal Missions, Season Track, Event Store.
Полная спецификация — [docs/THE_STRONGHOLD_SPEC.md](docs/THE_STRONGHOLD_SPEC.md), план
реализации — [docs/THE_STRONGHOLD_IMPLEMENTATION_PLAN.md](docs/THE_STRONGHOLD_IMPLEMENTATION_PLAN.md),
схема БД — [docs/THE_STRONGHOLD_DATABASE.md](docs/THE_STRONGHOLD_DATABASE.md), отчёт о
реализации — [docs/THE_STRONGHOLD_IMPLEMENTATION_REPORT.md](docs/THE_STRONGHOLD_IMPLEMENTATION_REPORT.md).

Отдельных миграций/сид-команд запускать не нужно — таблицы и контент THE STRONGHOLD
создаются автоматически при `init_database()` (то есть при обычном запуске `python main.py`,
как и весь остальной сид проекта). Событие стартует в статусе `DRAFT`: чтобы сделать его
видимым игрокам, администратор с доступом к разделу «🏰 THE STRONGHOLD» должен
запланировать/активировать его через Lifecycle в админ-панели (или напрямую в БД — см.
`stronghold_events.status`).

### Тесты

```powershell
pip install -r requirements-dev.txt
pytest
```

Тесты покрывают: миграции и идемпотентность сида, полную цепочку апгрейда 92→99,
недостаток средств, повтор `request_id`, конкурентные запросы, прохождение Fortress и
разблокировку следующей крепости/Endless Siege, недельный лимит FT в Endless Siege,
Missions (прогресс, claim, дневной сброс), Season Track, Event Store (лимиты, идемпотентность,
блокировка после Archive), автоконвертацию FT→Coins, admin-редакторы контента,
healthcheck и регресс существующих систем бота.

### Служебные скрипты

```powershell
python scripts/stronghold_healthcheck.py          # проверка БД/сида, exit-код 0/1
python scripts/stronghold_smoke_test.py            # сквозной прогон всех механик события
python scripts/stronghold_demo_seed.py              # dry-run (по умолчанию — ничего не меняет)
python scripts/stronghold_demo_seed.py --confirm     # создаёт тестового игрока с картой/валютой
```

Чек-лист перед активацией события на проде —
[docs/THE_STRONGHOLD_RELEASE_CHECKLIST.md](docs/THE_STRONGHOLD_RELEASE_CHECKLIST.md).
