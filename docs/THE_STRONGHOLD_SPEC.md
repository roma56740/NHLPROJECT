# THE STRONGHOLD — спецификация сезонного события

Единый источник правды для реализации события THE STRONGHOLD в NHL Telegram Card Bot.
Все последующие этапы разработки должны сверяться с этим документом; при расхождении
кода со спекой — приоритет у спеки, изменения в спеку вносятся осознанно и фиксируются.

## 0. Важное отличие от типового веб-проекта

Изначальное ТЗ на THE STRONGHOLD было написано в терминах веб-приложения (REST API,
OpenAPI/Swagger, отдельный frontend, браузерная admin panel с RBAC, k6-нагрузочные тесты,
Docker-микросервисы). Реальный проект — это **один Python-процесс** (aiogram 3, long polling,
Railway worker), без ORM (используется raw `sqlite3` + собственная миграционная система
`ensure_column`), без REST API и без отдельного frontend. UI пользователя и admin-панель —
это Telegram-сообщения с inline/reply-клавиатурами.

Поэтому вся спека ниже адаптирована так:

- «Frontend-экраны» → Telegram-хендлеры + inline-клавиатуры + тексты (`app/handlers`,
  `app/keyboards`, `app/texts`, `app/states` — по одному файлу `stronghold.py` в каждом).
- «Admin panel» → Telegram admin-хендлеры (`app/handlers/admin_stronghold.py`), защищённые
  той же ролевой системой (`app/services/admin_permissions.py`), а не отдельным веб-интерфейсом.
- «REST API / OpenAPI» → внутренний слой сервисов (`app/services/stronghold_*.py`) с чёткими
  сигнатурами функций, типизированными dataclass-результатами и единым набором кодов ошибок
  (см. раздел 9). Это функциональный эквивалент API-контракта, вызываемый напрямую из хендлеров.
- «Идемпотентность через requestId» → на уровне SQLite это уникальные constraint'ы
  (`UNIQUE(user_id, ...)`) + `BEGIN IMMEDIATE`-транзакции с проверкой `rowcount`, как это уже
  сделано в `app/services/shop.py`. Явный `request_id` всё равно вводится в
  `stronghold_upgrade_transactions` и `stronghold_store_purchases`, чтобы повторный клик кнопки
  Telegram не создавал вторую операцию.
- «k6-нагрузочные тесты» — не применимы к single-process Telegram-боту с SQLite; вместо этого
  делается упор на конкурентные unit/integration-тесты (двойной клик, гонки) через `pytest`.

Все требования по безопасности данных из исходного ТЗ соблюдаются буквально: существующая
БД не удаляется и не пересоздаётся, миграции только аддитивные (`ensure_column` /
`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`), `.env` не трогается, секреты
в Git не попадают.

## 1. Событие

- Название: **THE STRONGHOLD**.
- Основная фаза: **30 дней**.
- После основной фазы: **7 дней Upgrade Grace Period**.
- Состояния (`stronghold_events.status`):
  - `DRAFT` — создано, не запланировано, не видно игрокам.
  - `SCHEDULED` — есть `starts_at`/`ends_at`, ещё не наступило `starts_at`.
  - `ACTIVE` — основная фаза, доступны все механики.
  - `GRACE_PERIOD` — 7 дней после `ends_at`.
  - `ARCHIVED` — событие закрыто.

Переходы состояний выполняются либо фоновой задачей `stronghold_lifecycle_loop`
(по времени), либо вручную администратором (досрочное завершение, архивация).

### В ACTIVE доступны:

Все механики: коллекция, Upgrade Chain, Fortress, Endless Siege, Daily/Weekly/Seasonal
Missions, Season Track, Event Store.

### В GRACE_PERIOD доступны:

- просмотр события (Overview);
- Upgrade Chain (продолжение прокачки Хейсканена);
- Event Store — **только если** `stronghold_events.store_available_in_grace = 1`
  (конфигурируемый флаг конкретной публикации события);
- получение уже заработанных наград (claim того, что было закрыто до конца ACTIVE).

Недоступны в GRACE_PERIOD: новые Fortress-матчи, Endless Siege, начисление нового
прогресса миссий/Season Track (сами Claim уже выполненных — доступны).

### После окончания GRACE_PERIOD:

- новые действия блокируются (событие переходит в `ARCHIVED`);
- у всех пользователей с `fortress_tokens_balance > 0` выполняется автоконвертация:
  курс **1 FT = 5000 Coins**, начисление на основной баланс Coins;
  конвертация — идемпотентная фоновая задача (раздел 5.6).

## 2. Основные механики

