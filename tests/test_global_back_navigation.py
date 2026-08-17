from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import build_user_home_keyboard
from app.utils.inline_navigation import (
    AUTO_ADMIN_BULK_CALLBACK,
    AUTO_BACK_CALLBACK,
    add_auto_back_row,
    has_navigation_button,
    suppress_auto_back_button,
)


def _callbacks(markup: InlineKeyboardMarkup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_auto_back_is_added_to_keyboard_without_navigation() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Действие", callback_data="feature:action")]]
    )
    assert _callbacks(markup).count(AUTO_BACK_CALLBACK) == 1


def test_existing_back_is_not_duplicated() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Действие", callback_data="feature:action")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="feature:main")],
        ]
    )
    assert AUTO_BACK_CALLBACK not in _callbacks(markup)


def test_cancel_counts_as_navigation() -> None:
    rows = [[InlineKeyboardButton(text="❌ Отмена", callback_data="feature:cancel")]]
    assert has_navigation_button(rows)
    assert len(add_auto_back_row(rows)) == 1


def test_suppression_keeps_root_keyboard_unchanged() -> None:
    with suppress_auto_back_button():
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Раздел", callback_data="menu:open:test")]]
        )
    assert AUTO_BACK_CALLBACK not in _callbacks(markup)


def test_user_root_menu_has_exactly_twelve_buttons_without_auto_back() -> None:
    markup = build_user_home_keyboard()
    callbacks = _callbacks(markup)
    assert len(callbacks) == 12
    assert AUTO_BACK_CALLBACK not in callbacks


def test_admin_keyboard_gets_bulk_upload_button_automatically() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Админ-действие", callback_data="admin_cards:list:1")]]
    )
    assert _callbacks(markup).count(AUTO_ADMIN_BULK_CALLBACK) == 1


def test_user_keyboard_does_not_get_admin_bulk_button() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Действие", callback_data="feature:action")]]
    )
    assert AUTO_ADMIN_BULK_CALLBACK not in _callbacks(markup)
