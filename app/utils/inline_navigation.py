"""Глобальная страховка навигации для inline-клавиатур.

Большая часть проекта исторически создаёт клавиатуры непосредственно через
``InlineKeyboardMarkup``. Из-за этого отдельные экраны могли остаться без кнопки
возврата, и пользователю приходилось повторно вводить ``/start``.

Модуль один раз расширяет конструктор ``InlineKeyboardMarkup``: если в разметке
нет явной кнопки возврата/отмены, внизу автоматически добавляется универсальная
кнопка ``⬅️ Назад``. Она возвращает обычного игрока в пользовательское главное
меню, а администратора — в административный центр.

Это намеренно является UX-страховкой, а не заменой логических кнопок «назад» в
конкретных многоуровневых сценариях. Уже существующие кнопки не дублируются.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


AUTO_BACK_CALLBACK = "nav:auto_back"
AUTO_BACK_TEXT = "⬅️ Назад"
AUTO_ADMIN_BULK_CALLBACK = "admin_bulk:hub"
AUTO_ADMIN_BULK_TEXT = "📥 Массовая загрузка"

_suppress_auto_back: ContextVar[bool] = ContextVar("suppress_auto_inline_back", default=False)
_installed = False
_original_init: Any | None = None


# Достаточно широкая проверка, чтобы не добавлять вторую кнопку рядом с уже
# существующими «Назад», «Отмена», «Главное меню», переходом к родительскому
# экрану и другими явными выходами из текущего действия.
_NAVIGATION_TEXT_MARKERS = (
    "назад",
    "главное меню",
    "быстрое меню",
    "в меню",
    "к меню",
    "в админ-панель",
    "к админ-панели",
    "к профилю",
    "к списку",
    "к наградам",
    "к настройкам",
    "отмена",
    "закрыть",
)

_NAVIGATION_CALLBACK_MARKERS = (
    "menu:main",
    AUTO_BACK_CALLBACK,
    ":back",
    ":cancel",
    ":main",
)


def _button_text(button: Any) -> str:
    return str(getattr(button, "text", "") or "").strip().lower()


def _button_callback(button: Any) -> str:
    return str(getattr(button, "callback_data", "") or "").strip().lower()


def has_navigation_button(rows: Iterable[Iterable[Any]]) -> bool:
    """Возвращает True, если клавиатура уже содержит понятный выход назад."""
    for row in rows:
        for button in row:
            text = _button_text(button)
            callback_data = _button_callback(button)
            if any(marker in text for marker in _NAVIGATION_TEXT_MARKERS):
                return True
            if callback_data in _NAVIGATION_CALLBACK_MARKERS:
                return True
            if callback_data.endswith(":main") or callback_data.endswith(":back") or callback_data.endswith(":cancel"):
                return True
    return False



_ADMIN_CALLBACK_PREFIXES = (
    "admin_", "admin:", "bm_admin:", "chemistry:", "starter_kit:",
    "season:", "broadcast:", "free_card:admin", "events:admin",
    "hockey_pass:admin", "daily_login:admin", "shop:admin", "packs:admin",
)


def has_admin_bulk_button(rows: Iterable[Iterable[Any]]) -> bool:
    return any(_button_callback(button) == AUTO_ADMIN_BULK_CALLBACK for row in rows for button in row)


def looks_like_admin_keyboard(rows: Iterable[Iterable[Any]]) -> bool:
    for row in rows:
        for button in row:
            callback_data = _button_callback(button)
            if callback_data.startswith(_ADMIN_CALLBACK_PREFIXES):
                return True
    return False


def add_auto_admin_bulk_row(rows: Iterable[Iterable[Any]]) -> list[list[Any]]:
    copied = [list(row) for row in rows]
    if looks_like_admin_keyboard(copied) and not has_admin_bulk_button(copied):
        copied.append([InlineKeyboardButton(text=AUTO_ADMIN_BULK_TEXT, callback_data=AUTO_ADMIN_BULK_CALLBACK)])
    return copied

def add_auto_back_row(rows: Iterable[Iterable[Any]]) -> list[list[Any]]:
    """Копирует строки и добавляет универсальную кнопку, когда выхода нет."""
    copied = [list(row) for row in rows]
    if _suppress_auto_back.get() or has_navigation_button(copied):
        return copied
    copied.append([InlineKeyboardButton(text=AUTO_BACK_TEXT, callback_data=AUTO_BACK_CALLBACK)])
    return copied


@contextmanager
def suppress_auto_back_button():
    """Отключает автодобавление для корневых меню, где кнопка назад бессмысленна."""
    token = _suppress_auto_back.set(True)
    try:
        yield
    finally:
        _suppress_auto_back.reset(token)


def install_global_inline_back_button() -> None:
    """Идемпотентно включает автодобавление кнопки для всего приложения."""
    global _installed, _original_init
    if _installed:
        return

    original_init = InlineKeyboardMarkup.__init__
    _original_init = original_init

    def patched_init(self: InlineKeyboardMarkup, *args: Any, **kwargs: Any) -> None:
        rows = kwargs.get("inline_keyboard")
        if rows is not None:
            rows = add_auto_admin_bulk_row(rows)
            kwargs["inline_keyboard"] = add_auto_back_row(rows)
        original_init(self, *args, **kwargs)

    InlineKeyboardMarkup.__init__ = patched_init  # type: ignore[method-assign]
    _installed = True


__all__ = [
    "AUTO_BACK_CALLBACK",
    "AUTO_BACK_TEXT",
    "AUTO_ADMIN_BULK_CALLBACK",
    "AUTO_ADMIN_BULK_TEXT",
    "add_auto_admin_bulk_row",
    "add_auto_back_row",
    "has_navigation_button",
    "install_global_inline_back_button",
    "suppress_auto_back_button",
]
