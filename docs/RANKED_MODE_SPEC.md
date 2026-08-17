# RANKED MODE (v1) — спецификация, архитектура и отчёт о реализации

Реализовано поверх существующего проекта, без переписывания и без поломки старого
функционала (обычные матчи/лиги/зарплатный лимит/карты/коллекции/паки/инвентарь/
Hockey Pass/админка). Построено по плану из этой же сессии
(`C:\Users\Eric\.claude\plans\harmonic-wandering-glade.md`).

**Это первая версия Ranked Mode, не "2.0"** — в проекте не было предыдущей системы
ранкед-режима. Новый
проект не создавался — всё реализовано внутри существующего `NHLPROJECT`.

## 0. Ключевые решения (binding)

- Префикс: **`ranked_`** для всех новых таблиц/сервисов/хендлеров. Callback-префиксы
  `ranked:` (игрок) / `admin_ranked:` (админ). Избежаны две легаси-строки
  (`LEGACY_DEMO_COLLECTION_CODES`/`LEGACY_DEMO_PACK_CODES` содержат буквально
  `"ranked"`/`"ranked-pack"` и удаляются на каждом запуске бота) — новые коды
  `ranked_season1_legends` (коллекция) и `ranked_pack_<division>` (7 паков).
- **Косметика: обобщена, не утроена.** CLAN WAR 2.0-таблицы `war2_cosmetic_items`
  (каталог)/`user_cosmetic_items` (владение) теперь ОБЩИЕ для CLAN WAR 2.0 и RANKED
  MODE. Физически имена таблиц НЕ переименованы (решение отличается от исходного
  плана, который предлагал ренейм `war2_cosmetic_items` → `cosmetic_items`) — вместо
  этого `type` CHECK расширен на месте (миграция с пересборкой таблицы под тем же
  именем, см. раздел 12) до 6 значений: `FRAME`, `BACKGROUND`, `NICK_BADGE`
  (существующие, CLAN WAR 2.0) + `CARD_FRAME`, `PROFILE_BACKGROUND`, `TITLE` (новые,
  Ranked). Причина отклонения от плана: ренейм потребовал бы дополнительно
  перепроверить/переписать все FK и код, ссылающийся на старое имя, ради
  косметического выигрыша — расширение CHECK на месте безопаснее и делает то же самое.
  `NICK_BADGE` — буквально общее понятие для обеих систем.
- **CARD_FRAME ≠ war2 FRAME.** war2 FRAME декорирует КАЖДУЮ карту в отрендеренном
  составе (render-time override). CARD_FRAME привязывается к ОДНОЙ конкретной
  собственной карте через новую таблицу-связку `user_card_frames` (раздел 6).
- **Матчи: не копия `enter_matchmaking()`, а мгновенный подбор** (как у CLAN WAR 2.0),
  а не дословная очередь с фоновым watcher-таском и per-поиск sleep-тасками,
  привязанными к `chat_id`/`message_id` в хендлере. Осознанное упрощение: см.
  раздел 5, это единственное отклонение от исходного плана в разделе "матч-флоу".
  `record_ranked_match_result` не вызывает `matches.save_match_result()` — та
  безусловно меняет `users.matches_played/wins/losses/rating_points/league` (обычная
  лестница), что было бы неверно для Ranked. Переиспользована только математика
  (`build_simulation`/`choose_scorer`/`calculate_rating_delta`).
- **Ранг — двунаправленный** (очки растут и падают), в отличие от одностороннего
  прогресса NCAA→OLYMPICS. Дивизион/тир — чистая функция текущего `rank_points`
  относительно admin-редактируемой таблицы порогов (`ranked_leagues`), пересчитывается
  заново на каждом матче. Деён (демоушен) не требует отдельного кода — следует из
  конструкции.
- **Ranked Pack — новые таблицы**, не расширение общего `packs`/`pack_slots`
  (у общего слот умеет выдавать только карту; Ranked нужны 4 типа наград).
