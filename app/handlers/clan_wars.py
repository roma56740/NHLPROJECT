from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.clan_wars import build_arena_view_keyboard, build_wars_arenas_keyboard
from app.services.clan_wars import declare_attack, get_arena, get_arenas
from app.services.community import get_user_id_by_telegram_id
from app.texts.clan_wars import WARS_MAIN_TEXT, WARS_NO_ARENAS_TEXT, build_arena_profile_text

from app.database.db import get_connection


router = Router()


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


def get_viewer_clan_context(telegram_id: int) -> tuple[int | None, int | None, str | None]:
    """Возвращает (user_id, clan_id, role) для зрителя."""
    with get_connection() as connection:
        user_row = connection.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if user_row is None:
            return None, None, None
        member = connection.execute(
            "SELECT clan_id, role FROM clan_members WHERE user_id = ?",
            (int(user_row["id"]),),
        ).fetchone()
        if member is None:
            return int(user_row["id"]), None, None
        return int(user_row["id"]), int(member["clan_id"]), member["role"]


@router.callback_query(F.data == "wars:main")
async def wars_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    arenas = await get_arenas()
    if not arenas:
        await edit_or_send(callback, WARS_NO_ARENAS_TEXT, reply_markup=build_wars_arenas_keyboard([]))
        await callback.answer()
        return
    await edit_or_send(callback, WARS_MAIN_TEXT, reply_markup=build_wars_arenas_keyboard(arenas))
    await callback.answer()


@router.callback_query(F.data.startswith("wars:arena:"))
async def wars_arena_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    arena_id = int(raw_id) if raw_id.isdigit() else 0
    arena = await get_arena(arena_id)
    if arena is None or not arena.active:
        await callback.answer("Арена недоступна", show_alert=True)
        return

    user_id, clan_id, role = get_viewer_clan_context(callback.from_user.id)
    can_attack = (
        clan_id is not None
        and role in ("leader", "officer")
        and arena.holder_clan_id != clan_id
        and not any(attack.clan_id == clan_id for attack in arena.attacks)
    )

    await edit_or_send(
        callback,
        build_arena_profile_text(arena, viewer_clan_id=clan_id),
        reply_markup=build_arena_view_keyboard(arena, can_attack=can_attack),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wars:attack:"))
async def wars_attack(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    raw_id = callback.data.split(":")[-1] if callback.data else ""
    arena_id = int(raw_id) if raw_id.isdigit() else 0

    user_id = get_user_id_by_telegram_id(callback.from_user.id)
    if user_id is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return

    result = await declare_attack(user_id, arena_id)

    if result.ok:
        arena = await get_arena(arena_id)
        _, clan_id, _ = get_viewer_clan_context(callback.from_user.id)

        # Уведомляем участников клана о начале атаки.
        if arena is not None and clan_id is not None:
            with get_connection() as connection:
                members = connection.execute(
                    """
                    SELECT users.telegram_id
                    FROM clan_members
                    JOIN users ON users.id = clan_members.user_id
                    WHERE clan_members.clan_id = ? AND users.is_banned = 0 AND users.telegram_id != ?
                    """,
                    (clan_id, callback.from_user.id),
                ).fetchall()
            for member in members:
                try:
                    await callback.bot.send_message(
                        chat_id=int(member["telegram_id"]),
                        text=(
                            f"⚔️ <b>Клан начал атаку!</b>\n\n"
                            f"Ваш клан атакует арену <b>{escape(arena.name, quote=False)}</b>. "
                            f"Каждая твоя победа в матче — +1 очко атаки. Вперёд, на лёд!"
                        ),
                    )
                except Exception:
                    pass

    arena = await get_arena(arena_id)
    if arena is not None:
        _, clan_id, role = get_viewer_clan_context(callback.from_user.id)
        can_attack = (
            clan_id is not None
            and role in ("leader", "officer")
            and arena.holder_clan_id != clan_id
            and not any(attack.clan_id == clan_id for attack in arena.attacks)
        )
        await edit_or_send(
            callback,
            build_arena_profile_text(arena, viewer_clan_id=clan_id),
            reply_markup=build_arena_view_keyboard(arena, can_attack=can_attack),
        )

    await callback.answer(result.title, show_alert=not result.ok)