1. Коллекция THE STRONGHOLD (23 Card Definition).
2. Upgrade Chain Miro Heiskanen 92 → 99 (7 шагов).
3. 15 Fortress, по 6 матчей в каждой.
4. Endless Siege (бесконечные волны после Fortress 15).
5. Daily / Weekly / Seasonal Missions.
6. Season Track (Event XP → уровни → награды).
7. Event Store (Featured / Packs / Cards / Resources / Bundles).
8. Fortress Tokens (FT) — новая событийная валюта, хранится в `currency_balances`
   с `currency_code = 'fortress_token'` (переиспользуется существующая таблица валют,
   не создаётся отдельный «event wallet»; см. раздел 4.1 почему).
9. Coins — существующая валюта проекта (`currencies.code = 'coins'`).
10. Аналитика/LiveOps — таблицы `stronghold_audit_log`, `stronghold_analytics_event`,
    экраны в admin-панели.
11. Административная панель — раздел «🏰 THE STRONGHOLD» в существующем admin-меню.

## 3. Коллекция

Отдельная событийная коллекция (`collections.code = 'the_stronghold'`), 23 Card Definition
(`cards` с `rarity = 'Event'`, `collection_id` → коллекция THE STRONGHOLD).

### Upgrade-цепочка (одна карта, 8 определений одного игрока):

```
Miro Heiskanen 92 / 93 / 94 / 95 / 96 / 97 / 98 / 99
```

### Остальные 15 карт коллекции:

| OVR | Игроки |
|-----|--------|
| 98  | Victor Hedman, Connor Hellebuyck, Jaccob Slavin |
| 97  | Charlie McAvoy, Moritz Seider, Sergei Bobrovsky, Aleksander Barkov |
| 96  | Devon Toews, Mackenzie Weegar, Jordan Staal, Jeremy Swayman |
| 95  | Brock Faber, Rasmus Andersson, Radko Gudas, Anthony Cirelli |

Итого: 8 (Heiskanen) + 15 (остальные) = **23 Card Definition**.

Позиция/страна/команда/зарплата заполняются по существующему справочнику проекта
(`cards.team`, `cards.country`, `cards.position` CHECK `G|D|F`, `cards.salary`); если по
конкретному игроку нет точного значения в текущих данных — используется разумное реальное
значение NHL. `image_path` — стабильный asset key вида
`assets/uploads/stronghold/<player_key>_<ovr>.png`; при отсутствии файла рендер карточек
(`app/services/renders.py`) уже поддерживает fallback на плейсхолдер — новый механизм не
нужен.

## 4. Upgrade Chain

### 4.1 Почему не отдельный "Event Wallet"

В проекте уже есть универсальная модель `currencies` + `currency_balances`
(`user_id, currency_code` → `amount`). Создание отдельной сущности `EventWallet` было бы
параллельной архитектурой к уже существующей — вместо этого:

- добавляется новая строка в `currencies`: `code = 'fortress_token'`, `name = 'Fortress Token'`.
- баланс FT — обычная строка `currency_balances` с этим `currency_code`.
- отдельная таблица `stronghold_currency_ledger` ведёт историю начислений/списаний FT и
  Coins **в контексте события** (обычный `currency_balances` историю не хранит) — это и есть
  «Currency Ledger» из исходного ТЗ.

### 4.2 Стоимость шагов

| Переход | FT  | Coins      |
|---------|-----|------------|
| 92→93   | 20  | 150 000    |
| 93→94   | 30  | 250 000    |
| 94→95   | 40  | 400 000    |
| 95→96   | 50  | 550 000    |
| 96→97   | 65  | 700 000    |
| 97→98   | 75  | 900 000    |
| 98→99   | 95  | 1 100 000  |
| **Итого** | **375** | **4 050 000** |

Сумма проверяется программно в seed-скрипте (assert) и в admin-валидации публикации
конфигурации (раздел 8).

### 4.3 Правила Upgrade

- Preview ничего не списывает и не меняет карту, только считает и возвращает предупреждения.
- Confirm выполняется одной SQLite-транзакцией (`BEGIN IMMEDIATE ... COMMIT`), по аналогии
  с `shop.py:purchase_shop_pack`:
  1. Валидация состояния события (`ACTIVE` или `GRACE_PERIOD`, иначе ошибка).
  2. Проверка владения `user_cards.id` и что карта — актуальный шаг Upgrade Chain
     THE STRONGHOLD (по `card_id` → `stronghold_upgrade_steps.from_card_id`).
  3. Проверка, что карта не в `is_in_lineup` активного матча (см. `match_guard.py`), не
     выставлена на рынке/трейде (`trade_offer_cards`, будущий модуль рынка — если в проекте
     появится — тем же паттерном), не заблокирована (`trade_locked`/`lock_until`).
  4. Проверка баланса Coins и FT (`currency_balances`, guarded `UPDATE ... WHERE amount >= ?`).
  5. Списание Coins и FT, запись в `stronghold_currency_ledger` (2 строки).
  6. `UPDATE user_cards SET card_id = <next_card_id>, updated_at = CURRENT_TIMESTAMP WHERE id = ?`
     — карта **не удаляется и не создаётся заново**, обновляется `card_id` той же строки
     `user_cards`, чтобы сохранить `id`, `lineup_slot`, историю трейдов и т.д. (это и есть
     «наследование допустимых свойств старой карты», реализованное максимально просто и
     безопасно для SQLite).
  7. Запись в `stronghold_upgrade_transactions` (аудит, `request_id` для идемпотентности).
  8. Запись в `stronghold_audit_log`.
