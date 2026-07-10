from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.services.community import get_user_id_by_telegram_id
from app.services.creator_tournaments import create_tournament, mark_ready_and_play, register, tournament_text
from app.services.creators import get_panel, is_creator

router=Router()

class TournamentCreate(StatesGroup):
    name=State(); description=State(); size=State(); duration=State(); rewards=State()


def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Создать турнир',callback_data='ct:create')],[InlineKeyboardButton(text='📋 Мои турниры',callback_data='ct:mine')],[InlineKeyboardButton(text='⬅️ Назад',callback_data='creator:panel')]])

@router.callback_query(F.data=='creator:tournaments')
async def tournaments(callback:CallbackQuery,state:FSMContext):
    await state.clear(); uid=get_user_id_by_telegram_id(callback.from_user.id)
    if not uid or not await is_creator(uid): await callback.answer('Только для креаторов',show_alert=True);return
    await callback.message.edit_text('<b>🏆 Турниры</b>\n\nСоздавай playoff-турниры с наградами из банка.',reply_markup=menu_kb());await callback.answer()

@router.callback_query(F.data=='ct:create')
async def create_start(callback:CallbackQuery,state:FSMContext):
    await state.set_state(TournamentCreate.name);await callback.message.edit_text('Название турнира:');await callback.answer()

@router.message(TournamentCreate.name)
async def create_name(message:Message,state:FSMContext):
    await state.update_data(title=(message.text or '')[:80]);await state.set_state(TournamentCreate.description);await message.answer('Описание турнира:')

@router.message(TournamentCreate.description)
async def create_desc(message:Message,state:FSMContext):
    await state.update_data(description=(message.text or '')[:500]);await state.set_state(TournamentCreate.size);await message.answer('Количество участников: 2, 4, 8, 16 или 32')

@router.message(TournamentCreate.size)
async def create_size(message:Message,state:FSMContext):
    raw=(message.text or '').strip()
    if raw not in {'2','4','8','16','32'}:await message.answer('Допустимо только: 2, 4, 8, 16, 32');return
    await state.update_data(capacity=int(raw));await state.set_state(TournamentCreate.duration);await message.answer('Время на матч в минутах: 30, 60, 180, 360, 720 или 1440')

@router.message(TournamentCreate.duration)
async def create_duration(message:Message,state:FSMContext):
    raw=(message.text or '').strip()
    if raw not in {'30','60','180','360','720','1440'}:await message.answer('Допустимо: 30, 60, 180, 360, 720, 1440');return
    uid=get_user_id_by_telegram_id(message.from_user.id);panel=await get_panel(uid)
    items='\n'.join(f"ID {i.id}: {i.title} ×{i.quantity}" for i in panel.bank_items)
    await state.update_data(duration=int(raw));await state.set_state(TournamentCreate.rewards)
    await message.answer('Укажи награды, каждая с новой строки:\n<code>место|ID_награды|количество</code>\nДиапазон: <code>5-8|ID|1</code>\n\n'+items)

@router.message(TournamentCreate.rewards)
async def create_rewards(message:Message,state:FSMContext):
    rewards=[]
    try:
        for line in (message.text or '').splitlines():
            place,item,qty=[x.strip() for x in line.split('|')]
            if '-' in place:a,b=map(int,place.split('-',1))
            else:a=b=int(place)
            rewards.append({'place_from':a,'place_to':b,'bank_item_id':int(item),'quantity':int(qty)})
    except Exception:await message.answer('Ошибка формата. Пример: <code>1|15|100000</code>');return
    data=await state.get_data();await state.clear();uid=get_user_id_by_telegram_id(message.from_user.id)
    ok,msg,tid=await create_tournament(uid,data['title'],data['description'],data['capacity'],data['duration'],rewards)
    kb=None
    if ok:kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Участвовать',callback_data=f'ct:join:{tid}')],[InlineKeyboardButton(text='📊 Сетка турнира',callback_data=f'ct:view:{tid}')]])
    await message.answer(('✅ ' if ok else '❌ ')+msg,reply_markup=kb)

@router.callback_query(F.data.startswith('ct:join:'))
async def join(callback:CallbackQuery):
    tid=int(callback.data.rsplit(':',1)[1]);uid=get_user_id_by_telegram_id(callback.from_user.id)
    ok,msg,started=await register(tid,uid);await callback.answer(msg,show_alert=not ok)
    if ok and started:await callback.message.answer('🏆 Турнир заполнен и запущен. Открой сетку, чтобы сыграть матч.')

@router.callback_query(F.data.startswith('ct:view:'))
async def view(callback:CallbackQuery):
    tid=int(callback.data.rsplit(':',1)[1]);text=await tournament_text(tid);uid=get_user_id_by_telegram_id(callback.from_user.id)
    with get_connection() as c:
        matches=c.execute("SELECT id FROM creator_tournament_matches WHERE tournament_id=? AND status IN ('pending','waiting') AND (player1_user_id=? OR player2_user_id=?)",(tid,uid,uid)).fetchall()
    rows=[[InlineKeyboardButton(text=f'🎮 Играть матч #{r[0]}',callback_data=f'ct:play:{r[0]}')] for r in matches]
    rows.append([InlineKeyboardButton(text='🔄 Обновить',callback_data=f'ct:view:{tid}')])
    await callback.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback.answer()

@router.callback_query(F.data.startswith('ct:play:'))
async def play(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1]);uid=get_user_id_by_telegram_id(callback.from_user.id)
    ok,msg,result=await mark_ready_and_play(mid,uid);await callback.answer(msg,show_alert=not ok)
    if result:await callback.message.answer(f"Матч завершён: {result['score1']}:{result['score2']}")

@router.callback_query(F.data=='ct:mine')
async def mine(callback:CallbackQuery):
    uid=get_user_id_by_telegram_id(callback.from_user.id)
    with get_connection() as c:rows=c.execute('SELECT id,title,status FROM creator_tournaments WHERE creator_user_id=? ORDER BY id DESC LIMIT 20',(uid,)).fetchall()
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"#{r['id']} {r['title']} · {r['status']}",callback_data=f"ct:view:{r['id']}")] for r in rows]+[[InlineKeyboardButton(text='⬅️ Назад',callback_data='creator:tournaments')]])
    await callback.message.edit_text('<b>Мои турниры</b>',reply_markup=kb);await callback.answer()