- **Ranked Pass — новые таблицы**, не общие строки с Hockey Pass (`hockey_pass_rewards
  .level` жёстко `CHECK(1-40)`, 2 линии; Ranked нужно 60 уровней/3 линии).

## 1. NORMAL MODE — без зарплатного лимита, без Ranked-рейтинга

`app/services/matches.py`:
- `enter_matchmaking()` и `play_quick_match()` — удалены блокирующие блоки
  `if overview.salary_cap and overview.salary_total > overview.salary_cap: ...`.
  `play_player_match()` такой проверки не имел изначально — не менялся.
- `get_lineup_overview()` (`app/services/lineup.py`) **не менялся** — по-прежнему
  считает `salary_total`/`salary_cap` для информационного отображения на экранах
  профиля/состава. Убрано только блокирование старта матча, не вся зарплатная UI.
- `match_queue` получила аддитивную колонку `mode TEXT NOT NULL DEFAULT 'normal'`
  (`ensure_column`). `enter_matchmaking()`'s SELECT/INSERT явно фильтруют/пишут
  `mode = 'normal'` — существующее поведение не меняется (дефолт есть у всех старых
  строк). Колонка задумана на будущее, если Ranked когда-нибудь перейдёт с мгновенного
  подбора на очередь — сейчас Ranked её не использует (см. раздел 5).
- Ranked-рейтинг живёт в отдельных таблицах (`ranked_player_stats`), обычные матчи их
  никогда не пишут — "без Ranked рейтинга" выполнено по конструкции.

## 2. RANKED ACCESS

`app/services/ranked_core.py:is_ranked_eligible(league)` — переиспользует существующий
порядок `app.services.matches.LEAGUES` (`LEAGUES.index(league) >= LEAGUES.index("AHL")`),
новый список лиг не изобретён. Проверяется в начале `play_ranked_match()` и на главном
экране `ranked:` (понятное сообщение с указанием нужной лиги вместо запуска матча).

## 3. SALARY CAP — переиспользован, не пересобран

`app/services/salary.py`: `RANKED_SALARY_CAP = 54000` — тот же формат хранения
(тысячи $), что и у всех остальных лимитов файла (`STRONGHOLD_SALARY_CAP`,
`CLAN_WAR_SALARY_CAP=70000`, `WAR2_SALARY_CAP`). `54000` = $54,000,000 = "54M", а не
буквальные `54_000_000`. `play_ranked_match()` сравнивает `overview.salary_total >
RANKED_SALARY_CAP` (не `overview.salary_cap` — это лиговый потолок, к Ranked не
относится) и переиспользует существующий `format_salary()` без изменений для текста
блокировки.

## 4. RANKED SEASON

Новая таблица `ranked_seasons` (id, season_number, status
CHECK(scheduled/active/ended), starts_at, ends_at, top_json). Длительность —
`game_settings.ranked_season_length_days` (по умолчанию **56**). Существующие сезоны
(`seasons`/`war2_seasons`, ~28 дней) не тронуты — "другие сезоны
остаются 28 дней" выполнено тем, что их код вообще не менялся.

`start_ranked_season()` — не даёт запустить второй активный сезон одновременно
(`RankedError("SEASON_ALREADY_ACTIVE")`). `end_ranked_season()` — снимок топ-25 в
`top_json`, статус → `ended`. **`ranked_player_stats` НЕ удаляются** (историчны,
привязаны к `season_id`) — новый сезон стартует "с нуля" просто потому, что для нового
`season_id` ещё нет строк статистики (тот же приём, что и у `war2_player_stats`).

## 5. RANK SYSTEM

- `ranked_leagues` — 21 запись (7 дивизионов × 3 тира): Bronze/Silver/Gold/Platinum/
  Diamond/Master/Legend, `UNIQUE(division_code, tier_number)`, порог `min_points`
  admin-редактируемый. Сидируется `ranked_seed.py` с восходящей лестницей порогов
  (Bronze 0/100/200 → Legend 5500/6300/7100).
