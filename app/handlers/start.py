from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from app.keyboards.reply import build_admin_main_keyboard, build_user_main_keyboard
from app.services.currencies import format_currency_amount
from app.services.subscription import get_start_banner_file, get_subscription_settings
from app.services.users import PlayerProfile, register_or_update_player
from app.utils.users import is_admin


router = Router()


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
    status_line = "✅ Профиль создан. Добро пожаловать на лёд!" if profile.is_new else "✅ Главное меню открыто. Прогресс сохранён!"
    template = ADMIN_START_TEXT if is_user_admin else USER_START_TEXT

    return template.format(
        status_line=status_line,
        nickname=escape(profile.nickname, quote=False),
        league=escape(profile.league, quote=False),
        rating_points=profile.rating_points,
        hockey_pass_level=profile.hockey_pass_level,
        balances=build_balances_text(profile),
    )


async def send_start_screen(message: Message, telegram_user: User, delete_trigger: bool = False) -> None:
    profile = await register_or_update_player(telegram_user)
    is_user_admin = is_admin(telegram_user.id)

    text = build_start_text(profile, is_user_admin)
    keyboard = build_admin_main_keyboard(telegram_user.id) if is_user_admin else build_user_main_keyboard()

    if delete_trigger:
        await delete_start_message(message)

    subscription_settings = await get_subscription_settings()
    banner = get_start_banner_file(subscription_settings)

    if banner is not None:
        await message.answer_photo(
            photo=banner,
            caption=text,
            reply_markup=keyboard,
        )
        return

    await message.answer(
        text,
        reply_markup=keyboard,
    )


@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    await send_start_screen(message, message.from_user, delete_trigger=True)
