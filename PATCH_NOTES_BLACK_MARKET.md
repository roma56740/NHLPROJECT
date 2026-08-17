# PATCH NOTES — Black Market (Чёрный рынок): технический аудит и доработка

Дата: 2026-07-29
Область: полная персональная ежедневная ротация витрины Чёрного рынка (master pool общий, storefront — индивидуальный на каждого игрока).

---

## 1. Что уже было реализовано правильно (подтверждено аудитом)

- Персональная модель данных: 7 таблиц, из них `black_market_user_rotations`/`black_market_user_rotation_items` — per-user, остальные (`black_market_settings`, `black_market_rarity_weights`, `black_market_pool_items`) — общий master pool.
- Ленивая генерация витрины при первом открытии, без предварительного массового job'а.
- HMAC-SHA256 seed на `(user_id, business_date, rotation_version)`, локальный `random.Random`, никогда не задевает глобальный модуль `random`.
- Защита от гонки: `BEGIN IMMEDIATE` + partial unique index (`WHERE status='ACTIVE'`) + fallback на `IntegrityError`.
- Атомарная покупка: идемпотентность по `request_id`, проверка владения ротацией, guarded UPDATE для валюты и стока, полный rollback при любой ошибке.
- «Обновить всем» — только bump `global_rotation_version`, без массовой генерации.
- «Обновить игроку» — инвалидация (EXPIRED) + сохранение истории, а не удаление.
- Router-порядок: `black_market`/`admin_black_market` зарегистрированы раньше catch-all `creator_tournaments`, кнопка не перехватывается (проверено тестом `test_black_market_routers_registered_before_creator_tournaments_catchall`).
- Секрет HMAC никогда не логируется и не выводится в UI.

## 2. Проблемы, найденные аудитом

1. **Покупка в один клик без подтверждения** — в списке товаров клик сразу списывал деньги, не было экрана "подробности + подтвердить/отменить".
2. **Не было пагинации** и экрана детали товара с точным временем следующего обновления.
3. **Rarity/item-type dispatch была if/elif-цепочкой** в двух местах (`black_market_generation.py`, `black_market_store.py`) — нарушение явного требования "не должно быть одной цепочки if/elif".
4. **Нет валидации весов редкости** — можно было выставить веса не суммой 100%, либо все веса = 0.
5. **Нет fallback-логирования**, когда у выпавшей редкости нет предметов.
6. **`personal_purchase_limit` был всегда равен стоку** — не мог настраиваться отдельно.
7. **Нет полей "доступность по датам"** (`available_from`/`available_until`) у предметов пула.
8. **`allow_repeat_in_rotation` был только глобальным** переключателем, не мог настраиваться на уровне отдельного предмета.
9. **Не было `shop_enabled`** — нельзя было выключить магазин целиком.
10. **Не было экранов**: настройки ротации, история ротаций/покупок игрока, последние покупки (все игроки), toggle магазина.
11. **Не было мастера "Добавить предмет"** в админке — пул можно было наполнять только напрямую через SQL/скрипт.
12. **Превью товара не рендерилось** через существующий compositor (`app/services/renders.py`) — только хранился сырой `image_path`, показывался просто текстом/файлом.
13. **`BLACK_MARKET_SEED_SECRET` fallback на `bot_token`** был тихим — не логировался warning, не было явной deployment-инструкции для Railway.
14. **Не было фонового цикла**, который заметил бы смену business_date и разослал уведомление "ассортимент обновлён" без предварительной генерации всем.
15. **`refresh_one_user`/`refresh_everyone`** не запускали реальную отправку уведомлений (сервис уведомлений существовал, но нигде не вызывался).
16. **Не было индекса `(rotation_version, status)`** для админ-запросов.
17. Тесты не покрывали: fallback-редкости, пустой пул, репиты (per-item и global), детерминизм RANDOM_RANGE после принудительной регенерации, валидацию цен/весов, shop_enabled, порядок роутеров, полный FSM добавления товара.

## 3. Что было исправлено

### Схема и миграции
- Добавлены колонки (через `ensure_column`, идемпотентно, без потери данных):
  `black_market_settings.shop_enabled`, `black_market_settings.last_notified_business_date`,
  `black_market_pool_items.personal_purchase_limit`, `.available_from`, `.available_until`, `.allow_repeat_in_rotation`.
- Новый индекс `idx_bm_user_rotations_version_status (rotation_version, status)`.
- Новая миграция `0004_black_market_notification_baseline` — выставляет `last_notified_business_date` в сегодняшний день один раз, чтобы фоновый цикл уведомлений не разослал спам сразу после деплоя.