- `compute_ranked_division(rank_points)` — чистый запрос
  `ORDER BY min_points DESC WHERE min_points <= ? LIMIT 1`, не кэшируемая
  промоушен/демоушен-логика.
- `ranked_player_stats` (season_id, user_id, rank_points, ranked_league_id [денорм.
  кэш], ranked_xp, wins, losses, matches_played), `UNIQUE(season_id, user_id)`.
- `ranked_matches` — история матчей (opponent_*, score, result, rank_delta,
  division_before/after) — `get_match_history()` отдаёт её игроку.
- Рейтинг: `calculate_rating_delta()` переиспользована as-is (уже возвращает
  отрицательную дельту при поражении) — `rank_points = max(0, rank_points + delta)`.

**Матч-флоу**: `play_ranked_match(telegram_id)` — единый вызов (подбор соперника
мгновенный, отдельного экрана "идёт поиск" не нужно, как и у `play_quick_match`):
доступ (AHL+) → состав заполнен → зарплатный лимит 54M → лок матча
(`try_acquire_match_lock`) → мгновенный подбор соперника
(`find_ranked_opponent` — реальный игрок AHL+ с ближайшим `rank_points`, иначе бот) →
`build_simulation`/`calculate_rating_delta`/`choose_scorer` (переиспользованы как есть)
→ одна транзакция: `ranked_player_stats` upsert, пересчёт дивизиона до/после (см.
баг №2 ниже), `_grant_league_reward`, начисление XP, запись в `ranked_matches`.

## 6. RANK REWARDS

`ranked_league_rewards` (ranked_league_id, reward_type CHECK(cosmetic/currency/pack),
cosmetic_item_id, currency_code, amount, **pack_id → ranked_packs(id)**). Сидирована:
тир 1 каждого дивизиона → `NICK_BADGE`, тир 2 → `CARD_FRAME`, тир 3 →
`PROFILE_BACKGROUND` (косметика с division-тематическим названием, создана через
`war2_cosmetics`-совместимый `_get_or_create_cosmetic_item` в `ranked_seed.py`).

Идемпотентная выдача — `ranked_league_reward_claims`, `UNIQUE(user_id, season_id,
ranked_league_id)`: вставка в claims-таблицу и сама выдача — в ОДНОЙ транзакции с
обновлением рейтинга, поэтому демоушен-затем-повторный-подъём в течение сезона не
выдаёт награду повторно.

**CARD_FRAME → ровно одна карта.** Новая таблица `user_card_frames(user_id,
user_cosmetic_item_id UNIQUE, user_card_id UNIQUE)` — обе UNIQUE-колонки вместе дают
запрошенную связку player_id/frame_id/card_id "один к одному": одна купленная/
полученная рамка украшает максимум одну карту, одна карта носит максимум одну рамку.
`app/services/ranked_cosmetics.py:bind_frame_to_card()` — валидирует владение обеими
сторонами, тип строго `CARD_FRAME`, "перепривязка" реализована как одна транзакция
DELETE старых связей (по любой из двух сторон) → INSERT новой — без отдельного шага
"отвязать сначала".

## 7. INVENTORY

`NICK_BADGE`, `CARD_FRAME`, `PROFILE_BACKGROUND`, `TITLE` — все живут в уже
существующих (расширенных, раздел 0) `war2_cosmetic_items`/`user_cosmetic_items` —
"все предметы — inventory objects" выполнено по конструкции, включая уже готовые
future-market-ready поля (`owner_id`, `type`, `rarity`, `source`) на строке владения.

## 8. RANKED PACK

