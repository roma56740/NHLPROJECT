from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.keyboards.admin_cards import build_admin_cards_main_keyboard
from app.services.bulk_import import create_bulk_cards, parse_bulk_cards
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin

router = Router()


class BulkCardStates(StatesGroup):
    waiting_for_text = State()


BULK_TEMPLATE_TEXT = """
<b>📥 Массовое добавление карт</b>

Вставь список карт одним сообщением. Карты разделяй пустой строкой.
Шаблон одной карты (поля в любом порядке, можно рус/англ):

<code>Имя: Sidney Crosby
Позиция: F
OVR: 87
Команда: Pittsburgh Penguins
Страна: Canada
Коллекция: Base Collection
Редкость: Epic
Зарплата: 5.5</code>

Позиция: G / D / F. Редкость: Common, Rare, Epic, Legendary, Event, Icon. Зарплата — в миллионах.
Картинку добавишь позже в карточке (пока ставится логотип-заглушка).
""".strip()


def build_bulk_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_cards:main")]])


def build_bulk_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать карты", callback_data="bulk_cards:confirm")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_cards:main")],
        ]
    )


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data == "bulk_cards:start")
async def bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для администрации", show_alert=True)
        return
    await state.clear()
    await state.set_state(BulkCardStates.waiting_for_text)
    await edit_or_send(callback, BULK_TEMPLATE_TEXT, reply_markup=build_bulk_cancel_keyboard())
    await callback.answer()


@router.message(BulkCardStates.waiting_for_text)
async def bulk_receive(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await safe_delete_message(message)

    parsed = parse_bulk_cards(message.text or "")
    if not parsed:
        await message.answer("Не удалось разобрать ни одной карты. Проверь формат.", reply_markup=build_bulk_cancel_keyboard())
        return

    valid = [p for p in parsed if p.error is None]
    invalid = [p for p in parsed if p.error is not None]

    # сохраняем распознанный текст, чтобы пересобрать на подтверждении
    await state.update_data(raw_text=message.text or "")

    lines = [f"<b>📥 Предпросмотр</b>\n\nВсего распознано: {len(parsed)}", f"✅ Готовы к добавлению: <b>{len(valid)}</b>"]
    for p in valid[:15]:
        lines.append(f"  • {p.fields['name']} · {p.fields['overall']} OVR · {p.fields['rarity']}")
    if invalid:
        lines.append(f"\n❌ С ошибками: <b>{len(invalid)}</b>")
        for p in invalid[:15]:
            name = p.fields.get("name", f"строка {p.line_no}")
            lines.append(f"  • {name}: {p.error}")

    keyboard = build_bulk_confirm_keyboard() if valid else build_bulk_cancel_keyboard()
    await message.answer("\n".join(lines), reply_markup=keyboard)


@router.callback_query(F.data == "bulk_cards:confirm")
async def bulk_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для администрации", show_alert=True)
        return
    data = await state.get_data()
    raw_text = data.get("raw_text", "")
    await state.clear()

    parsed = parse_bulk_cards(raw_text)
    created, errors = await create_bulk_cards(parsed)

    lines = [f"<b>✅ Готово</b>\n\nСоздано карт: <b>{created}</b>"]
    if errors:
        lines.append(f"\nНе добавлено: <b>{len(errors)}</b>")
        for err in errors[:15]:
            lines.append(f"  {err}")
    await edit_or_send(callback, "\n".join(lines), reply_markup=build_admin_cards_main_keyboard())
    await callback.answer(f"Создано {created}")
