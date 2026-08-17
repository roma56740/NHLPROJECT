from __future__ import annotations

from html import escape
from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.db import get_connection
from app.services.community import get_user_id_by_telegram_id
from app.services.creator_tournaments import (
    cancel_match,
    cancel_pending_result,
    create_pending_result,
    create_tournament,
    ensure_tournament_invite_token,
    find_matches_needing_attention,
    get_tournament_invite,
    invite_payload,
    force_simulate_match,
    get_active_pending_result,
    mark_ready_and_play,
    parse_score_text,
    register,
    resolve_pending_result,
    restart_match,
    set_pending_result_prompt_message,
    submit_manual_result,
    tournament_text,
)
from app.services.creators import get_panel, is_creator
from app.utils.messages import safe_delete_callback_message, safe_delete_message, safe_edit_message

router=Router()

class TournamentCreate(StatesGroup):
    name=State(); description=State(); size=State(); duration=State(); rewards=State()


def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Создать турнир',callback_data='ct:create')],[InlineKeyboardButton(text='📋 Мои турниры',callback_data='ct:mine')],[InlineKeyboardButton(text='⬅️ Назад',callback_data='creator:panel')]])

async def _tournament_deep_link(bot, tournament_id: int, creator_user_id: int | None = None) -> str | None:
    token = await ensure_tournament_invite_token(tournament_id, creator_user_id)
    if not token:
        return None
    me = await bot.get_me()
    if not me.username:
        return None
    return f"https://t.me/{me.username}?start={invite_payload(token)}"


def _share_url(link: str, title: str) -> str:
    share_text = f"🏆 {title}\nЗаходи в турнир по ссылке:"
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(share_text, safe='')}"


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
    if ok:
        link=await _tournament_deep_link(message.bot,tid,uid)
        rows=[[InlineKeyboardButton(text='Участвовать',callback_data=f'ct:join:{tid}')],[InlineKeyboardButton(text='📊 Сетка турнира',callback_data=f'ct:view:{tid}')]]
        if link:
            rows.append([InlineKeyboardButton(text='📤 Поделиться турниром',url=_share_url(link,data['title']))])
            rows.append([InlineKeyboardButton(text='🔗 Показать ссылку',callback_data=f'ct:share:{tid}')])
        kb=InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(('✅ ' if ok else '❌ ')+msg,reply_markup=kb)

@router.callback_query(F.data.startswith('ct:share:'))
async def share_tournament(callback:CallbackQuery):
    tid=int(callback.data.rsplit(':',1)[1]);uid=get_user_id_by_telegram_id(callback.from_user.id)
    meta=await get_tournament_invite(tid)
    if not meta or not uid or int(meta['creator_user_id'])!=int(uid):
        await callback.answer('Турнир недоступен.',show_alert=True);return
    if str(meta['status'])!='registration':
        await callback.answer('Ссылку можно раздавать только пока открыта регистрация.',show_alert=True);return
    link=await _tournament_deep_link(callback.bot,tid,uid)
    if not link:
        await callback.answer('Не удалось собрать ссылку.',show_alert=True);return
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📤 Поделиться',url=_share_url(link,str(meta['title'])))],
        [InlineKeyboardButton(text='📊 Открыть турнир',callback_data=f'ct:view:{tid}')],
    ])
    await callback.message.answer(
        f"<b>🔗 Ссылка на турнир</b>\n\n<code>{escape(link, quote=False)}</code>\n\n"
        "Игрок открывает ссылку, нажимает Start и автоматически регистрируется, если регистрация открыта и есть место.",
        reply_markup=kb,
    )
    await callback.answer()


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
        creator_row=c.execute('SELECT creator_user_id FROM creator_tournaments WHERE id=?',(tid,)).fetchone()
    rows=[[InlineKeyboardButton(text=f'🎮 Играть матч #{r[0]}',callback_data=f'ct:play:{r[0]}')] for r in matches]
    if creator_row and int(creator_row['creator_user_id'])==uid:
        meta=await get_tournament_invite(tid)
        if meta and str(meta['status'])=='registration':
            rows.append([InlineKeyboardButton(text='🔗 Поделиться турниром',callback_data=f'ct:share:{tid}')])
        attention=await find_matches_needing_attention(tid)
        if attention:
            rows.append([InlineKeyboardButton(text=f'⚠️ Требуют внимания ({len(attention)})',callback_data=f'ct:attention:{tid}')])
    rows.append([InlineKeyboardButton(text='🔄 Обновить',callback_data=f'ct:view:{tid}')])
    await safe_edit_message(callback,text,InlineKeyboardMarkup(inline_keyboard=rows));await callback.answer()

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


# ---------------------------------------------------------------------------
# Восстановление зависших матчей (раздел 3 спеки)
# ---------------------------------------------------------------------------