Новые таблицы (по образцу существующих `packs`/`pack_slots`/`pack_cards`, но со слотом,
поддерживающим 4 типа наград): `ranked_packs` (code UNIQUE, division_code, name),
`ranked_pack_slots` (reward_type CHECK(card/currency/xp/cosmetic), currency_code,
amount, cosmetic_item_id), `ranked_pack_cards` (pack_id, card_id, UNIQUE — пул карт для
card-слотов), `user_ranked_packs` (владение, quantity). `open_ranked_pack()`
(`app/services/ranked_packs.py`) — одна транзакция, обходит все активные слоты пака,
для card-слота тянет случайную карту из `ranked_pack_cards` (`ORDER BY RANDOM()`).
Сидировано 7 паков (`ranked_pack_bronze` … `ranked_pack_legend`), у каждого по
умолчанию один функциональный XP-слот (50 XP) — админ донастраивает реальные награды
(раздел 12).

## 9. RANKED SEASON 1 LEGENDS

`ranked_seed.py:_seed_legends_collection()` — создаёт ТОЛЬКО `collections`-строку
(`code='ranked_season1_legends'`, `is_exclusive=1`), **ноль хардкоженных карт** — по
прямому требованию ТЗ ("не хардкодить игроков жёстко"). Карты добавляет
администрация через уже существующий, полностью обобщённый по `collection_id`
`admin_cards.py` — то же самое переиспользование, что и у CLAN WAR Legends. Плейсхолдер
для отсутствующей картинки — уже существующее поведение `renders.py`
(`resolve_asset_path`/`_placeholder_card`), новый код не потребовался.

## 10. PASS SYSTEM (60 уровней, FREE/GOLD/PLATINUM)

`ranked_passes` (season_id, levels_count DEFAULT 60, points_per_level DEFAULT 100,
gold/platinum/upgrade currency+price), `ranked_pass_rewards` (level CHECK(1-60), track
CHECK(free/gold/platinum), reward_type CHECK(currency/pack/card/cosmetic), **pack_id →
packs(id)** — общий пак-магазин, та же семантика, что у `hockey_pass_rewards.pack_id`),
`user_ranked_passes` (gold_unlocked, platinum_unlocked, purchased_at,
platinum_purchased_at), `user_ranked_pass_rewards` (claim-таблица).

`calculate_ranked_level(xp, points_per_level, levels_count)` — та же формула, что
`hockey_pass.calculate_level()` (`min(levels_count, max(1, xp // points_per_level +
1))`), но параметризована (там `40` зашито буквально).

## 11. PASS XP (без квестов)

**"Не добавлять quests" выполнено буквально** — XP НЕ идёт через
`app/services/quests.py`. Начисляется прямо внутри транзакций:
- `play_ranked_match()` — флэт-сумма за матч + бонус за победу + одноразовый бонус за
  первый в этом сезоне переход в новый ДИВИЗИОН (не под-тир). Все три суммы —
  `game_settings` (`ranked_xp_per_match`=20, `ranked_xp_win_bonus`=30,
  `ranked_xp_division_up_bonus`=150 по умолчанию), не хардкод — оператор может
  подстроить баланс без деплоя.
- `open_ranked_pack()` — XP-слоты паков.

Баланс по умолчанию: активный игрок (несколько матчей в день, регулярные победы,
переходы дивизионов) проходит все 60 уровней за 56-дневный сезон с запасом;
неактивный (эпизодические заходы) — не проходит, что и требовалось.

## 12. PASS PURCHASE (Gold/Platinum + апгрейд)

`purchase_gold()` — списание валюты, `user_ranked_passes.gold_unlocked=1` (по образцу
`hockey_pass.purchase_premium()`). `upgrade_gold_to_platinum()` — **новое поведение,
которого нет у Hockey Pass** (там апгрейда между линиями не существует): списывает цену
апгрейда, ставит `platinum_unlocked=1`, затем **ретроактивно выдаёт все уже
достигнутые Platinum-награды** (цикл `level in 1..current_level`, `track='platinum'`,
пропуская уже полученные через `sqlite3.IntegrityError`-перехват на claim-INSERT),
возвращает число выданных наград для подтверждения в UI. Это единственное место, где
Ranked Pass намеренно отходит от поведения Hockey Pass — по прямому требованию ТЗ
("После покупки: выдать все уже открытые Platinum rewards").

