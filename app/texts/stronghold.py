"""Текстовые константы THE STRONGHOLD (пользовательский UI).

Вынесено из app/handlers/stronghold.py в соответствии с конвенцией проекта
(texts/keyboards отдельно от handlers, см. app/texts/quests.py и т.д.).
Динамическая сборка текста экрана (зависящая от данных сервисов) остаётся в
handlers/stronghold.py — здесь только статичные словари/подписи.
"""

from __future__ import annotations

STATUS_TITLES: dict[str, str] = {
    "DRAFT": "не запущено",
    "SCHEDULED": "скоро начнётся",
    "ACTIVE": "идёт",
    "GRACE_PERIOD": "Grace Period",
    "ARCHIVED": "завершено",
}

ERROR_MESSAGES: dict[str, str] = {
    "EVENT_NOT_ACTIVE": "Событие THE STRONGHOLD сейчас недоступно.",
    "EVENT_ARCHIVED": "Событие THE STRONGHOLD завершено.",
    "LINEUP_INCOMPLETE": "Заполните весь состав (все 6 слотов) перед началом матча.",
    "UPGRADE_GRACE_PERIOD_ENDED": "Grace Period завершён, апгрейды больше недоступны.",
    "CARD_NOT_FOUND": "Карта не найдена.",
    "CARD_NOT_OWNED": "Эта карта вам не принадлежит.",
    "CARD_NOT_IN_UPGRADE_CHAIN": "Эта карта не участвует в Upgrade Chain.",
    "CARD_ALREADY_MAX_LEVEL": "Карта уже достигла 99 OVR.",
    "INSUFFICIENT_COINS": "Недостаточно Coins.",
    "INSUFFICIENT_FORTRESS_TOKENS": "Недостаточно Fortress Tokens.",
    "CARD_IN_PENDING_TRADE": "Карта участвует в обмене.",
    "CARD_IN_ACTIVE_MATCH": "Сейчас идёт матч, дождитесь его завершения.",
    "CARD_LOCKED": "Карта временно заблокирована.",
    "SALARY_CAP_EXCEEDED": "Превышен зарплатный потолок THE STRONGHOLD (45 000 000).",
    "REQUEST_ID_CONFLICT": "Действие уже выполняется, попробуйте ещё раз.",
    "UPGRADE_ALREADY_PROCESSED": "Операция уже обрабатывается.",
    "MISSION_NOT_FOUND": "Задание не найдено.",
    "MISSION_NOT_ACTIVE": "Задания сейчас недоступны.",
    "MISSION_NOT_COMPLETED": "Задание ещё не выполнено.",
    "MISSION_ALREADY_CLAIMED": "Награда уже получена.",
    "SEASON_LEVEL_LOCKED": "Уровень ещё не открыт.",
    "SEASON_REWARD_ALREADY_CLAIMED": "Награда уже получена.",
    "PRODUCT_NOT_FOUND": "Товар не найден.",
    "PRODUCT_NOT_AVAILABLE": "Товар сейчас недоступен.",
    "PRODUCT_EXPIRED": "Срок действия товара истёк.",
    "PURCHASE_LIMIT_REACHED": "Лимит покупок исчерпан.",
    "INSUFFICIENT_CURRENCY": "Недостаточно средств.",
    "PURCHASE_ALREADY_PROCESSED": "Покупка уже обрабатывается.",
    "FORTRESS_LOCKED": "Крепость ещё заблокирована.",
    "FORTRESS_MATCH_LOCKED": "Этот матч ещё заблокирован.",
    "COLLECTION_CARD_REQUIRED": "В составе должна быть минимум одна карта коллекции THE STRONGHOLD.",
    "ENDLESS_SIEGE_LOCKED": "Endless Siege открывается после прохождения всех 15 Fortress.",
}

CURRENCY_ICONS: dict[str, str] = {"coins": "🪙", "fortress_token": "🛡"}

LEDGER_REASON_LABELS: dict[str, str] = {
    "upgrade_spend": "Апгрейд Heiskanen",
    "fortress_first_completion": "Первое прохождение Fortress",
    "fortress_repeat": "Повторное прохождение Fortress",
    "endless_siege_wave": "Волна Endless Siege",
    "mission_reward": "Награда за задание",
    "season_track_reward": "Награда Season Track",
    "store_purchase": "Покупка в магазине",
    "ft_conversion": "Конвертация FT → Coins",
    "admin_compensation": "Компенсация от администрации",
}

FORTRESS_STATUS_ICONS: dict[str, str] = {"LOCKED": "🔒", "AVAILABLE": "⚪", "IN_PROGRESS": "🟡", "COMPLETED": "✅"}
FORTRESS_MATCH_STATUS_ICONS: dict[str, str] = {"LOCKED": "🔒", "AVAILABLE": "⚪", "STARTED": "🟡", "WON": "✅", "LOST": "❌", "COMPLETED": "✅"}
MISSION_STATUS_ICONS: dict[str, str] = {"ACTIVE": "🟡", "COMPLETED": "✅", "CLAIMED": "☑️"}
SEASON_LEVEL_STATUS_ICONS: dict[str, str] = {"LOCKED": "🔒", "AVAILABLE": "🎁", "CLAIMED": "✅"}


def error_text(code: str, fallback: str) -> str:
    return ERROR_MESSAGES.get(code, fallback)