STATUS_LABELS={'waiting':'ожидает','pending':'ожидает','playing':'идёт','failed':'⚠️ зависший','problem':'⚠️ зависший','cancelled':'отменён'}


def _match_title(m)->str:
    return f"{m['n1'] or 'TBD'} — {m['n2'] or 'TBD'}"


async def _uid(callback:CallbackQuery)->int|None:
    return get_user_id_by_telegram_id(callback.from_user.id)


@router.callback_query(F.data.startswith('ct:attention:'))
async def attention_list(callback:CallbackQuery):
    tid=int(callback.data.rsplit(':',1)[1]);uid=await _uid(callback)
    matches=await find_matches_needing_attention(tid)
    matches=[m for m in matches if uid and int(m['creator_user_id'])==uid]
    if not matches:
        await callback.answer('Зависших матчей нет.',show_alert=True)
        return
    lines=['<b>⚠️ Требуют вмешательства</b>','']
    rows=[]
    for m in matches:
        status=STATUS_LABELS.get(m['status'],m['status'])
        lines.append(f"#{m['id']} {_match_title(m)} — {status}")
        rows.append([InlineKeyboardButton(text=f"#{m['id']} {_match_title(m)}",callback_data=f"ct:attention_match:{m['id']}")])
    rows.append([InlineKeyboardButton(text='⬅️ Назад',callback_data=f'ct:view:{tid}')])
    await safe_edit_message(callback,'\n'.join(lines),InlineKeyboardMarkup(inline_keyboard=rows));await callback.answer()


async def _render_attention_match(callback:CallbackQuery,mid:int)->bool:
    """Отрисовывает карточку зависшего матча. Не вызывает callback.answer() — это
    осознанно (Telegram отклоняет повторный answer на один и тот же callback_query),
    чтобы функцию можно было безопасно переиспользовать после restart/force_sim/cancel,
    которые уже сами ответили на callback алертом с результатом действия."""
    uid=await _uid(callback)
    with get_connection() as c:
        m=c.execute("SELECT mm.*,u1.nickname n1,u2.nickname n2,t.creator_user_id,t.id tournament_id FROM creator_tournament_matches mm LEFT JOIN users u1 ON u1.id=mm.player1_user_id LEFT JOIN users u2 ON u2.id=mm.player2_user_id JOIN creator_tournaments t ON t.id=mm.tournament_id WHERE mm.id=?",(mid,)).fetchone()
    if not m or not uid or int(m['creator_user_id'])!=uid:
        return False
    status=STATUS_LABELS.get(m['status'],m['status'])
    lines=[f"⚠️ Матч #{mid}",'',_match_title(m),f'Статус: {status}',f"Попыток: {m['attempt_count'] or 0}"]
    if m['error_message']:lines.append(f"Ошибка: {m['error_message']}")
    kb=[
        [InlineKeyboardButton(text='🔄 Перезапустить матч',callback_data=f'ct:restart:{mid}')],
        [InlineKeyboardButton(text='✍️ Назначить результат',callback_data=f'ct:manual_start:{mid}')],
        [InlineKeyboardButton(text='▶️ Завершить симуляцией',callback_data=f'ct:force_sim:{mid}')],
        [InlineKeyboardButton(text='❌ Отменить матч',callback_data=f'ct:cancel_ask:{mid}')],
        [InlineKeyboardButton(text='📋 Журнал матча',callback_data=f'ct:logs:{mid}')],
        [InlineKeyboardButton(text='⬅️ Назад',callback_data=f"ct:attention:{m['tournament_id']}")],
    ]
    await safe_edit_message(callback,'\n'.join(lines),InlineKeyboardMarkup(inline_keyboard=kb))
    return True


@router.callback_query(F.data.startswith('ct:attention_match:'))
async def attention_match(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1])
    ok=await _render_attention_match(callback,mid)
    if not ok:
        await callback.answer('Матч недоступен.',show_alert=True);return
    await callback.answer()


@router.callback_query(F.data.startswith('ct:restart:'))
async def restart_action(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1]);uid=await _uid(callback)
    ok,msg=await restart_match(mid,uid) if uid else (False,'Открой игру через /start.')
    await callback.answer(msg,show_alert=True)
    await _render_attention_match(callback,mid)


@router.callback_query(F.data.startswith('ct:force_sim:'))
async def force_sim_action(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1]);uid=await _uid(callback)
    ok,msg,result=await force_simulate_match(mid,uid) if uid else (False,'Открой игру через /start.',None)
    await callback.answer(msg,show_alert=True)
    await _render_attention_match(callback,mid)


@router.callback_query(F.data.startswith('ct:cancel_ask:'))
async def cancel_ask(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1])
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Да, отменить матч',callback_data=f'ct:cancel_confirm:{mid}')],
        [InlineKeyboardButton(text='⬅️ Назад',callback_data=f'ct:attention_match:{mid}')],
    ])
    await safe_edit_message(callback,f'Отменить матч #{mid}? Действие необратимо.',kb);await callback.answer()


