from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app.services.settings import get_bool_setting, get_setting


SUBSCRIPTION_CHECK_CALLBACK = "subscription:check"
DEFAULT_START_BANNER_PATH = "assets/visual/start_banner.jpeg"
ACTIVE_MEMBER_STATUSES = {"creator", "administrator", "member"}


@dataclass(frozen=True)
class SubscriptionSettings:
    enabled: bool
    channel_id: str
    channel_url: str
    start_banner_path: str


def _strip_tme_prefix(value: str) -> str:
    value = value.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if value.startswith(prefix):
            return value.removeprefix(prefix).strip("/")
    return value


def normalize_channel_id(value: str) -> str:
    """Return a value that Telegram can use in get_chat_member."""

    value = (value or "").strip()
    if not value:
        return ""

    stripped = _strip_tme_prefix(value)

    # Invite links cannot be used as chat_id for get_chat_member.
    if stripped.startswith("+") or stripped.startswith("joinchat/"):
        return ""

    if stripped.startswith("@"):
        return stripped

    if stripped.startswith("-100") or stripped.lstrip("-").isdigit():
        return stripped

    return f"@{stripped}"


def build_channel_url(channel_id: str, explicit_url: str = "") -> str:
    explicit_url = (explicit_url or "").strip()
    if explicit_url:
        return explicit_url

    raw = (channel_id or "").strip()
    if not raw:
        return ""

    stripped = _strip_tme_prefix(raw)
    if stripped.startswith("+") or stripped.startswith("joinchat/"):
        return raw if raw.startswith("http") else f"https://t.me/{stripped}"

    if stripped.startswith("@"):
        stripped = stripped[1:]

    if stripped.startswith("-100") or stripped.lstrip("-").isdigit():
        return ""

    return f"https://t.me/{stripped}"


async def get_subscription_settings() -> SubscriptionSettings:
    enabled = await get_bool_setting("subscription_required_enabled", default=False)
    channel_id = await get_setting("subscription_channel_id", "")
    channel_url = await get_setting("subscription_channel_url", "")
    start_banner_path = await get_setting("start_banner_path", DEFAULT_START_BANNER_PATH)
    return SubscriptionSettings(
        enabled=enabled,
        channel_id=channel_id.strip(),
        channel_url=channel_url.strip(),
        start_banner_path=start_banner_path.strip() or DEFAULT_START_BANNER_PATH,
    )


async def is_subscription_gate_enabled() -> bool:
    settings = await get_subscription_settings()
    return settings.enabled and bool(normalize_channel_id(settings.channel_id))


async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    settings = await get_subscription_settings()
    if not settings.enabled:
        return True

    chat_id = normalize_channel_id(settings.channel_id)
    if not chat_id:
        return False

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False

    status = str(getattr(member, "status", "")).lower()
    if status in ACTIVE_MEMBER_STATUSES:
        return True

    if status == "restricted":
        return bool(getattr(member, "is_member", False))

    return False


def build_subscription_keyboard(settings: SubscriptionSettings) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    channel_url = build_channel_url(settings.channel_id, settings.channel_url)

    if channel_url:
        rows.append([InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_url)])

    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data=SUBSCRIPTION_CHECK_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_subscription_text(settings: SubscriptionSettings) -> str:
    channel_line = ""
    channel_id = normalize_channel_id(settings.channel_id)
    if channel_id:
        channel_line = f"\n\nКанал: <b>{channel_id}</b>"

    return f"""
<b>🏒 Доступ к NHL Card Bot</b>

Чтобы пользоваться ботом, сначала подпишись на Telegram-канал лиги.{channel_line}

После подписки нажми кнопку <b>Проверить подписку</b>.
""".strip()


def get_start_banner_file(settings: SubscriptionSettings | None = None) -> FSInputFile | None:
    path_value = settings.start_banner_path if settings else DEFAULT_START_BANNER_PATH
    path = Path(path_value)
    if not path.exists():
        return None
    return FSInputFile(path)


def build_subscription_debug_note(settings: SubscriptionSettings) -> str:
    if not settings.channel_id:
        return "Канал подписки не указан."
    if not normalize_channel_id(settings.channel_id):
        return "Для проверки подписки укажи @username канала или числовой ID -100... . Invite-ссылка нужна только для кнопки."
    return "Бот должен быть администратором канала, иначе Telegram не даст проверить подписку."