## 13. ADMIN PANEL

`app/handlers/admin_ranked.py` (+ `app/states/admin_ranked.py`), монолитный inline-
стиль, как и `admin_war2.py` (тот же осознанный выбор этой сессии — единый обзор
многоэкранного flow важнее строгого разделения на файлы при заданном объёме задачи):
- **Сезон**: старт (56 дней по умолчанию из настроек)/финиш — мирроринг
  `admin_war2.py`.
- **Ranked leagues**: список из 21 записи (постранично, 7/страница), редактирование
  `min_points` через FSM-текстовый ввод. **Осознанное ограничение**: `title`/`icon`
  не редактируются через UI (только через прямой SQL) — набор из 21 дивизиона/тира
  фиксирован спецификацией, редактирование порогов — то, что реально нужно
  операционно; названия менять предполагается редко и не через Telegram-текстовый
  ввод посимвольно.
- **Ranked Packs**: список 7 паков → детальный экран (текущие слоты + размер пула
  карт) → добавление слота "валюта"/"XP" (текстовый ввод суммы) → **добавление карты
  в пул** (текстовый ввод `card_id`, автоматически создаёт `card`-слот при первом
  добавлении, если его ещё нет) — этот последний пункт был обнаружен как пробел уже
  после первой сборки админки (сервисный слой `open_ranked_pack()` полностью
  поддерживал card-слоты, но UI для их наполнения отсутствовал) и добавлен в этом же
  заходе.
- **Ranked Pass**: создание пропуска (title/gold_price/platinum_price/upgrade_price
  через 4-шаговый FSM; `levels_count=60`, `points_per_level=100`, `currency='coins'`
  зафиксированы при создании), добавление наград по уровню/линии
  (`"5,gold"`-текстовый ввод уровня+линии → сумма → название; `reward_type='currency'`
  зафиксирован для этого быстрого UI-пути — card/pack/cosmetic-награды пропуска
  добавляются напрямую через БД, отдельного UI для них нет, см. раздел 15).
- **Косметика**: 4 вкладки (`NICK_BADGE`/`CARD_FRAME`/`PROFILE_BACKGROUND`/`TITLE`),
  полностью переиспользует функции `war2_cosmetics.py` (общий каталог, раздел 0) —
  создание (код/название/редкость/[текст приставки ИЛИ загрузка PNG]),
  включение/выключение, выдача игроку по `telegram_id` (тот же lookup-паттерн, что у
  `admin_war2.py`/`stronghold_admin.py`).
- **Ranked Season 1**: отдельного экрана нет — коллекция управляется целиком
  существующим `admin_cards.py` (тот же выбор, что у CLAN WAR Legends).

Права: `PERMISSION_RANKED` (новая, только добавления в `admin_permissions.py`) —
выдана `ADMIN_ROLE_ECONOMY`, `admin_ranked:` зарегистрирован в
`CALLBACK_PERMISSION_PREFIXES`. Ни одна существующая роль/префикс не изменены.

Вход в игровой экран — новая строка reply-клавиатуры "🏆 Ranked Mode"
(`app/keyboards/reply.py:USER_MAIN_BUTTONS`, сразу под "🏰 THE STRONGHOLD"). Вход в
админку — из общего экрана `ranked:`, видна только `is_admin()` (тот же паттерн, что у
THE STRONGHOLD/CLAN WAR 2.0 — не через общий `admin_panel.py`).

## 14. База данных

