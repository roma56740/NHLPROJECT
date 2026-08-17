"""Регрессия единого фото-меню V10.3."""

from pathlib import Path

from app.keyboards.main_menu import (
    ADMIN_HOME_BUTTONS,
    USER_HOME_BUTTONS,
    build_admin_home_keyboard,
    build_user_home_keyboard,
)


def _flat(rows):
    return [button for row in rows for button in row]


def test_user_home_has_exactly_twelve_frequent_actions():
    buttons = _flat(USER_HOME_BUTTONS)
    assert len(buttons) == 12
    labels = [label for label, _ in buttons]
    assert labels == [
        "🏒 Играть",
        "🧩 Состав",
        "🃏 Карты",
        "🎁 Паки",
        "🏆 Ranked",
        "🏰 Stronghold",
        "⚔️ Clan War",
        "🕶 Чёрный рынок",
        "🛒 Магазин",
        "🎨 Косметика",
        "🎯 Прогресс",
        "☰ Ещё",
    ]
    assert all(callback.startswith("menu:") for _, callback in buttons)


def test_admin_home_has_exactly_twelve_quick_actions():
    buttons = _flat(ADMIN_HOME_BUTTONS)
    assert len(buttons) == 12
    labels = [label for label, _ in buttons]
    assert "🃏 Карточки" in labels
    assert "👥 Пользователи" in labels
    assert "🏆 Ranked" in labels
    assert "🏰 Stronghold" in labels
    assert "⚔️ Clan War" in labels
    assert "🛠 Техперерыв" in labels
    assert "📥 Массовая загрузка" in labels
    assert "☰ Все разделы" in labels


def test_main_keyboards_are_inline_not_reply_keyboards():
    user_keyboard = build_user_home_keyboard()
    admin_keyboard = build_admin_home_keyboard(None)
    assert hasattr(user_keyboard, "inline_keyboard")
    assert hasattr(admin_keyboard, "inline_keyboard")
    assert not hasattr(user_keyboard, "keyboard")
    assert not hasattr(admin_keyboard, "keyboard")


def test_start_and_menu_do_not_attach_legacy_reply_keyboard():
    root = Path(__file__).resolve().parents[1]
    start_text = (root / "app/handlers/start.py").read_text(encoding="utf-8")
    menu_text = (root / "app/handlers/menu.py").read_text(encoding="utf-8")
    assert "build_user_main_keyboard" not in start_text
    assert "build_admin_main_keyboard" not in start_text
    assert "answer_photo" in menu_text
    assert "ReplyKeyboardRemove" in menu_text


def test_open_dispatch_covers_all_twelve_user_buttons():
    root = Path(__file__).resolve().parents[1]
    navigation_text = (root / "app/handlers/navigation.py").read_text(encoding="utf-8")
    for key in {
        "matches",
        "lineup",
        "cards",
        "packs",
        "ranked",
        "stronghold",
        "war2",
        "black_market",
        "shop",
        "cosmetics",
    }:
        assert f'"{key}":' in navigation_text
