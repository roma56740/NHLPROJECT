# THE STRONGHOLD — внутренний API-контракт

Функциональный эквивалент REST/OpenAPI-спеки для этого проекта: единой HTTP-границы
нет (Telegram-бот, не веб-сервис — см. THE_STRONGHOLD_SPEC.md, раздел 0), поэтому
контракт — это публичные async-функции сервисного слоя `app/services/stronghold_*.py`.
Каждая функция ниже — прямой эквивалент "эндпоинта": типизированные параметры вместо
request body, `@dataclass(frozen=True)` вместо response schema, `StrongholdError` вместо
HTTP-ошибки.

## Конверты запроса/ответа

Явных JSON-конвертов `{"success": ..., "data": ...}` нет — их роль играют:

- **Успех** → возвращаемый dataclass (`UpgradeResult`, `FortressMatchPlayResult`, ...).
- **Ошибка** → исключение `StrongholdError(code, message)` — `code` из фиксированного
  списка (см. ниже), `message` — человекочитаемый текст для показа пользователю.
- **serverTime** → `stronghold_common.utc_now()` — вызывается сервисами напрямую, не
  передаётся клиентом; все проверки времени (Grace Period, недельные лимиты) идут по
  серверным часам.
- **configurationVersion** → `StrongholdEventState.config_version` (поле события).
- **correlationId** → структурированные логи (`stronghold_common.log_stronghold_operation`)
  используют `user_id` + `action` + время как идентифицирующий контекст вместо отдельного
  correlationId (в Telegram-боте нет сквозного request-id уровня HTTP — ближайший аналог,
  `callback_query.id`, уникален на каждый тап и не подходит для группировки повторов,
  поэтому для идемпотентности используется явный `request_id`, который выбирает вызывающая
  сторона — см. ниже).

## Авторизация

`user_id` **никогда** не передаётся клиентом в теле "запроса" — вызывающий код
(`app/handlers/stronghold.py`) получает его из `callback.from_user.id` /
`message.from_user.id` (Telegram гарантирует подлинность отправителя на уровне протокола,
это эквивалент проверенного access token) → `get_player_profile_by_telegram_id()` →
`profile.id`. Ни одна функция сервисного слоя не принимает "чужой" `user_id` из
пользовательского ввода. Admin-функции дополнительно проверяются
`has_admin_permission(admin_id, PERMISSION_STRONGHOLD)` на уровне хендлера
(`app/handlers/admin_stronghold.py:_require_permission`) до вызова сервиса.

## Идемпотентность

Операции, списывающие валюту, принимают `request_id: str` (генерируется вызывающей
стороной один раз на "экран/попытку", не на каждый тап — см. `app/handlers/stronghold.py`,
FSM-хранение `numeric_edit`/`stg_upgrade_request_id` в состоянии). Повтор с тем же
`request_id` возвращает сохранённый успешный результат (`replayed=True`), не списывая
повторно. Конфликт `request_id` с другим объектом операции → `REQUEST_ID_CONFLICT`.

## Единый список кодов ошибок

```
EVENT_NOT_ACTIVE, EVENT_ARCHIVED, UPGRADE_GRACE_PERIOD_ENDED,
CARD_NOT_FOUND, CARD_NOT_OWNED, CARD_NOT_IN_UPGRADE_CHAIN, CARD_ALREADY_MAX_LEVEL,
UPGRADE_STEP_NOT_FOUND, INSUFFICIENT_COINS, INSUFFICIENT_FORTRESS_TOKENS,
CARD_LISTED_ON_MARKET, CARD_IN_PENDING_TRADE, CARD_IN_ACTIVE_MATCH, CARD_LOCKED,
SALARY_CAP_EXCEEDED, REQUEST_ID_CONFLICT, UPGRADE_ALREADY_PROCESSED,
INTERNAL_TRANSACTION_ERROR, MISSION_NOT_FOUND, MISSION_NOT_ACTIVE,
MISSION_NOT_COMPLETED, MISSION_ALREADY_CLAIMED, MISSION_EXPIRED, SEASON_LEVEL_LOCKED,
SEASON_REWARD_ALREADY_CLAIMED, PRODUCT_NOT_FOUND, PRODUCT_NOT_AVAILABLE,
PRODUCT_EXPIRED, PURCHASE_LIMIT_REACHED, INSUFFICIENT_CURRENCY,
INVALID_PRODUCT_CONFIGURATION, PURCHASE_ALREADY_PROCESSED, FORTRESS_LOCKED,
FORTRESS_MATCH_LOCKED, MATCH_RESULT_ALREADY_SUBMITTED, COLLECTION_CARD_REQUIRED,
ENDLESS_SIEGE_LOCKED
```

Определены как строковые константы прямо в местах `raise StrongholdError(...)` (не
enum — сознательно, чтобы не плодить ещё один слой отображения; полный grep:
`grep -rn "StrongholdError(\"" app/services/`). Хендлеры сопоставляют код с текстом через
`ERROR_MESSAGES`/`ERROR_MESSAGES` в `app/handlers/stronghold.py`.

## "Эндпоинты" (публичные функции)

### Event / Wallet

| Функция | Модуль | Параметры | Возврат |
|---|---|---|---|
| `get_active_event()` | `stronghold_common` | — | `StrongholdEventState \| None` |
| `get_wallet(user_id)` | `stronghold_wallet` | `user_id: int` | `WalletInfo` |
| `get_currency_history(user_id, event_id, page, per_page=10)` | `stronghold_wallet` | — | `LedgerPage` |

### Upgrade Chain