### Архитектура кода
- Новый модуль `app/services/black_market_items.py` — реестр адаптеров `ITEM_ADAPTERS: dict[item_type, ItemAdapter]` (currency/pack/card/cosmetic), каждый со своим `resolve_display`/`grant`. Убрана if/elif-цепочка из генерации и покупки.
- `black_market_generation.py`: фильтр по `available_from/available_until`, per-item `allow_repeat_in_rotation`, `personal_purchase_limit` из пула (fallback на сток, если 0), `logger.warning` при fallback между редкостями и при исчерпании всего пула.
- `black_market_admin.py`: строгая валидация цен (`RANDOM_RANGE`: min ≤ max, оба ≥ 0; `FIXED`: ≥ 0) и весов редкости (0..100 каждый, сумма активных строго 100, хотя бы одна активна — без float, целые числа), `set_shop_enabled`, `update_rotation_settings`, `list_user_rotation_history`, `list_user_purchase_history`, `list_recent_purchases`, хелперы выбора карт/паков/валют/косметики для мастера добавления.
- `app/services/renders.py`: `render_black_market_item_preview()` — переиспользует существующий compositor (`_paste_shadowed_card`, `_load_background`, `render_card_profile_image`) вместо нового движка; кэш по стабильному `cache_key`, `invalidate_black_market_preview()` вызывается при правке предмета пула.
- `app/services/black_market_notifications.py`: `black_market_notification_loop()` — фоновый цикл (регистрируется в `main.py`), замечает смену business_date и рассылает уведомление согласно `notification_target`; `notify_single_user()` для точечного уведомления после admin refresh одного игрока.
- `config.py`: `BLACK_MARKET_SEED_SECRET` — теперь при отсутствии переменной явно логируется `logger.warning(...)` с инструкцией задать её в Railway; сам секрет никогда не логируется.

### UX
- Пользовательский экран: список (пагинация по 4) → карточка товара (тип/редкость/цена/остаток/лимит/статус + фото-превью) → явное «✅ Купить» / «❌ Отмена» → результат. Показывается точное время следующего обновления ("Обновление в 00:00 UTC (через N ч M мин)").
- Админка: добавлены «⚙️ Настройки ротации», toggle «🟢/🔴 магазин», «📜 История ротаций», «🧾 История покупок» (по игроку и общая), «➕ Добавить предмет» — полный мастер (CARD с выбором по ID + preview, FRAME/BACKGROUND с выбором существующего ИЛИ загрузкой нового PNG/JPG/WEBP через тот же `war2_cosmetics.create_cosmetic_item`, PACK/CURRENCY из существующих списков) с настройкой rarity/selection_weight/price mode/currency/personal stock/personal limit/даты доступности/allow_repeat.

### Тесты
Добавлено 23 новых теста (35 → 58 в Black Market suite): shop_enabled блокирует листинг/покупку, доступность по датам, personal_purchase_limit независим от стока, allow_repeat_in_rotation (per-item и global), пустой master pool, fallback между редкостями + лог warning, детерминизм RANDOM_RANGE после принудительной регенерации, валидация цен и весов редкости, порядок роутеров, полный прогон FSM добавления CURRENCY-товара, smoke-тесты рендера превью (включая безопасный fallback на отсутствующий asset и кэширование).

## 4. Полный список изменённых файлов

**Новые файлы:**
- `app/services/black_market_common.py`
- `app/services/black_market_generation.py`
- `app/services/black_market_store.py`
- `app/services/black_market_admin.py`
- `app/services/black_market_items.py`
- `app/services/black_market_notifications.py`
- `app/middlewares/last_active.py`
- `app/keyboards/black_market.py`
- `app/texts/black_market.py`
- `app/handlers/black_market.py`
- `app/handlers/admin_black_market.py`
- `tests/test_black_market_generation.py`
- `tests/test_black_market_store.py`
- `tests/test_black_market_admin.py`
- `tests/test_black_market_notifications.py`
- `tests/test_black_market_audit_fixes.py`
- `tests/test_black_market_handlers_smoke.py`

**Изменённые файлы:**
- `app/database/schema.py`
- `app/database/db.py`
- `config.py`
- `app/services/admin_permissions.py`
- `app/services/renders.py`
- `app/keyboards/reply.py`
- `app/handlers/__init__.py`
- `main.py`
- `tests/conftest.py`

## 5. Таблицы и индексы

| Таблица | Назначение | Ключевые индексы/constraints |
|---|---|---|
| `black_market_settings` | Единственная строка (id=1): slots_count, stock_mode, allow_duplicate_slots, global_rotation_version, notification_target/active_days, shop_enabled, last_notified_business_date | PK id CHECK(id=1) |
| `black_market_rarity_weights` | Общие веса 6 редкостей (Common/Rare/Epic/Legendary/Event/Icon) | PK rarity |
| `black_market_pool_items` | Общий master pool: item_type, ссылки (currency_code/pack_id/card_id/cosmetic_item_id), rarity, price_mode/amount/min/max, stock/limit, available_from/until, allow_repeat_in_rotation, selection_weight, active | idx_bm_pool_items_active (active, rarity) |
| `black_market_user_rotations` | Персональная ротация: user_id, business_date, rotation_version, seed_hash, status, generation_reason | partial UNIQUE (user_id, business_date, rotation_version) WHERE status='ACTIVE'; idx_bm_user_rotations_user_date; idx_bm_user_rotations_version_status |
| `black_market_user_rotation_items` | Слоты витрины — снапшот на момент генерации (имя/цена/сток/лимит) | UNIQUE (user_rotation_id, slot_number); idx_bm_rotation_items_rotation |
| `black_market_purchases` | Лог покупок, идемпотентность | UNIQUE (user_id, request_id); idx_bm_purchases_user |
| `black_market_admin_audit` | Аудит всех админ-действий (before/after JSON) | idx_bm_admin_audit_created |

