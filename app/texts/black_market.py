"""Текстовые константы BLACK MARKET (пользовательский и админ UI).

Вынесено из app/handlers/black_market.py по конвенции проекта (см. app/texts/stronghold.py).
"""

from __future__ import annotations

ERROR_MESSAGES: dict[str, str] = {
    "REQUEST_ID_REQUIRED": "Действие устарело, откройте экран заново.",
    "REQUEST_ID_CONFLICT": "Действие уже выполняется, попробуйте ещё раз.",
    "ITEM_NOT_FOUND": "Товар не найден.",
    "ITEM_NOT_OWNED": "Этот товар не принадлежит вашей витрине.",
    "ROTATION_EXPIRED": "Витрина устарела, откройте Чёрный рынок заново.",
    "ITEM_UNAVAILABLE": "Товар больше недоступен.",
    "OUT_OF_STOCK": "Товар распродан.",
    "PURCHASE_LIMIT_REACHED": "Лимит покупок этого товара исчерпан.",
    "INSUFFICIENT_CURRENCY": "Недостаточно средств для покупки.",
    "PURCHASE_FAILED": "Не удалось завершить покупку. Попробуйте ещё раз.",
    "INVALID_ITEM_CONFIGURATION": "Некорректная конфигурация товара, обратитесь к администрации.",
    "INVALID_ITEM_TYPE": "Неизвестный тип предмета.",
    "INVALID_RARITY": "Неизвестная редкость.",
    "NO_FIELDS_TO_UPDATE": "Нет полей для обновления.",
    "SETTINGS_NOT_FOUND": "Настройки Чёрного рынка не найдены.",
    "USER_NOT_FOUND": "Игрок не найден.",
    "SHOP_DISABLED": "Чёрный рынок временно закрыт администрацией.",
    "INVALID_PRICE_MODE": "Некорректный режим цены.",
    "PRICE_RANGE_INVALID": "Некорректный диапазон цены (min должен быть ≤ max, оба ≥ 0).",
    "RARITY_WEIGHTS_INVALID": "Некорректные веса редкости.",
    "INVALID_STOCK_MODE": "Некорректный режим стока.",
    "INVALID_SLOTS_COUNT": "Количество слотов должно быть положительным.",
    "IMAGE_UPLOAD_FAILED": "Не удалось загрузить изображение. Пришлите PNG/JPG/WEBP файлом или фото.",
}

STATUS_ICONS: dict[str, str] = {
    "AVAILABLE": "🟢",
    "SOLD_OUT": "🔴",
    "REMOVED": "⚫",
}

RARITY_ICONS: dict[str, str] = {
    "Common": "⚪",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "🟠",
    "Event": "🟢",
    "Icon": "🌟",
}

ITEM_TYPE_LABELS: dict[str, str] = {
    "currency": "Валюта",
    "pack": "Пак",
    "card": "Карта",
    "cosmetic": "Косметика",
}

ITEM_STATUS_LABELS: dict[str, str] = {
    "AVAILABLE": "В наличии",
    "SOLD_OUT": "Распродано",
    "REMOVED": "Убрано администрацией",
}


def error_text(code: str, fallback: str) -> str:
    return ERROR_MESSAGES.get(code, fallback)
