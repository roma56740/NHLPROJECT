from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.services.miniapp_runtime import get_miniapp_url

CONTACT_URL = "https://t.me/teyld"


def build_miniapp_keyboard() -> InlineKeyboardMarkup:
    url = get_miniapp_url()
    if url:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть Nexcore", web_app=WebAppInfo(url=url))],
                [InlineKeyboardButton(text="Поддержка / покупка Energy", url=CONTACT_URL)],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Покупка Energy / поддержка @teyld", url=CONTACT_URL)]
        ]
    )