@router.callback_query(F.data.startswith('ct:cancel_confirm:'))
async def cancel_confirm(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1]);uid=await _uid(callback)
    ok,msg=await cancel_match(mid,uid,'Отменено создателем турнира.') if uid else (False,'Открой игру через /start.')
    await callback.answer(msg,show_alert=True)
    await _render_attention_match(callback,mid)


@router.callback_query(F.data.startswith('ct:logs:'))
async def match_logs(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1])
    with get_connection() as c:
        m=c.execute('SELECT tournament_id FROM creator_tournament_matches WHERE id=?',(mid,)).fetchone()
        if not m:
            await callback.answer('Матч не найден.',show_alert=True);return
        logs=c.execute("SELECT * FROM creator_tournament_logs WHERE tournament_id=? AND (details LIKE ? OR action='completed') ORDER BY id DESC LIMIT 20",(m['tournament_id'],f'%"match_id": {mid}%')).fetchall()
    lines=[f'<b>📋 Журнал матча #{mid}</b>','']
    for entry in logs:
        lines.append(f"{entry['created_at']} — {entry['action']}: {entry['details']}")
    if len(lines)==2:lines.append('Записей пока нет.')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Назад',callback_data=f'ct:attention_match:{mid}')]])
    await safe_edit_message(callback,'\n'.join(lines)[:4000],kb);await callback.answer()


# ---------------------------------------------------------------------------
# Ручной ввод результата — состояние хранится в БД (creator_tournament_pending_results),
# переживает restart/redeploy (раздел 5 спеки), не использует aiogram FSM.
# ---------------------------------------------------------------------------

def _score_prompt_kb()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Отменить ввод результата',callback_data='ct:manual_cancel')]])


@router.callback_query(F.data.startswith('ct:manual_start:'))
async def manual_start(callback:CallbackQuery):
    mid=int(callback.data.rsplit(':',1)[1]);uid=await _uid(callback)
    if not uid:
        await callback.answer('Открой игру через /start.',show_alert=True);return
    with get_connection() as c:
        m=c.execute('SELECT tournament_id,player1_user_id,player2_user_id FROM creator_tournament_matches WHERE id=?',(mid,)).fetchone()
        if not m:
            await callback.answer('Матч не найден.',show_alert=True);return
        players=c.execute('SELECT id,nickname FROM users WHERE id IN (?,?)',(m['player1_user_id'],m['player2_user_id'])).fetchall()
    names={int(p['id']):p['nickname'] for p in players}
    n1=names.get(int(m['player1_user_id'] or 0),'TBD'); n2=names.get(int(m['player2_user_id'] or 0),'TBD')
    ok,msg,pending_id=await create_pending_result(uid,int(m['tournament_id']),mid,callback.message.chat.id)
    if not ok:
        await callback.answer(msg,show_alert=True);return
    text=(
        f'✍️ Результат матча #{mid}\n\n'
        f'1️⃣ {n1}\n2️⃣ {n2}\n\n'
        'Введите итоговый счёт:\n3:2\n\n'
        'Первая цифра относится к первому игроку.\n'
        'Вторая цифра относится ко второму игроку.\n'
        'Ничья запрещена.'
    )
    sent=await callback.message.answer(text,reply_markup=_score_prompt_kb())
    await set_pending_result_prompt_message(pending_id,sent.message_id)
    await callback.answer()


@router.callback_query(F.data=='ct:manual_cancel')
async def manual_cancel(callback:CallbackQuery):
    uid=await _uid(callback)
    if uid:await cancel_pending_result(uid)
    await callback.answer('Ввод результата отменён.',show_alert=True)
    await safe_delete_callback_message(callback)


@router.message(StateFilter(None))
async def maybe_manual_result(message:Message)->None:
    """Ловит текстовый ввод счёта для отложенного результата (creator_tournament_pending_results).

    Не использует FSMContext специально — такое состояние не переживает restart/redeploy,
    а этот флоу обязан их переживать (раздел 5 спеки). Не мешает остальным обработчикам:
    срабатывает только если у отправителя есть активная запись ожидания в БД.
    """
    if message.from_user is None or not message.text:
        return
    uid=get_user_id_by_telegram_id(message.from_user.id)
    if not uid:
        return
    pending=await get_active_pending_result(uid)
    if not pending:
        return
    await safe_delete_message(message)
    parsed=parse_score_text(message.text)
    if parsed is None:
        await message.answer(
            'Некорректный счёт. Примеры: 3:2, 3-2, 3 2. Ничья запрещена.',
            reply_markup=_score_prompt_kb(),
        )
        return
    score1,score2=parsed
    ok,msg=await submit_manual_result(pending['match_id'],uid,score1,score2)
    await resolve_pending_result(int(pending['id']))
    await message.answer(('✅ ' if ok else '❌ ')+msg)