14 новых таблиц (`CREATE TABLE IF NOT EXISTS`, добавлены в `SCHEMA_QUERIES`):
`ranked_seasons`, `ranked_leagues`, `ranked_player_stats`, `ranked_matches`,
`ranked_league_rewards`, `ranked_league_reward_claims`, `user_card_frames`,
`ranked_packs`, `ranked_pack_slots`, `ranked_pack_cards`, `user_ranked_packs`,
`ranked_passes`, `ranked_pass_rewards`, `user_ranked_passes`,
`user_ranked_pass_rewards` (это 15 — счёт включает и claim-таблицы). Плюс:
- Одна аддитивная колонка: `match_queue.mode` (`ensure_column`).
- Одна миграция-расширение существующей таблицы: `war2_cosmetic_items.type` CHECK
  расширен с 3 до 6 значений через пересборку таблицы под тем же именем
  (`app/database/db.py:migrate_cosmetic_catalog_shared_types()` — CHECK-constraint в
  SQLite нельзя ALTER, поэтому: `CREATE TABLE ...__rebuild` с новым CHECK → `INSERT ...
  SELECT` всех колонок с сохранением ID → `DROP TABLE` старой → `RENAME TO` обратно в
  исходное имя). Проверено вручную: существующие строки (включая id) сохраняются
  байт-в-байт, FK у `user_cosmetic_items.cosmetic_item_id` не затронуты (SQLite
  резолвит FK по имени таблицы, не по объектному идентификатору, поэтому после
  RENAME обратно в `war2_cosmetic_items` все внешние ссылки продолжают работать без
  каких-либо правок в зависимых таблицах).
- 4 новых `game_settings`: `ranked_season_length_days` (56), `ranked_xp_per_match`
  (20), `ranked_xp_win_bonus` (30), `ranked_xp_division_up_bonus` (150).

`users`/`cards`/`collections`/`user_cards`/`leagues`/`hockey_pass*` — только читаются
новым кодом, ни одна существующая таблица не изменена структурно (кроме описанного
CHECK-расширения) и ни одна строка не удаляется никаким новым кодом.

## 15. Расхождения с планом / осознанные упрощения

- **Cosmetic-таблица НЕ переименована** (`war2_cosmetic_items` → `cosmetic_items`),
  вопреки исходному плану — вместо этого CHECK расширен на месте под тем же именем.
  Функционально идентично тому, что предлагал план (общий каталог для двух фич), но
  ниже риск: не пришлось искать и править все места, ссылающиеся на старое имя
  таблицы по всему проекту.
- **Матчи используют мгновенный подбор соперника** (как у CLAN WAR 2.0), а не
  дословную реплику `enter_matchmaking()`'s очереди с фоновым watcher-таском.
  Реальный `enter_matchmaking()` завязан на инфраструктуру уровня хендлера
  (`chat_id`/`message_id`, `asyncio.sleep`-таски) — воспроизводить её для Ranked v1
  означало бы дублировать существенный объём async-инфраструктуры ради результата,
  который мгновенный подбор уже даёт игроку (реальный соперник подходящего уровня,
  либо бот). Прямо соответствует собственной формулировке ТЗ "первая версия" —
  очередь с ожиданием можно добавить отдельной задачей позже, `match_queue.mode`
  оставлена задела ради (см. раздел 1).
- **Ranked leagues admin UI редактирует только `min_points`**, не `title`/`icon` —
  см. раздел 13. Осознанное ограничение, не пробел: набор дивизионов/тиров
  фиксирован спецификацией (7×3), не предполагает добавления/удаления через UI.
- **Ranked Pass reward admin UI создаёт только `reward_type='currency'`** награды.
  Card/pack/cosmetic-награды пропуска поддерживаются полностью на уровне сервиса
  (`_deliver_reward()` в `ranked_pass.py` обрабатывает все 4 типа), но быстрый
  текстовый FSM для их создания через Telegram не реализован — операционно это
  редко нужные, штучные записи, добавляются прямой SQL-строкой при настройке
  пропуска на сезон. Задокументировано как известное ограничение, не бага.
- **Пробел, найденный и закрытый в этом же заходе**: изначальная версия админки
  Ranked Packs позволяла добавлять только currency/XP-слоты — card-слоты
  (`ranked_pack_cards`) можно было наполнить только напрямую через SQL, хотя
  `open_ranked_pack()` их полностью поддерживал. Добавлена кнопка "🃏 Добавить карту
  в пул" → `admin_ranked_pack_slot_card_start/apply` (раздел 13) — закрыто до отчёта,
  не оставлено на будущее.

