# THE STRONGHOLD — чек-лист релиза

Проверять перед активацией события на реальном проде. Каждый пункт — конкретная
команда или экран, а не общее пожелание.

## 1. Резервная копия

- [ ] Скопировать `data/nhl_bot.sqlite3` (или значение `DATABASE_PATH`) в безопасное
      место перед первым запуском версии с THE STRONGHOLD на проде.
- [ ] Убедиться, что Railway volume (`/app/data`) бэкапится штатным механизмом Railway
      или вручную (`railway_boot.py` не создаёт бэкапов сам).

## 2. Миграции и сид

- [ ] Задеплоить новую версию — `init_database()` автоматически создаст 24 таблицы
      `stronghold_*` и засеет контент при первом запуске `main.py`.
- [ ] Проверить логи первого запуска на отсутствие исключений при старте.
- [ ] Прогнать healthcheck: `python scripts/stronghold_healthcheck.py` (или экран
      «🩺 Healthcheck» в admin-панели THE STRONGHOLD) — все пункты должны быть OK.

## 3. Данные события

- [ ] `event_seeded`, `collection_complete` (23 карты), `upgrade_chain_complete`
      (375 FT / 4 050 000 Coins), `fortress_count_complete` (15) — все OK в healthcheck.
- [ ] Admin-панель → «✅ Проверить публикацию» — без ошибок (проверяет те же суммы +
      структуру Fortress/Missions/Season Track).
- [ ] Даты события (`starts_at`/`ends_at`) заданы и соответствуют плану ивента —
      задаются через admin-панель (Lifecycle) или напрямую в `stronghold_events`.

## 4. Экономика

- [ ] Upgrade Chain: 375 FT, 4 050 000 Coins суммарно (7 шагов) — см. п.3.
- [ ] Fortress: 220 FT суммарно по 15 крепостям — см. п.3.
- [ ] Daily Missions: 4 FT/день (→120 за 30 дней) — admin-панель → Missions.
- [ ] Weekly Missions: 20 FT/неделю (→80 за 4 недели) — admin-панель → Missions.
- [ ] Season Track: 50 FT суммарно по уровням — admin-панель → Season Track.
- [ ] Endless Siege: лимит 20 FT/неделю — `stronghold_endless_config.weekly_ft_cap`.
- [ ] Event Salary Cap: 45 000 000 (`salary.py:STRONGHOLD_SALARY_CAP`).

## 5. Fortress / Missions / Season Track / Store

- [ ] 15 Fortress × 6 матчей — healthcheck + admin Fortress-редактор.
- [ ] Все Daily/Weekly/Seasonal миссии активны (`active = 1`) — admin Missions.
- [ ] Все уровни Season Track настроены — admin Season Track.
- [ ] Товары Event Store активны и с корректными ценами — admin Store.

## 6. Тесты

- [ ] `pip install -r requirements-dev.txt && pytest` — все тесты зелёные (на момент
      написания: 56+ тестов, `tests/test_stronghold_*.py` + `test_regression_existing_systems.py`).
- [ ] `python scripts/stronghold_smoke_test.py` — PASSED (полный цикл: событие → кошелёк
      → Upgrade → Fortress → Missions → Season Track → Store → healthcheck).

## 7. Admin-доступ

- [ ] Хотя бы один админ с ролью, включающей `PERMISSION_STRONGHOLD`
      (`owner`/`senior_admin`/`economy_admin`), может открыть «🏰 THE STRONGHOLD».
- [ ] Проверить, что не-STRONGHOLD-админы (например `moderator`) корректно получают
      отказ в доступе к разделу.

## 8. Мониторинг/логирование

- [ ] Логи процесса (`main.py`, `stronghold_lifecycle_loop`) пишутся и видны в Railway
      logs — фоновая задача логирует переходы статуса и ошибки конвертации FT.
- [ ] `stronghold_audit_log` растёт при админских действиях (Lifecycle/компенсации/
      редактирование контента) — проверить через экран «📜 Аудит-лог».
- [ ] `stronghold_analytics_event` пишется при матчах Fortress (проверить SELECT COUNT
      после первых тестовых матчей).

## 9. Support-готовность

- [ ] Admin → «🔍 Поиск пользователя» находит игрока по Telegram ID и показывает
      баланс/прогресс.
- [ ] Admin → «🎁 Компенсация» (одиночная и массовая через «🧰 Массовые операции»)
      работает и пишет причину/request_id в аудит.

## 10. Запуск

- [ ] Активировать событие: admin-панель → Lifecycle → ACTIVE (или дождаться
      наступления `starts_at`, если статус `SCHEDULED`).
- [ ] После активации — ещё раз healthcheck + быстрый ручной прогон через
      `python scripts/stronghold_demo_seed.py --confirm` на STAGING/локально (не на
      проде — скрипт создаёт тестового игрока в реальной БД, к которой подключён).

## Rollback

Если после активации найдена критическая проблема:

1. Admin-панель → Lifecycle → перевести событие в `ARCHIVED` (блокирует новые
   действия, не трогает уже выданные награды/данные игроков).
2. Данные THE STRONGHOLD не пересекаются с остальными системами бота — откат не
   требует восстановления БД целиком, если проблема ограничена событием.
3. Полный откат кода — обычный Railway rollback на предыдущий деплой; таблицы
   `stronghold_*` останутся в БД (создание аддитивно, не мешает старой версии кода,
   которая их просто не использует).
