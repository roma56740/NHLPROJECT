from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from app.handlers.menu import send_home_photo
from app.services.users import register_or_update_player
from app.services.creator_tournaments import (
    get_tournament_by_invite_token,
    is_tournament_participant,
    parse_invite_payload,
    register as register_creator_tournament,
)


router = Router()


async def delete_start_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def send_start_screen(message: Message, telegram_user: User, delete_trigger: bool = False) -> None:
    # Регистрация/обновление профиля остаётся прежней; меняется только навигация:
    # вместо нижней ReplyKeyboard отправляется одна фотография с 12 inline-кнопками.
    await register_or_update_player(telegram_user)

    if delete_trigger:
        await delete_start_message(message)

    await send_home_photo(message, telegram_user.id, remove_reply_keyboard=True)


def _start_payload(message: Message) -> str | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else None


def _creator_invite_text(meta: dict, join_status: str) -> str:
    status = str(meta.get("status") or "registration")
    status_label = {
        "registration": "🟢 Регистрация открыта",
        "active": "🟡 Турнир уже идёт",
        "completed": "✅ Турнир завершён",
    }.get(status, status)
    return (
        f"<b>🏆 {escape(str(meta.get('title') or 'Турнир'), quote=False)}</b>\n\n"
        f"{escape(str(meta.get('description') or ''), quote=False)}\n\n"
        f"👤 Создатель: <b>{escape(str(meta.get('creator_nickname') or 'Creator'), quote=False)}</b>\n"
        f"👥 Участники: <b>{int(meta.get('participants_count') or 0)}/{int(meta.get('capacity') or 0)}</b>\n"
        f"⏱ Время на матч: <b>{int(meta.get('round_duration_minutes') or 0)} мин.</b>\n"
        f"{status_label}\n\n{join_status}"
    )


async def handle_start_payload(message: Message, telegram_user: User, payload: str | None) -> bool:
    invite_token = parse_invite_payload(payload)
    if not invite_token:
        return False
    profile = await register_or_update_player(telegram_user)
    meta = await get_tournament_by_invite_token(invite_token)
    if not meta:
        await message.answer("❌ Ссылка на турнир недействительна или была отключена.")
        return True
    tid = int(meta["id"])
    already = await is_tournament_participant(tid, profile.id)
    if already:
        join_status = "✅ Ты уже зарегистрирован в этом турнире."
    else:
        ok, msg, started = await register_creator_tournament(tid, profile.id)
        join_status = ("✅ " if ok else "❌ ") + msg
        if ok and started:
            join_status += "\n🏒 Турнир заполнен и автоматически запущен."
    refreshed = await get_tournament_by_invite_token(invite_token)
    if refreshed:
        meta = refreshed
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Открыть сетку", callback_data=f"ct:view:{tid}")]])
    await message.answer(_creator_invite_text(meta, join_status), reply_markup=kb)
    return True


@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    payload = _start_payload(message)
    if payload:
        await delete_start_message(message)
        if await handle_start_payload(message, message.from_user, payload):
            return
    await send_start_screen(message, message.from_user, delete_trigger=not bool(payload))