## 16. Тесты

`tests/test_ranked.py` (16 сценариев, сервисный слой) — покрывает все 7 пунктов из
раздела TESTING ТЗ:
1. Игрок ниже AHL не допускается в Ranked (понятная ошибка `LEAGUE_TOO_LOW`) + игрок
   на AHL и выше допускается.
2. Ranked использует лимит 54M, а не лиговый (два теста: разрешено под лимитом,
   заблокировано над лимитом).
3. Обычный режим не ограничен зарплатой (quick match и matchmaking — оба с составом,
   который заблокировал бы старую лиговую проверку).
4. Рамка применяется ровно к одной карте (привязка/переприкрепление "на лету" без
   отдельного анбинда, привязка второй рамки к той же карте вытесняет первую,
   попытка привязать не принадлежащий предмет отклоняется).
5. Апгрейд Gold → Platinum: ретроактивная выдача (при XP=300/уровень=4 выдаются
   ровно 3 награды уровней 1/2/3, уровень 5 корректно НЕ выдаётся), Platinum
   заблокирован без апгрейда.
6. XP начисляется за матч + бонус за победу + бонус за переход в новый дивизион
   (этот тест поймал баг №2 ниже).
7. Длительность сезона — 56 дней; завершение сезона архивирует топ-25, не удаляет
   `ranked_player_stats`, новый сезон стартует с 0 очков для новых игроков.

Плюс регрессия: полный матч не трогает `users.rating_points`/`users.league`
(обычную лестницу); открытие Ranked-пака выдаёт настроенные слотами награды.

`tests/test_ranked_handlers_smoke.py` (11 сценариев, реальные aiogram-объекты — тот же
паттерн, что и `test_war2_handlers_smoke.py`: настоящие `User`/`Chat`/`Message`/
`CallbackQuery`, подмена только сетевых методов на no-op, вызов реальных функций-
хендлеров напрямую): главный экран (с профилем/без), блокировка игры ниже AHL, полный
матч через хендлер, косметика+рамка через хендлеры, открытие пака через хендлер,
Pass-флоу (claim/покупка Gold/апгрейд до Platinum — всё через реальные хендлеры),
админ-экраны (главный/сезон/редактирование лиг), паки (добавление currency-слота),
создание пропуска + добавление награды, создание косметики через FSM.

## 17. Баги, найденные тестами (не пользователем)

Все правки в этом разделе — самостоятельно найдены и исправлены во время разработки
(тестами или ревью кода до запуска тестов), пользователь не сообщал ни об одной из
них:

1. **`ranked_league_rewards.pack_id` изначально указывал не на ту таблицу.** По
   аналогии с `ranked_pass_rewards.pack_id` (который правильно ссылается на общий
   `packs`) была скопирована та же ссылка `REFERENCES packs(id)`, хотя награды по
   лигам должны выдавать тематический, по дивизиону, `ranked_packs`. Найдено
   самостоятельным ревью схемы (не тестом) до первого запуска. Исправлено в
   `schema.py` и в `_grant_league_reward()`'s pack-ветке (теперь пишет в
   `user_ranked_packs`, не в `user_packs`).
2. **Баг определения `league_up`** (найден тестом `test_ranked_xp_division_up_bonus`):
   "дивизион до матча" изначально читался из закэшированной колонки
   `ranked_player_stats.ranked_league_id`, которая может быть `NULL`, если строка
   статистики была создана НЕ матчем (например, начислением XP через Ranked Pack до
   первого матча игрока) — сравнение с `NULL` молча гасило бонус "дошёл до нового
   дивизиона" даже при реальном переходе (тест зафиксировал `rank_points=308`,
   пересекающий порог Silver=300, но `league_up=False`). Исправлено: "дивизион до"
   теперь ВСЕГДА пересчитывается заново из `current_points` тем же прямым SQL-
   запросом, что и "дивизион после", в той же транзакции/соединении — колонка-кэш
   для этого сравнения больше не используется.