- Идемпотентность: `stronghold_upgrade_transactions` имеет
  `UNIQUE(user_id, request_id)`. Confirm сначала пытается `INSERT` строки транзакции со
  статусом `pending`; если конфликт — читает существующую строку и, если `status='success'`,
  возвращает её результат повторно **без повторного списания**.
- Гонки: `BEGIN IMMEDIATE` берёт write-lock на всю БД (SQLite не поддерживает row-level
  locking), это достаточно для однопроцессного бота — второй параллельный confirm блокируется
  до коммита первого, затем читает уже обновлённую карту и корректно завершается ошибкой
  `CARD_NOT_IN_UPGRADE_CHAIN` / `UPGRADE_ALREADY_PROCESSED`.

## 5. Экономика FT

| Источник | FT |
|---|---|
| Fortress: первое полное прохождение всех 15 | 220 |
| Daily Missions за 30 дней | 120 (4/день) |
| Weekly Missions за 4 недели | 80 (20/неделя) |
| Season Track | 50 |
| Endless Siege | максимум 20/неделю |
| **Общий потолок без Endless Siege** | **470** |

Итоговая максимальная сумма Upgrade — 375 FT, то есть у игрока, проходящего все механики,
есть запас (470 + Endless Siege) — это осознанный запас, а не ошибка баланса.

- Event Salary Cap: **$45 000 000**. В единицах проекта (`cards.salary`/`salary.py` хранят
  зарплату в тысячах $, см. `LEAGUE_SALARY_CAPS`/`CLAN_WAR_SALARY_CAP`) это константа
  `salary.py:STRONGHOLD_SALARY_CAP = 45000`.
- Для участия в Fortress/Endless Siege в составе (`lineup`) должна быть минимум 1 карта
  коллекции THE STRONGHOLD.
- Зарплаты карт THE STRONGHOLD хранятся в `cards.salary` (существующее поле) — отдельной
  «конфигурируемой таблицы зарплат» не создаётся, т.к. в проекте она уже есть
  (`cards.salary`, курируется вручную через admin, без хардкода в бизнес-логике).

### 5.6 Автоконвертация FT после Grace Period

Фоновая задача `stronghold_conversion_loop`, идемпотентная, пакетная (батчи по 200
пользователей), с записью в `stronghold_currency_ledger` (списание FT + начисление Coins)
и `stronghold_audit_log`. Флаг `stronghold_ft_conversions.converted_at IS NOT NULL`
предотвращает повторную конвертацию пользователя. Безопасна для перезапуска процесса
(SQLite — один writer, распределённая блокировка не нужна).

## 6. Fortress

15 записей `stronghold_fortresses` (`order_index` 1..15), у каждой 6
`stronghold_fortress_matches`. Открытие строго последовательное: Fortress N+1 доступна
только когда у пользователя `stronghold_user_fortress_progress` для Fortress N имеет
`status = 'COMPLETED'`.

Статусы Fortress пользователя: `LOCKED / AVAILABLE / IN_PROGRESS / COMPLETED`.
Статусы матча: `LOCKED / AVAILABLE / STARTED / WON / LOST / COMPLETED`.

Звёзды (1-3) — конфигурируемые условия на уровне матча (`stronghold_fortress_matches.star_rules`,
JSON): победа, разница шайб, пропущено не больше X, использована карта коллекции,
дополнительное условие. Хранение через JSON-колонку — по аналогии с
`matches.periods_summary TEXT` (уже используемый в проекте паттерн сериализации в TEXT).

220 FT распределены по 15 Fortress без дробных значений, с повышенной наградой у Fortress 15
(boss). Точное распределение — конфигурация в seed (раздел seed-документа), не хардкод.

Повторное прохождение не выдаёт FT повторно (unique `(user_id, fortress_id)` в таблице
выданных first-completion наград), но может выдавать Coins по конфигурации.

## 7. Endless Siege

Разблокируется после Fortress 15 (`COMPLETED`). Волны — `stronghold_endless_waves`
(per-user append-only лог), сложность растёт по конфигурируемой формуле
(`stronghold_endless_config`, не хардкод в коде). Модификаторы волны хранятся как JSON.

