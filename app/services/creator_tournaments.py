from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.db import get_connection
from app.services.rewards import grant_currency, grant_pack

ALLOWED_SIZES = {2, 4, 8, 16, 32}
ALLOWED_DURATIONS = {30, 60, 180, 360, 720, 1440}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: datetime) -> str:
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _round_name(size: int) -> str:
    return {32:'1/16 финала',16:'1/8 финала',8:'1/4 финала',4:'Полуфинал',2:'Финал'}[size]


def migrate_creator_tournaments(connection) -> None:
    queries = [
        """CREATE TABLE IF NOT EXISTS creator_tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, creator_user_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', capacity INTEGER NOT NULL, round_duration_minutes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'registration', started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(creator_user_id) REFERENCES users(id))""",
        """CREATE TABLE IF NOT EXISTS creator_tournament_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, user_id INTEGER NOT NULL, seed INTEGER, final_place INTEGER, eliminated_round TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(tournament_id,user_id), FOREIGN KEY(tournament_id) REFERENCES creator_tournaments(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id))""",
        """CREATE TABLE IF NOT EXISTS creator_tournament_matches (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, round_no INTEGER NOT NULL, round_name TEXT NOT NULL, bracket_index INTEGER NOT NULL, player1_user_id INTEGER, player2_user_id INTEGER, player1_ready_at TEXT, player2_ready_at TEXT, deadline TEXT, winner_user_id INTEGER, loser_user_id INTEGER, score1 INTEGER, score2 INTEGER, status TEXT NOT NULL DEFAULT 'pending', is_third_place INTEGER NOT NULL DEFAULT 0, decided_by TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT, UNIQUE(tournament_id,round_no,bracket_index,is_third_place), FOREIGN KEY(tournament_id) REFERENCES creator_tournaments(id) ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS creator_tournament_reward_items (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, place_from INTEGER NOT NULL, place_to INTEGER NOT NULL, bank_item_id INTEGER NOT NULL, item_type TEXT NOT NULL, currency_code TEXT, pack_id INTEGER, user_card_id INTEGER, quantity INTEGER NOT NULL, value_per_unit INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(tournament_id) REFERENCES creator_tournaments(id) ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS creator_tournament_reward_deliveries (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, reward_item_id INTEGER NOT NULL, recipient_user_id INTEGER NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'delivered', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS creator_tournament_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL, actor_user_id INTEGER, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        "CREATE INDEX IF NOT EXISTS idx_creator_tournaments_status ON creator_tournaments(status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_creator_tournament_matches_deadline ON creator_tournament_matches(status,deadline)",
    ]
    for query in queries:
        connection.execute(query)


def _log(c, tournament_id: int, actor: int | None, action: str, details: Any='') -> None:
    c.execute('INSERT INTO creator_tournament_logs(tournament_id,actor_user_id,action,details) VALUES(?,?,?,?)', (tournament_id,actor,action,json.dumps(details,ensure_ascii=False) if not isinstance(details,str) else details))


async def create_tournament(creator_user_id: int, title: str, description: str, capacity: int, duration: int, rewards: list[dict]) -> tuple[bool,str,int|None]:
    if capacity not in ALLOWED_SIZES or duration not in ALLOWED_DURATIONS or not title.strip():
        return False, 'Некорректные параметры турнира.', None
    if not rewards:
        return False, 'Добавь хотя бы одну награду.', None
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        creator=c.execute('SELECT is_creator FROM users WHERE id=?',(creator_user_id,)).fetchone()
        if not creator or not creator['is_creator']:
            c.rollback(); return False,'Только для официальных креаторов.',None
        cur=c.execute('INSERT INTO creator_tournaments(creator_user_id,title,description,capacity,round_duration_minutes) VALUES(?,?,?,?,?)',(creator_user_id,title.strip(),description.strip(),capacity,duration))
        tid=int(cur.lastrowid)
        for reward in rewards:
            item_id=int(reward['bank_item_id']); qty=int(reward['quantity']); pf=int(reward['place_from']); pt=int(reward.get('place_to',pf))
            row=c.execute("SELECT * FROM creator_bank_items WHERE id=? AND user_id=? AND status='available' AND quantity>=?",(item_id,creator_user_id,qty)).fetchone()
            if not row or qty<=0 or pf<1 or pt>capacity or pf>pt:
                c.rollback(); return False,'Награда недоступна или место указано неверно.',None
            c.execute("UPDATE creator_bank_items SET quantity=quantity-?, status=CASE WHEN quantity-?<=0 THEN 'distributed' ELSE status END, updated_at=CURRENT_TIMESTAMP WHERE id=?",(qty,qty,item_id))
            c.execute('''INSERT INTO creator_tournament_reward_items(tournament_id,place_from,place_to,bank_item_id,item_type,currency_code,pack_id,user_card_id,quantity,value_per_unit) VALUES(?,?,?,?,?,?,?,?,?,?)''',(tid,pf,pt,item_id,row['item_type'],row['currency_code'],row['pack_id'],row['user_card_id'],qty,row['value_per_unit']))
        _log(c,tid,creator_user_id,'created',{'capacity':capacity,'duration':duration})
        c.commit()
    return True,'Турнир создан. Награды зарезервированы.',tid


async def register(tournament_id:int, user_id:int)->tuple[bool,str,bool]:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        t=c.execute("SELECT * FROM creator_tournaments WHERE id=? AND status='registration'",(tournament_id,)).fetchone()
        if not t: c.rollback(); return False,'Регистрация закрыта.',False
        has_rewards=c.execute('SELECT 1 FROM creator_tournament_reward_items WHERE tournament_id=? LIMIT 1',(tournament_id,)).fetchone()
        if has_rewards and int(t['creator_user_id'])==user_id: c.rollback(); return False,'Создатель не может участвовать в турнире с наградами.',False
        count=c.execute('SELECT COUNT(*) n FROM creator_tournament_participants WHERE tournament_id=?',(tournament_id,)).fetchone()['n']
        if count>=t['capacity']: c.rollback(); return False,'Все места заняты.',False
        try:c.execute('INSERT INTO creator_tournament_participants(tournament_id,user_id) VALUES(?,?)',(tournament_id,user_id))
        except Exception:c.rollback(); return False,'Ты уже зарегистрирован.',False
        count+=1; started=False
        if count==t['capacity']:
            _start_bracket(c,tournament_id,int(t['capacity']),int(t['round_duration_minutes'])); started=True
        _log(c,tournament_id,user_id,'registered')
        c.commit()
    return True,'Регистрация подтверждена.',started


def _start_bracket(c,tid:int,capacity:int,duration:int)->None:
    ids=[int(r['user_id']) for r in c.execute('SELECT user_id FROM creator_tournament_participants WHERE tournament_id=?',(tid,)).fetchall()]
    random.shuffle(ids)
    for i,uid in enumerate(ids,1): c.execute('UPDATE creator_tournament_participants SET seed=? WHERE tournament_id=? AND user_id=?',(i,tid,uid))
    deadline=_dt(_utcnow()+timedelta(minutes=duration))
    for idx in range(capacity//2):
        c.execute('INSERT INTO creator_tournament_matches(tournament_id,round_no,round_name,bracket_index,player1_user_id,player2_user_id,deadline) VALUES(?,?,?,?,?,?,?)',(tid,1,_round_name(capacity),idx,ids[idx*2],ids[idx*2+1],deadline))
    c.execute("UPDATE creator_tournaments SET status='active',started_at=CURRENT_TIMESTAMP WHERE id=?",(tid,)); _log(c,tid,None,'started')


async def mark_ready_and_play(match_id:int,user_id:int)->tuple[bool,str,dict|None]:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m=c.execute("SELECT * FROM creator_tournament_matches WHERE id=? AND status IN ('pending','waiting')",(match_id,)).fetchone()
        if not m or user_id not in (m['player1_user_id'],m['player2_user_id']): c.rollback(); return False,'Матч недоступен.',None
        col='player1_ready_at' if user_id==m['player1_user_id'] else 'player2_ready_at'
        c.execute(f'UPDATE creator_tournament_matches SET {col}=COALESCE({col},CURRENT_TIMESTAMP),status=\'waiting\' WHERE id=?',(match_id,))
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m['player1_ready_at'] or not m['player2_ready_at']:
            c.commit(); return True,'Ожидаем соперника...',None
        changed=c.execute("UPDATE creator_tournament_matches SET status='playing' WHERE id=? AND status='waiting'",(match_id,)).rowcount
        if not changed: c.rollback(); return False,'Матч уже запускается.',None
        users=c.execute('SELECT id,telegram_id FROM users WHERE id IN (?,?)',(m['player1_user_id'],m['player2_user_id'])).fetchall(); c.commit()
    tele={int(r['id']):int(r['telegram_id']) for r in users}
    from app.services.matches import play_player_match
    r1,r2=await play_player_match(tele[int(m['player1_user_id'])],tele[int(m['player2_user_id'])])
    if not r1 or not r2:
        with get_connection() as c:c.execute("UPDATE creator_tournament_matches SET status='problem' WHERE id=?",(match_id,));c.commit()
        return False,'Не удалось запустить матч: проверьте составы.',None
    winner=int(m['player1_user_id']) if r1.user_score>r1.opponent_score else int(m['player2_user_id'])
    await complete_match(match_id,winner,r1.user_score,r1.opponent_score,'played')
    return True,'Матч завершён.',{'score1':r1.user_score,'score2':r1.opponent_score,'winner_user_id':winner}


async def complete_match(match_id:int,winner_id:int,score1:int|None=None,score2:int|None=None,decided_by:str='manual')->None:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE'); m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m or m['status']=='completed': c.rollback(); return
        loser=int(m['player2_user_id'] if winner_id==m['player1_user_id'] else m['player1_user_id'])
        c.execute("UPDATE creator_tournament_matches SET winner_user_id=?,loser_user_id=?,score1=?,score2=?,status='completed',decided_by=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",(winner_id,loser,score1,score2,decided_by,match_id))
        _log(c,int(m['tournament_id']),winner_id,'match_completed',{'match_id':match_id,'by':decided_by})
        _advance(c,int(m['tournament_id']),int(m['round_no']))
        c.commit()


def _advance(c,tid:int,round_no:int)->None:
    pending=c.execute("SELECT COUNT(*) n FROM creator_tournament_matches WHERE tournament_id=? AND round_no=? AND is_third_place=0 AND status!='completed'",(tid,round_no)).fetchone()['n']
    if pending:return
    current=c.execute('SELECT * FROM creator_tournament_matches WHERE tournament_id=? AND round_no=? AND is_third_place=0 ORDER BY bracket_index',(tid,round_no)).fetchall()
    if len(current)==1:
        final=current[0]; c.execute('UPDATE creator_tournament_participants SET final_place=1 WHERE tournament_id=? AND user_id=?',(tid,final['winner_user_id'])); c.execute('UPDATE creator_tournament_participants SET final_place=2 WHERE tournament_id=? AND user_id=?',(tid,final['loser_user_id']))
        third=c.execute('SELECT * FROM creator_tournament_matches WHERE tournament_id=? AND is_third_place=1',(tid,)).fetchone()
        if third and third['status']!='completed':return
        if third:
            c.execute('UPDATE creator_tournament_participants SET final_place=3 WHERE tournament_id=? AND user_id=?',(tid,third['winner_user_id'])); c.execute('UPDATE creator_tournament_participants SET final_place=4 WHERE tournament_id=? AND user_id=?',(tid,third['loser_user_id']))
        _finish(c,tid); return
    winners=[int(r['winner_user_id']) for r in current]; duration=int(c.execute('SELECT round_duration_minutes FROM creator_tournaments WHERE id=?',(tid,)).fetchone()[0]); deadline=_dt(_utcnow()+timedelta(minutes=duration))
    next_size=len(winners); rn=round_no+1
    for idx in range(next_size//2): c.execute('INSERT OR IGNORE INTO creator_tournament_matches(tournament_id,round_no,round_name,bracket_index,player1_user_id,player2_user_id,deadline) VALUES(?,?,?,?,?,?,?)',(tid,rn,_round_name(next_size),idx,winners[idx*2],winners[idx*2+1],deadline))
    if len(current)==2:
        losers=[int(r['loser_user_id']) for r in current]
        c.execute('INSERT OR IGNORE INTO creator_tournament_matches(tournament_id,round_no,round_name,bracket_index,player1_user_id,player2_user_id,deadline,is_third_place) VALUES(?,?,?,?,?,?,?,?,1)',(tid,rn,'Матч за 3 место',0,losers[0],losers[1],deadline))


def _finish(c,tid:int)->None:
    participants=c.execute('SELECT user_id,final_place FROM creator_tournament_participants WHERE tournament_id=?',(tid,)).fetchall()
    for p in participants:
        if not p['final_place']:continue
        rewards=c.execute('SELECT * FROM creator_tournament_reward_items WHERE tournament_id=? AND ? BETWEEN place_from AND place_to',(tid,p['final_place'])).fetchall()
        for r in rewards:
            key=f"tournament:{tid}:reward:{r['id']}:user:{p['user_id']}"
            try:c.execute('INSERT INTO creator_tournament_reward_deliveries(tournament_id,reward_item_id,recipient_user_id,idempotency_key) VALUES(?,?,?,?)',(tid,r['id'],p['user_id'],key))
            except Exception:continue
            if r['item_type']=='currency':grant_currency(c,p['user_id'],r['currency_code'],r['quantity'])
            elif r['item_type']=='pack':grant_pack(c,p['user_id'],r['pack_id'],r['quantity'])
            else:c.execute("UPDATE user_cards SET user_id=?,is_in_lineup=0,lineup_slot=NULL,trade_locked=0,lock_reason=NULL,lock_until=NULL,obtained_from='creator_tournament',updated_at=CURRENT_TIMESTAMP WHERE id=?",(p['user_id'],r['user_card_id']))
            c.execute('INSERT INTO creator_distributions(creator_user_id,target_user_id,reward_desc,reward_type,value_coins,amount,source_item_id) SELECT creator_user_id,?,?,?,value_per_unit*quantity,quantity,bank_item_id FROM creator_tournaments JOIN creator_tournament_reward_items ON creator_tournament_reward_items.tournament_id=creator_tournaments.id WHERE creator_tournament_reward_items.id=?',(p['user_id'],f"Турнир #{tid}, место {p['final_place']}",r['item_type'],r['id']))
    c.execute("UPDATE creator_tournaments SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE id=?",(tid,));_log(c,tid,None,'completed')


async def tournament_text(tid:int)->str:
    with get_connection() as c:
        t=c.execute('SELECT * FROM creator_tournaments WHERE id=?',(tid,)).fetchone()
        if not t:return 'Турнир не найден.'
        matches=c.execute('''SELECT m.*,u1.nickname n1,u2.nickname n2 FROM creator_tournament_matches m LEFT JOIN users u1 ON u1.id=m.player1_user_id LEFT JOIN users u2 ON u2.id=m.player2_user_id WHERE m.tournament_id=? ORDER BY m.round_no,m.is_third_place,m.bracket_index''',(tid,)).fetchall()
        count=c.execute('SELECT COUNT(*) FROM creator_tournament_participants WHERE tournament_id=?',(tid,)).fetchone()[0]
    lines=[f"<b>🏆 {t['title']}</b>",t['description'] or '',f"Участники: {count}/{t['capacity']}",f"Статус: {t['status']}"]
    last=None
    for m in matches:
        title=m['round_name']
        if title!=last:lines+=['',f'<b>{title.upper()}</b>'];last=title
        score=f"{m['score1']}:{m['score2']}" if m['status']=='completed' and m['score1'] is not None else ('ожидает' if m['status']!='completed' else 'тех.')
        lines.append(f"#{m['id']} {m['n1'] or 'TBD'} — {score} — {m['n2'] or 'TBD'}")
    return '\n'.join(lines)


async def expire_tournament_matches()->list[dict]:
    actions=[]
    with get_connection() as c:
        rows=c.execute("SELECT * FROM creator_tournament_matches WHERE status IN ('pending','waiting') AND deadline<CURRENT_TIMESTAMP").fetchall()
    for m in rows:
        if bool(m['player1_ready_at']) ^ bool(m['player2_ready_at']):
            winner=int(m['player1_user_id'] if m['player1_ready_at'] else m['player2_user_id']); await complete_match(int(m['id']),winner,None,None,'walkover');actions.append({'match_id':m['id'],'winner':winner})
        elif not m['player1_ready_at'] and not m['player2_ready_at']:
            with get_connection() as c:c.execute("UPDATE creator_tournament_matches SET status='problem' WHERE id=? AND status IN ('pending','waiting')",(m['id'],));_log(c,m['tournament_id'],None,'problem_match',{'match_id':m['id']});c.commit()
    return actions