3. **Вложенные соединения внутри уже открытой транзакции** (найдено ревью кода):
   `play_ranked_match()`'s транзакционный блок изначально вызывал `await
   get_ranked_stats(...)`/`await compute_ranked_division(...)`, каждая из которых
   открывает СВОЁ соединение, находясь уже внутри открытой `BEGIN IMMEDIATE`-
   транзакции на другом соединении — расточительно и потенциальный источник
   путаницы (хоть и не жёсткий баг на этой WAL-конфигурации SQLite). Исправлено:
   эквивалентный raw SQL выполняется напрямую на уже открытом `connection` по всей
   транзакционной секции.
4. **Пробел в админ-UI Ranked Packs** (найдено самостоятельным ревью сразу после
   первой сборки админки, закрыто до отчёта) — см. раздел 15, последний пункт.

## 18. Регресс — проверено

- Полный существующий набор pytest (183 теста на момент реализации, из них 27 новых
  для Ranked: 16 сервисных + 11 хендлерных) зелёный после схемы/сида/роутинга/прав.
- `setup_routers()` собирается без ошибок с новыми роутерами (`ranked`/`admin_ranked`).
- `render_lineup_image()`/`war2_cosmetics.py`/старая CLAN WAR 2.0-косметика — не
  затронуты расширением CHECK (публичные сигнатуры функций не менялись, только
  список допустимых значений `type` расширен).
- Существующие паки/коллекции/Hockey Pass/`admin_cards.py`/`admin_permissions.py` —
  только добавления, ни одна существующая строка кода не изменена (кроме самого
  `admin_permissions.py`, где добавлены новые константы/записи).
- **Известный, не связанный с Ranked изменениями flake**: при прогоне ПОЛНОГО набора
  тестов `tests/test_stronghold_endless.py::test_endless_weekly_ft_cap_stops_new_ft`
  один раз упал, но стабильно проходит и в изоляции (сам по себе), и в рамках своего
  файла целиком — типичный симптом межтестовой зависимости от порядка выполнения где-
  то в THE STRONGHOLD Endless-тестах, не имеющей отношения к Ranked (код `Ranked` не
  импортирует и не использует ничего из `stronghold_endless`). Не расследовано глубже
  в рамках этой задачи — рекомендация: если повторится, смотреть на общее состояние
  `game_settings`/системного времени между тестами THE STRONGHOLD Endless.

## 19. Файлы

**Новые**: `app/services/ranked_common.py`, `ranked_seed.py`, `ranked_core.py`,
`ranked_cosmetics.py`, `ranked_packs.py`, `ranked_pass.py`; `app/handlers/ranked.py`,
`admin_ranked.py`; `app/states/admin_ranked.py`; `tests/test_ranked.py` (16 тестов),
`tests/test_ranked_handlers_smoke.py` (11 тестов); этот файл.

**Изменены (только добавления, кроме указанного расширения CHECK)**:
`app/database/schema.py` (15 новых таблиц + 4 записи `DEFAULT_GAME_SETTINGS` + CHECK
у `war2_cosmetic_items.type` расширен с 3 до 6 значений), `app/database/db.py`
(`ensure_column(match_queue, mode)`, `migrate_cosmetic_catalog_shared_types()`, вызов
`seed_ranked_content()`), `app/services/salary.py` (`RANKED_SALARY_CAP`),
`app/services/matches.py` (удалены 2 блока проверки зарплатного лимита, `match_queue`
запросы получили `mode = 'normal'`), `app/services/war2_cosmetics.py` (docstring +
`COSMETIC_TYPES` расширен), `app/services/admin_permissions.py` (`PERMISSION_RANKED`
+ роль + callback-префикс), `app/handlers/__init__.py` (регистрация роутеров),
`app/keyboards/reply.py` (кнопка входа "🏆 Ranked Mode").
