from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

from app.keyboards.reply import build_admin_main_keyboard, build_user_main_keyboard
from app.services.currencies import format_currency_amount
from app.services.packs import ensure_starter_pack_for_user
from app.services.users import PlayerProfile, register_or_update_player
from app.utils.users import is_admin


router = Router()

LOGO_PATH = Path("Logo.png")


USER_START_TEXT = """
<b>🏒 NHL Card Bot</b>

{status_line}

👤 Игрок: <b>{nickname}</b>
🏆 Лига: <b>{league}</b>
⭐ Очки: <b>{rating_points}</b>
🎟 Hockey Pass: <b>{hockey_pass_level} уровень</b>

<b>Баланс</b>
{balances}

🃏 Собирай карточки игроков
🎁 Открывай паки и получай редкие находки
🧩 Собирай сильный состав
🏆 Побеждай в матчах и поднимайся в рейтинге

Выбери раздел ниже и начни путь к чемпионству.
""".strip()


ADMIN_START_TEXT = """
<b>🏒 NHL Card Bot — управление игрой</b>

{status_line}

👤 Профиль: <b>{nickname}</b>
🏆 Лига: <b>{league}</b>
⭐ Очки: <b>{rating_points}</b>

<b>Баланс</b>
{balances}

🃏 Карточки и коллекции
🎁 Паки и награды
🛒 Магазин и ротации
👥 Игроки и балансы
🎯 Задания и Hockey Pass
🏆 Лиги, события и рейтинг

Выбери нужный раздел ниже.
""".strip()


async def delete_start_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


def build_balances_text(profile: PlayerProfile) -> str:
    if not profile.balances:
        return "Пока пусто"

    return "\n".join(format_currency_amount(balance) for balance in profile.balances)


def build_start_text(profile: PlayerProfile, is_user_admin: bool) -> str:
    status_line = "✅ Профиль создан. Добро пожаловать на лёд!" if profile.is_new else "✅ Профиль готов. Рады видеть снова!"
    template = ADMIN_START_TEXT if is_user_admin else USER_START_TEXT

    return template.format(
        status_line=status_line,
        nickname=profile.nickname,
        league=profile.league,
        rating_points=profile.rating_points,
        hockey_pass_level=profile.hockey_pass_level,
        balances=build_balances_text(profile),
    )


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    if message.from_user is None:
        return

    profile = await register_or_update_player(message.from_user)
    await ensure_starter_pack_for_user(profile.id)
    is_user_admin = is_admin(message.from_user.id)

    text = build_start_text(profile, is_user_admin)
    keyboard = build_admin_main_keyboard() if is_user_admin else build_user_main_keyboard()

    await delete_start_message(message)

    if LOGO_PATH.exists():
        await message.answer_photo(
            photo=FSInputFile(LOGO_PATH),
            caption=text,
            reply_markup=keyboard,
        )
        return

    await message.answer(
        text,
        reply_markup=keyboard,
    )