| Функция | Параметры | Возврат | Ошибки |
|---|---|---|---|
| `preview_upgrade(user_id, user_card_id)` | — | `UpgradePreview` (не списывает) | `CARD_NOT_FOUND`, `CARD_NOT_OWNED`, `CARD_NOT_IN_UPGRADE_CHAIN`, `CARD_ALREADY_MAX_LEVEL` (raise); остальное — `blocking_reason` в ответе |
| `confirm_upgrade(user_id, user_card_id, request_id)` | — | `UpgradeResult` | весь список Upgrade-related кодов выше |
| `ensure_starter_card(user_id)` | — | `None` (побочный эффект) | — (best-effort, no-op вне ACTIVE/GRACE_PERIOD) |

### Fortress

| Функция | Параметры | Возврат |
|---|---|---|
| `list_fortresses(user_id)` | — | `list[FortressInfo]` |
| `get_fortress(user_id, fortress_id)` | — | `FortressInfo \| None` (с матчами) |
| `play_fortress_match(telegram_id, user_id, fortress_match_id)` | — | `FortressMatchPlayResult` |

### Endless Siege

| Функция | Параметры | Возврат |
|---|---|---|
| `get_status(user_id)` | — | `EndlessStatus` |
| `play_wave(telegram_id, user_id)` | — | `EndlessWaveResult` |
| `get_leaderboard(page=1, per_page=10, user_id=None)` | — | `LeaderboardPage` |

### Missions

| Функция | Параметры | Возврат |
|---|---|---|
| `list_missions(user_id, mission_type=None)` | — | `list[MissionInfo]` |
| `claim_mission(user_id, mission_id)` | — | `MissionClaimResult` |
| `apply_stronghold_progress(user_id, condition_type, amount=1)` | внутренний пост-хук, не вызывается напрямую из хендлеров | `None` |

### Season Track

| Функция | Параметры | Возврат |
|---|---|---|
| `get_track(user_id)` | — | `SeasonTrackInfo` |
| `claim_level(user_id, season_level_id)` | — | `SeasonClaimResult` |
| `add_event_xp(user_id, amount)` | внутренний пост-хук | `None` |

### Event Store

| Функция | Параметры | Возврат |
|---|---|---|
| `list_products(user_id, category=None)` | — | `list[StoreProductInfo]` |
| `purchase(user_id, product_id, request_id)` | — | `PurchaseResult` |

### Admin (требуют `PERMISSION_STRONGHOLD` на уровне хендлера)

| Функция | Модуль | Назначение |
|---|---|---|
| `validate_event_config(event_id)` | `stronghold_admin` | Проверка сумм/структуры перед публикацией |
| `schedule_event(...)` / `force_transition(...)` | `stronghold_admin` | Lifecycle |
| `grant_compensation(...)` | `stronghold_admin` | Одиночная компенсация, идемпотентна по `(admin_id, request_id)` |
| `list_audit_log(event_id, page)` | `stronghold_admin` | Аудит |
| `list_upgrade_steps` / `update_upgrade_step_costs` | `stronghold_admin_content` | Редактор Upgrade Chain |
| `list_fortresses_admin` / `update_fortress_reward` / `toggle_fortress_active` / `update_fortress_match_ovr` | `stronghold_admin_content` | Редактор Fortress |
| `list_missions_admin` / `create_mission` / `update_mission_rewards` / `toggle_mission_active` | `stronghold_admin_content` | Редактор Missions |
| `list_season_levels_admin` / `update_season_level` | `stronghold_admin_content` | Редактор Season Track |
| `list_store_products_admin` / `update_store_product_price` / `toggle_store_product_active` | `stronghold_admin_content` | Редактор Store |
| `get_analytics_summary(event_id)` | `stronghold_admin_content` | Аналитика |
| `reconcile_ledger_vs_balance(event_id)` | `stronghold_admin_content` | Анти-чит/целостность (см. QA-отчёт) |
| `mass_disable_store` / `mass_compensate` | `stronghold_admin_content` | Массовые операции |

### Health / Ops

| Функция | Модуль | Возврат |
|---|---|---|
| `get_health_status()` | `stronghold_health` | `HealthCheckResult` (см. также `scripts/stronghold_healthcheck.py`) |
| `convert_archived_event_balances(event_id, ft_conversion_rate)` | `stronghold_conversion` | Батч-конвертация FT→Coins, идемпотентна |

## Rate limiting / кэширование / пагинация

- **Rate limiting**: отдельного лимитера нет — естественным ограничителем выступает
  Telegram (пользователь физически не может тапать быстрее, чем UI успевает
  перерисовываться) + `match_guard.try_acquire_match_lock` для матчевых операций.
  Явный лимитер не добавлен, т.к. нагрузка одного Telegram-бота на SQLite несравнима с
  публичным REST API — при реальной необходимости следующий шаг: обёртка с
  token-bucket на `user_id` в `stronghold_common`.
- **Кэширование**: конфигурационные данные (Fortress/Missions/Season Track/Store)
  меняются редко — сейчас читаются каждый раз заново (простая корректная реализация).
  Баланс/приватные данные никогда не кэшируются намеренно.
- **Пагинация**: везде `page`/`per_page` с клампом на сервере
  (`min(max(page, 1), pages_count)`), см. `tests/test_stronghold_security.py::test_currency_history_pagination_clamped`.

## Пример потока (эквивалент smoke-flow из ТЗ)

См. `scripts/stronghold_smoke_test.py` — исполняемый эквивалент
`docs/api/the-stronghold.http`, вызывающий эти функции напрямую в том же порядке,
что описан в исходном ТЗ (открыть событие → кошелёк → preview → Upgrade → Fortress →
Missions → Store → healthcheck).