Лимит FT: **20/неделю**, неделя считается сервером (ISO-неделя по UTC,
`stronghold_endless_weekly_ft.week_key`), не зависит от локального времени клиента.
После лимита волны продолжают быть доступны, но FT не начисляется (начисляются другие
разрешённые награды).

Leaderboard — `stronghold_leaderboard_entries` (лучшая волна + tie-breaker по времени
достижения), пагинация через `LIMIT/OFFSET`.

## 8. Missions, Season Track, Event Store

- Missions: типы `DAILY / WEEKLY / SEASONAL`, статусы
  `LOCKED / ACTIVE / COMPLETED / CLAIMED / EXPIRED`. Прогресс начисляется только
  сервер-инициированными событиями (пост-хуки в `matches.py:save_match_result`,
  Fortress/Endless сервисах, upgrade-сервисе), клиентский прогресс не принимается —
  тот же принцип, что уже используется для `quests`/`events`.
- Season Track: Event XP → уровни → награды, суммарно 50 FT, распределены по нескольким
  milestone-уровням (конфигурация в seed). Модель по аналогии с `hockey_passes` /
  `hockey_pass_rewards`, но отдельная таблица под THE STRONGHOLD (без premium-дорожки —
  проект её не использует, но структура таблицы не мешает добавить её позже).
- Event Store: категории Featured/Packs/Cards/Resources/Bundles, валюта FT или Coins.
  Реальные платёжные валюты (Stars/рубли) **не подключаются** — в проекте нет готового
  безопасного платёжного модуля для внешних платежей THE STRONGHOLD (есть только внутренняя
  валюта `energy`/«рубли», которая уже обрабатывается как обычная игровая валюта — она
  доступна как способ оплаты наравне с FT/Coins, если админ включит её у конкретного товара).
  Покупка — атомарная транзакция аналогичная `purchase_shop_pack`, для Bundle — все элементы
  выдаются в одной транзакции или откатываются полностью.

## 9. Коды ошибок

Единый `StrongholdError(code: str, message: str)` (Python exception), перехватывается в
хендлерах и превращается в понятное сообщение пользователю/админу. Коды:

```
EVENT_NOT_ACTIVE, EVENT_ARCHIVED, UPGRADE_GRACE_PERIOD_ENDED,
CARD_NOT_FOUND, CARD_NOT_OWNED, CARD_NOT_IN_UPGRADE_CHAIN, CARD_ALREADY_MAX_LEVEL,
UPGRADE_STEP_NOT_FOUND, INSUFFICIENT_COINS, INSUFFICIENT_FORTRESS_TOKENS,
CARD_LISTED_ON_MARKET, CARD_IN_PENDING_TRADE, CARD_IN_ACTIVE_MATCH, CARD_LOCKED,
SALARY_CAP_EXCEEDED, REQUEST_ID_CONFLICT, UPGRADE_ALREADY_PROCESSED,
INTERNAL_TRANSACTION_ERROR,
MISSION_NOT_FOUND, MISSION_NOT_ACTIVE, MISSION_NOT_COMPLETED, MISSION_ALREADY_CLAIMED,
MISSION_EXPIRED, SEASON_LEVEL_LOCKED, SEASON_REWARD_ALREADY_CLAIMED,
PRODUCT_NOT_FOUND, PRODUCT_NOT_AVAILABLE, PRODUCT_EXPIRED, PURCHASE_LIMIT_REACHED,
INSUFFICIENT_CURRENCY, INVALID_PRODUCT_CONFIGURATION, PURCHASE_ALREADY_PROCESSED,
FORTRESS_LOCKED, FORTRESS_MATCH_LOCKED, MATCH_RESULT_ALREADY_SUBMITTED,
COLLECTION_CARD_REQUIRED, ENDLESS_SIEGE_LOCKED
```

## 10. Сервер как единственный источник истины

Ни цена, ни награда, ни OVR, ни FT/Coins/Event XP никогда не принимаются от клиента —
Telegram передаёт только `callback_data` с идентификаторами (`user_card_id`, `fortress_id`,
`match_id`, `product_id`), вся арифметика и проверки — на сервере, в сервис-слое.

## 11. Открытые технические решения (зафиксированы, не переспрашивались)

- FT — валюта в существующей таблице `currencies`, не отдельная сущность.
- Upgrade не создаёт новую строку `user_cards`, а переиспользует существующую (проще,
  атомарнее, не плодит "мёртвые" строки в SQLite без транзакционного DELETE+INSERT).
- Тестов в проекте не было вообще — вводится `pytest` + `tests/` с нуля (раздел QA).
- Git не используется в этой сессии по решению пользователя — вместо ветки
  `feature/the-stronghold` изменения вносятся напрямую, с чёткой фиксацией в
  `THE_STRONGHOLD_IMPLEMENTATION_REPORT.md`.
