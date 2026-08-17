"""Регрессия возврата из списка пользовательских карточек."""

from pathlib import Path


def test_cards_list_back_returns_to_photo_main_menu() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/keyboards/user_cards.py").read_text(encoding="utf-8")
    assert (
        'keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")])'
        in source
    )


def test_card_profile_back_still_returns_to_cards_page() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/keyboards/user_cards.py").read_text(encoding="utf-8")
    assert 'callback_data=f"user_cards:list:{page}"' in source
