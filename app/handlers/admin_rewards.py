from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_rewards import build_admin_rewards_keyboard
from app.texts.admin_rewards import ADMIN_REWARDS_BUTTON_TEXT, ADMIN_REWARDS_TEXT
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

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


@router.message(F.text == ADMIN_REWARDS_BUTTON_TEXT)
async def admin_rewards_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("🚫 Раздел доступен только администрации.")
        return
    await state.clear()
    await safe_delete_message(message)
    await message.answer(ADMIN_REWARDS_TEXT, reply_markup=build_admin_rewards_keyboard())


@router.callback_query(F.data == "admin_rewards:main")
async def admin_rewards_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администрации", show_alert=True)
        return
    await state.clear()
    await edit_or_send(callback, ADMIN_REWARDS_TEXT, reply_markup=build_admin_rewards_keyboard())
    await callback.answer()