## 6. Генерация персональной витрины

1. `business_date` = календарный день UTC.
2. `seed = HMAC_SHA256(BLACK_MARKET_SEED_SECRET, "user_id:business_date:rotation_version")[:8] → int`.
3. `rng = random.Random(seed)` — локальный, детерминированный, никогда не глобальный `random`.
4. Для каждого слота: выбор редкости по весам → выбор предмета пула (валиден: active, в окне дат, ссылка существует) взвешенно по `selection_weight` → если пусто — fallback по всем редкостям с `logger.warning` → цена (FIXED или `rng.randint(min,max)`) → сток (fixed или `rng.randint(min,max)`) → snapshot в `black_market_user_rotation_items`.
5. Гонка: `BEGIN IMMEDIATE` + double-check + partial unique index + `IntegrityError` fallback → только одна ACTIVE-ротация на `(user_id, business_date, rotation_version)`.

## 7. Атомарная покупка

Одна транзакция (`BEGIN IMMEDIATE` → `COMMIT`/rollback при исключении):
идемпотентность по `request_id` → rotation принадлежит вызывающему → business_date/version актуальны → сток > 0 и лимит не исчерпан → guarded UPDATE валюты → выдача через `black_market_items.grant_item` (registry) → guarded UPDATE стока → запись в `black_market_purchases`. Любое исключение до `commit()` откатывает ВСЁ (валюту, выдачу, сток, запись) целиком — это гарантия sqlite3 `with connection:`, дополнительно проверено тестом `test_rollback_restores_stock_and_balance_on_grant_failure`.

## 8. Инструкция администратора

1. Открыть кнопку «🕶 Чёрный рынок» (видна только админам с `PERMISSION_BLACK_MARKET`).
2. **Добавить предмет**: тип (CARD/FRAME/BACKGROUND/PACK/CURRENCY) → для CARD — ID карты (+ preview), для FRAME/BACKGROUND — выбрать существующий или загрузить новый PNG/JPG/WEBP, для PACK/CURRENCY — выбрать из списка → редкость → валюта цены → режим цены (фиксированная/диапазон) → сток (число или диапазон) → личный лимит покупок → вес выбора → разрешить повторы в одной витрине? → ограничить по датам? → подтвердить.
3. **Веса редкости**: `Common:50,Rare:25,...` — сумма активных должна быть 100.
4. **Настройки ротации**: просмотр slots_count/stock_mode/allow_duplicate_slots + toggle «включить/выключить магазин».
5. **Найти игрока**: по Telegram ID / никнейму / username → просмотр текущей витрины, история ротаций, история покупок, кнопка «Обновить рынок этого игрока» (не удаляет историю, инвалидирует текущую и уведомляет игрока лично).
6. **Обновить рынок всем**: только бампает версию — никто не получает новую витрину мгновенно, только при следующем открытии.
7. **Аудит** / **Последние покупки** — просмотр журналов.

## 9. Инструкция пользователя

1. Нажать «🕶 Чёрный рынок».
2. Пролистать ассортимент (кнопки ⬅️/➡️), открыть товар — увидеть тип, редкость, цену, личный остаток, личный лимит, статус и фото-превью.
3. Нажать «✅ Купить» → подтверждение → списание и выдача награды сразу.
4. Ассортимент — твой личный, не меняется от чужих покупок, обновляется раз в сутки (00:00 UTC) — точное время до обновления видно на главном экране.

## 10. Результат pytest

См. отдельный раздел в финальном отчёте (полный прогон всего проекта).

## 11. Переменные окружения Railway

| Переменная | Обязательна | Назначение |
|---|---|---|
| `BLACK_MARKET_SEED_SECRET` | Настоятельно рекомендуется (иначе fallback на `BOT_TOKEN` с warning в логах) | Секрет HMAC для детерминированной персональной генерации витрины. Должен быть стабильным между деплоями — смена значения меняет генерацию всем игрокам сразу. |

Остальные переменные (`BOT_TOKEN`, `ADMIN_IDS`, `DATABASE_PATH`, `START_COINS`, `START_ENERGY`, `START_RANK_POINTS`) не менялись этим патчем.
