from __future__ import annotations

import json
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.db import ensure_column, get_connection
from app.services.rewards import grant_currency, grant_pack

ALLOWED_SIZES = {2, 4, 8, 16, 32}
ALLOWED_DURATIONS = {30, 60, 180, 360, 720, 1440}

# --- Match state machine (см. docs/TOURNAMENT_RELIABILITY_SPEC.md) ---
# 'pending' — легаси-синоним 'waiting' (существующие строки в проде), оба значения
# везде трактуются одинаково — не мигрируем старые строки, только новый код пишет
# 'waiting'.
STATUS_WAITING = "waiting"
STATUS_PLAYING = "playing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
LEGACY_WAITING_STATUSES = ("pending", "waiting")
# 'problem' — легаси dead-end статус из старой версии кода, трактуется как 'failed'
# для целей отображения/восстановления, отдельно не мигрируется.
LEGACY_FAILED_STATUSES = ("problem", "failed")

SUSPICIOUS_AFTER_MINUTES = 15
FAIL_AFTER_MINUTES = 30
PENDING_RESULT_TTL_MINUTES = 30

MAX_SCORE = 30
_SCORE_PATTERN = re.compile(r"^\s*(\d{1,3})\s*(?:[:\-–—]|\s)\s*(\d{1,3})\s*$")

INVITE_TOKEN_BYTES = 9
INVITE_PAYLOAD_PREFIX = "ct_"


def _new_invite_token() -> str:
    return secrets.token_urlsafe(INVITE_TOKEN_BYTES)


def invite_payload(token: str) -> str:
    return f"{INVITE_PAYLOAD_PREFIX}{token}"


def parse_invite_payload(payload: str | None) -> str | None:
    value = str(payload or "").strip()
    if not value.startswith(INVITE_PAYLOAD_PREFIX):
        return None
    token = value[len(INVITE_PAYLOAD_PREFIX):].strip()
    if not token or len(token) > 48 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return None
    return token



def parse_score_text(text: str | None) -> tuple[int, int] | None:
    """Разбирает счёт матча: "3:2", "3-2", "3 — 2", "3 2". Отклоняет ничью,
    отрицательные/пустые/множественные значения и значения выше MAX_SCORE."""
    if not text:
        return None
    match = _SCORE_PATTERN.match(text.strip())
    if not match:
        return None
    score1, score2 = int(match.group(1)), int(match.group(2))
    if score1 > MAX_SCORE or score2 > MAX_SCORE:
        return None
    if score1 == score2:
        return None
    return score1, score2


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
        """CREATE TABLE IF NOT EXISTS creator_tournament_pending_results (id INTEGER PRIMARY KEY AUTOINCREMENT, creator_user_id INTEGER NOT NULL, tournament_id INTEGER NOT NULL, match_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, prompt_message_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', FOREIGN KEY(tournament_id) REFERENCES creator_tournaments(id) ON DELETE CASCADE, FOREIGN KEY(match_id) REFERENCES creator_tournament_matches(id) ON DELETE CASCADE)""",
        "CREATE INDEX IF NOT EXISTS idx_creator_tournaments_status ON creator_tournaments(status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_creator_tournament_matches_deadline ON creator_tournament_matches(status,deadline)",
        "CREATE INDEX IF NOT EXISTS idx_creator_pending_results_creator ON creator_tournament_pending_results(creator_user_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_creator_pending_results_match ON creator_tournament_pending_results(match_id,status)",
    ]
    for query in queries:
        connection.execute(query)

    # Explicit match state machine — новые поля, аддитивно (см. раздел 2 спеки).
    ensure_column(connection, "creator_tournament_matches", "started_at", "started_at TEXT")
    ensure_column(connection, "creator_tournament_matches", "last_activity_at", "last_activity_at TEXT")
    ensure_column(connection, "creator_tournament_matches", "attempt_count", "attempt_count INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection, "creator_tournament_matches", "error_message", "error_message TEXT")
    ensure_column(connection, "creator_tournament_matches", "processing_token", "processing_token TEXT")
    ensure_column(connection, "creator_tournament_matches", "updated_at", "updated_at TEXT")
    ensure_column(connection, "creator_tournaments", "invite_token", "invite_token TEXT")
    ensure_column(connection, "creator_tournaments", "invite_enabled", "invite_enabled INTEGER NOT NULL DEFAULT 1")

    missing = connection.execute(
        "SELECT id FROM creator_tournaments WHERE invite_token IS NULL OR invite_token = ''"
    ).fetchall()
    for row in missing:
        while True:
            token = _new_invite_token()
            exists = connection.execute(
                "SELECT 1 FROM creator_tournaments WHERE invite_token = ? LIMIT 1", (token,)
            ).fetchone()
            if not exists:
                connection.execute(
                    "UPDATE creator_tournaments SET invite_token = ? WHERE id = ?",
                    (token, int(row["id"])),
                )
                break
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_tournaments_invite_token ON creator_tournaments(invite_token)"
    )

    # R11 recovery: до этого любой отказ play_player_match() превращался в
    # ``failed / Составы не готовы``, хотя функция возвращает (None, None) также
    # при занятом global match lock. Такие матчи становились тупиковыми в панели
    # креатора. Возвращаем только строки со старой ТОЧНОЙ ошибкой в waiting;
    # завершённые/отменённые матчи и любые другие ошибки не трогаем.
    connection.execute(
        """
        UPDATE creator_tournament_matches
        SET status = 'waiting',
            player1_ready_at = NULL,
            player2_ready_at = NULL,
            started_at = NULL,
            processing_token = NULL,
            error_message = NULL,
            last_activity_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('failed', 'problem')
          AND winner_user_id IS NULL
          AND error_message = 'Составы не готовы к матчу.'
        """
    )


def _log(c, tournament_id: int, actor: int | None, action: str, details: Any='') -> None:
    c.execute('INSERT INTO creator_tournament_logs(tournament_id,actor_user_id,action,details) VALUES(?,?,?,?)', (tournament_id,actor,action,json.dumps(details,ensure_ascii=False) if not isinstance(details,str) else details))
    from app.services import audit_log
    audit_log.record(c, actor, f'tournament:{action}', 'creator_tournament', tournament_id, details)


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
        invite_token = _new_invite_token()
        while c.execute('SELECT 1 FROM creator_tournaments WHERE invite_token=? LIMIT 1',(invite_token,)).fetchone():
            invite_token = _new_invite_token()
        cur=c.execute('INSERT INTO creator_tournaments(creator_user_id,title,description,capacity,round_duration_minutes,invite_token,invite_enabled) VALUES(?,?,?,?,?,?,1)',(creator_user_id,title.strip(),description.strip(),capacity,duration,invite_token))
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


async def get_tournament_invite(tournament_id: int) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute(
            """
            SELECT t.*, u.nickname AS creator_nickname,
                   (SELECT COUNT(*) FROM creator_tournament_participants p WHERE p.tournament_id=t.id) AS participants_count
            FROM creator_tournaments t
            LEFT JOIN users u ON u.id=t.creator_user_id
            WHERE t.id=?
            """, (tournament_id,),
        ).fetchone()
    return dict(row) if row else None


async def get_tournament_by_invite_token(token: str) -> dict[str, Any] | None:
    token = str(token or "").strip()
    if not token:
        return None
    with get_connection() as c:
        row = c.execute(
            """
            SELECT t.*, u.nickname AS creator_nickname,
                   (SELECT COUNT(*) FROM creator_tournament_participants p WHERE p.tournament_id=t.id) AS participants_count
            FROM creator_tournaments t
            LEFT JOIN users u ON u.id=t.creator_user_id
            WHERE t.invite_token=? AND t.invite_enabled=1
            """, (token,),
        ).fetchone()
    return dict(row) if row else None


async def ensure_tournament_invite_token(tournament_id: int, creator_user_id: int | None = None) -> str | None:
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT creator_user_id,invite_token FROM creator_tournaments WHERE id=?", (tournament_id,)
        ).fetchone()
        if not row or (creator_user_id is not None and int(row["creator_user_id"]) != int(creator_user_id)):
            c.rollback()
            return None
        token = str(row["invite_token"] or "").strip()
        if not token:
            while True:
                token = _new_invite_token()
                if not c.execute("SELECT 1 FROM creator_tournaments WHERE invite_token=? LIMIT 1", (token,)).fetchone():
                    break
            c.execute(
                "UPDATE creator_tournaments SET invite_token=?,invite_enabled=1 WHERE id=?",
                (token, tournament_id),
            )
        c.commit()
        return token


async def is_tournament_participant(tournament_id: int, user_id: int) -> bool:
    with get_connection() as c:
        row = c.execute(
            "SELECT 1 FROM creator_tournament_participants WHERE tournament_id=? AND user_id=? LIMIT 1",
            (tournament_id, user_id),
        ).fetchone()
    return row is not None


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


async def _mark_match_failed(match_id: int, error_message: str) -> None:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m = c.execute('SELECT tournament_id,status FROM creator_tournament_matches WHERE id=?', (match_id,)).fetchone()
        if not m or m['status'] == STATUS_COMPLETED:
            c.rollback(); return
        c.execute(
            "UPDATE creator_tournament_matches SET status=?,error_message=?,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (STATUS_FAILED, (error_message or '')[:500], match_id),
        )
        _log(c, int(m['tournament_id']), None, 'match_failed', {'match_id': match_id, 'error': error_message})
        c.commit()


async def _tournament_lineup_problem(player1_user_id: int, player2_user_id: int) -> str | None:
    """Проверяет оба обычных состава ДО перевода турнирного матча в playing.

    Старый код узнавал о неполном составе только по ``(None, None)`` от
    play_player_match(), но такой же результат возвращается при занятом match lock.
    Из-за этого реальная причина терялась и матч ошибочно помечался зависшим.
    """
    from app.services.lineup import get_lineup_overview

    with get_connection() as c:
        rows = c.execute(
            "SELECT id,nickname FROM users WHERE id IN (?,?)",
            (player1_user_id, player2_user_id),
        ).fetchall()
    names = {int(row['id']): (row['nickname'] or f"Игрок {row['id']}") for row in rows}

    problems: list[str] = []
    for uid in (player1_user_id, player2_user_id):
        overview = await get_lineup_overview(uid)
        if not overview.is_complete or overview.average_overall is None:
            problems.append(f"{names.get(uid, f'Игрок {uid}')} ({overview.filled_count}/{overview.total_slots})")
    if not problems:
        return None
    return "Не готов состав: " + ", ".join(problems) + ". Заполните 3 FWD, 2 DEF и 1 G."


async def _tournament_busy_problem(player1_user_id: int, player2_user_id: int) -> str | None:
    """Возвращает понятную причину, если участник уже занят другим режимом."""
    from app.services import match_guard

    with get_connection() as c:
        rows = c.execute(
            "SELECT id,nickname FROM users WHERE id IN (?,?)",
            (player1_user_id, player2_user_id),
        ).fetchall()
    names = {int(row['id']): (row['nickname'] or f"Игрок {row['id']}") for row in rows}

    for uid in (player1_user_id, player2_user_id):
        lock = await match_guard.get_active_match(uid)
        if lock is None:
            continue
        label = match_guard.MATCH_TYPE_LABELS.get(lock.match_type, lock.match_type)
        return f"{names.get(uid, f'Игрок {uid}')} сейчас занят в режиме «{label}». Завершите тот матч и повторите запуск турнира."
    return None


async def _return_match_to_waiting(match_id: int, message: str) -> None:
    """Транзиентная проблема (занят другой матч) не должна превращать матч в failed."""
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m = c.execute(
            'SELECT tournament_id,status FROM creator_tournament_matches WHERE id=?',
            (match_id,),
        ).fetchone()
        if not m or m['status'] == STATUS_COMPLETED:
            c.rollback()
            return
        c.execute(
            """
            UPDATE creator_tournament_matches
            SET status=?, started_at=NULL, processing_token=NULL, error_message=?,
                last_activity_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (STATUS_WAITING, (message or '')[:500], match_id),
        )
        _log(c, int(m['tournament_id']), None, 'match_waiting_retry', {'match_id': match_id, 'reason': message})
        c.commit()


async def mark_ready_and_play(match_id:int,user_id:int)->tuple[bool,str,dict|None]:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m=c.execute("SELECT * FROM creator_tournament_matches WHERE id=? AND status IN (?,?)",(match_id,*LEGACY_WAITING_STATUSES)).fetchone()
        if not m or user_id not in (m['player1_user_id'],m['player2_user_id']): c.rollback(); return False,'Матч недоступен.',None
        col='player1_ready_at' if user_id==m['player1_user_id'] else 'player2_ready_at'
        c.execute(f'UPDATE creator_tournament_matches SET {col}=COALESCE({col},CURRENT_TIMESTAMP),status=?,error_message=NULL,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?',(STATUS_WAITING,match_id))
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m['player1_ready_at'] or not m['player2_ready_at']:
            c.commit(); return True,'Ожидаем соперника...',None
        p1=int(m['player1_user_id']); p2=int(m['player2_user_id'])
        users=c.execute('SELECT id,telegram_id FROM users WHERE id IN (?,?)',(p1,p2)).fetchall()
        c.commit()

    # Важно: readiness игроков и готовность их обычных составов — разные вещи.
    # Проверяем составы ДО status=playing, чтобы неполный ростер не создавал
    # «зависший» матч, который потом должен чинить креатор.
    lineup_problem = await _tournament_lineup_problem(p1, p2)
    if lineup_problem:
        await _return_match_to_waiting(match_id, lineup_problem)
        return False, lineup_problem, None

    # То же для глобального межрежимного lock: занятой Clan War/Ranked/обычный
    # матч — это временное состояние, а не поломка турнирной сетки.
    busy_problem = await _tournament_busy_problem(p1, p2)
    if busy_problem:
        await _return_match_to_waiting(match_id, busy_problem)
        return False, busy_problem, None

    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        changed=c.execute(
            "UPDATE creator_tournament_matches SET status=?,started_at=CURRENT_TIMESTAMP,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,attempt_count=attempt_count+1,error_message=NULL WHERE id=? AND status=?",
            (STATUS_PLAYING,match_id,STATUS_WAITING),
        ).rowcount
        if not changed: c.rollback(); return False,'Матч уже запускается.',None
        c.commit()

    tele={int(r['id']):int(r['telegram_id']) for r in users}
    if p1 not in tele or p2 not in tele:
        await _mark_match_failed(match_id, 'Не найден Telegram-профиль одного из участников.')
        return False,'Не удалось запустить матч: профиль участника недоступен.',None

    from app.services.matches import play_player_match
    try:
        r1,r2=await play_player_match(tele[p1],tele[p2],match_type='tournament')
    except Exception as error:
        from app.services import error_log
        error_log.record_error('creator_tournaments.mark_ready_and_play', error, context=f'match_id={match_id}')
        await _mark_match_failed(match_id, str(error))
        return False,'Не удалось запустить матч. Создатель турнира уведомлён и может восстановить матч.',None
    if not r1 or not r2:
        # Между preflight и acquire могла произойти гонка: участник успел начать
        # другой матч. Это НЕ failed — возвращаем пару в waiting и позволяем
        # повторить запуск после освобождения lock.
        busy_problem = await _tournament_busy_problem(p1, p2)
        if busy_problem:
            await _return_match_to_waiting(match_id, busy_problem)
            return False, busy_problem, None
        lineup_problem = await _tournament_lineup_problem(p1, p2)
        if lineup_problem:
            await _return_match_to_waiting(match_id, lineup_problem)
            return False, lineup_problem, None
        await _mark_match_failed(match_id, 'Движок матча не вернул результат после успешной проверки составов и блокировок.')
        return False,'Не удалось завершить симуляцию. Создатель турнира может перезапустить матч.',None
    winner=p1 if r1.user_score>r1.opponent_score else p2
    await complete_match(match_id,winner,r1.user_score,r1.opponent_score,'played')
    return True,'Матч завершён.',{'score1':r1.user_score,'score2':r1.opponent_score,'winner_user_id':winner}


async def complete_match(match_id:int,winner_id:int,score1:int|None=None,score2:int|None=None,decided_by:str='manual')->None:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE'); m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m or m['status']=='completed': c.rollback(); return
        loser=int(m['player2_user_id'] if winner_id==m['player1_user_id'] else m['player1_user_id'])
        c.execute("UPDATE creator_tournament_matches SET winner_user_id=?,loser_user_id=?,score1=?,score2=?,status='completed',decided_by=?,error_message=NULL,completed_at=CURRENT_TIMESTAMP,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(winner_id,loser,score1,score2,decided_by,match_id))
        _log(c,int(m['tournament_id']),winner_id,'match_completed',{'match_id':match_id,'by':decided_by,'score':f'{score1}:{score2}'})
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
        # ВАЖНО: было 9 value-выражений (8 "?" + буквальная "1") на 8 колонок —
        # SQLite бросал "9 values for 8 columns" при каждом турнире с 4+ участниками,
        # ровно на этапе создания матча за 3-е место после полуфиналов. Плюс params
        # был короче на один элемент (is_third_place передавался литералом мимо
        # биндинга). Исправлено: is_third_place передаётся обычным параметром.
        c.execute('INSERT OR IGNORE INTO creator_tournament_matches(tournament_id,round_no,round_name,bracket_index,player1_user_id,player2_user_id,deadline,is_third_place) VALUES(?,?,?,?,?,?,?,?)',(tid,rn,'Матч за 3 место',0,losers[0],losers[1],deadline,1))


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
        rows=c.execute("SELECT * FROM creator_tournament_matches WHERE status IN (?,?) AND deadline IS NOT NULL AND deadline<CURRENT_TIMESTAMP",LEGACY_WAITING_STATUSES).fetchall()
    for m in rows:
        if bool(m['player1_ready_at']) ^ bool(m['player2_ready_at']):
            winner=int(m['player1_user_id'] if m['player1_ready_at'] else m['player2_user_id']); await complete_match(int(m['id']),winner,None,None,'walkover');actions.append({'match_id':m['id'],'winner':winner})
        elif not m['player1_ready_at'] and not m['player2_ready_at']:
            with get_connection() as c:
                c.execute('BEGIN IMMEDIATE')
                changed=c.execute("UPDATE creator_tournament_matches SET status=?,error_message='Оба игрока не отметились до дедлайна.',last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN (?,?)",(STATUS_FAILED,m['id'],*LEGACY_WAITING_STATUSES)).rowcount
                if changed:_log(c,m['tournament_id'],None,'problem_match',{'match_id':m['id']})
                c.commit()
            if changed:actions.append({'match_id':m['id'],'action':'no_show_failed'})

    # Матчи, зависшие в 'playing' дольше FAIL_AFTER_MINUTES — переводим в 'failed' с
    # причиной, чтобы креатор увидел кнопки восстановления (раздел 3 спеки). Матчи
    # 15-30 минут в 'playing' считаются лишь "подозрительными" и не трогаются здесь —
    # они видны через find_matches_needing_attention() для панели креатора.
    with get_connection() as c:
        stale=c.execute(
            "SELECT id,tournament_id FROM creator_tournament_matches WHERE status=? AND last_activity_at IS NOT NULL AND last_activity_at<datetime('now',?)",
            (STATUS_PLAYING,f'-{FAIL_AFTER_MINUTES} minutes'),
        ).fetchall()
    for m in stale:
        await _mark_match_failed(int(m['id']),f'Матч завис в статусе playing более {FAIL_AFTER_MINUTES} минут.')
        actions.append({'match_id':m['id'],'action':'stale_playing_failed'})
    return actions


async def find_matches_needing_attention(tournament_id:int|None=None)->list[dict]:
    """Матчи, зависшие в playing дольше SUSPICIOUS_AFTER_MINUTES, или в failed/problem."""
    query=(
        "SELECT m.*,u1.nickname n1,u2.nickname n2,t.creator_user_id,t.title tournament_title "
        "FROM creator_tournament_matches m "
        "LEFT JOIN users u1 ON u1.id=m.player1_user_id "
        "LEFT JOIN users u2 ON u2.id=m.player2_user_id "
        "JOIN creator_tournaments t ON t.id=m.tournament_id "
        "WHERE (m.status=? AND m.last_activity_at IS NOT NULL AND m.last_activity_at<datetime('now',?)) "
        "OR m.status IN (?,?)"
    )
    params:list[Any]=[STATUS_PLAYING,f'-{SUSPICIOUS_AFTER_MINUTES} minutes',STATUS_FAILED,'problem']
    if tournament_id is not None:
        query+=' AND m.tournament_id=?'; params.append(tournament_id)
    query+=' ORDER BY m.last_activity_at ASC, m.id ASC'
    with get_connection() as c:
        rows=c.execute(query,params).fetchall()
    return [dict(r) for r in rows]


async def _check_creator(tournament_id:int,actor_user_id:int,c=None)->tuple[bool,int|None]:
    connection=c or get_connection()
    row=connection.execute('SELECT creator_user_id FROM creator_tournaments WHERE id=?',(tournament_id,)).fetchone()
    return (bool(row) and int(row['creator_user_id'])==actor_user_id),(int(row['creator_user_id']) if row else None)


async def restart_match(match_id:int,actor_user_id:int)->tuple[bool,str]:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m: c.rollback(); return False,'Матч не найден.'
        if m['status']=='completed': c.rollback(); return False,f"Матч уже завершён со счётом {m['score1']}:{m['score2']}."
        ok,_=await _check_creator(int(m['tournament_id']),actor_user_id,c)
        if not ok: c.rollback(); return False,'Только создатель турнира может перезапустить матч.'
        if m['status'] not in (STATUS_PLAYING,STATUS_FAILED,'problem'):
            c.rollback(); return False,'Перезапуск доступен только для зависших или ошибочных матчей.'
        c.execute(
            "UPDATE creator_tournament_matches SET status=?,player1_ready_at=NULL,player2_ready_at=NULL,attempt_count=attempt_count+1,error_message=NULL,started_at=NULL,processing_token=NULL,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (STATUS_WAITING,match_id),
        )
        _log(c,int(m['tournament_id']),actor_user_id,'match_restarted',{'match_id':match_id,'attempt':int(m['attempt_count'] or 0)+1})
        c.commit()
    return True,'Матч перезапущен. Игроки могут отметиться заново.'


async def cancel_match(match_id:int,actor_user_id:int,reason:str='')->tuple[bool,str]:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m: c.rollback(); return False,'Матч не найден.'
        if m['status']=='completed': c.rollback(); return False,f"Матч уже завершён со счётом {m['score1']}:{m['score2']}."
        ok,_=await _check_creator(int(m['tournament_id']),actor_user_id,c)
        if not ok: c.rollback(); return False,'Только создатель турнира может отменить матч.'
        c.execute(
            "UPDATE creator_tournament_matches SET status=?,error_message=?,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (STATUS_CANCELLED,(reason or 'Отменено создателем турнира.')[:500],match_id),
        )
        _log(c,int(m['tournament_id']),actor_user_id,'match_cancelled',{'match_id':match_id,'reason':reason})
        c.commit()
    return True,'Матч отменён.'


async def force_simulate_match(match_id:int,actor_user_id:int)->tuple[bool,str,dict|None]:
    with get_connection() as c:
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m: return False,'Матч не найден.',None
        if m['status']=='completed': return False,f"Матч уже завершён со счётом {m['score1']}:{m['score2']}.",None
        ok,_=await _check_creator(int(m['tournament_id']),actor_user_id)
        if not ok: return False,'Только создатель турнира может запустить симуляцию.',None
        if not m['player1_user_id'] or not m['player2_user_id']: return False,'Оба участника матча ещё не определены.',None
        p1=int(m['player1_user_id']); p2=int(m['player2_user_id'])
        users=c.execute('SELECT id,telegram_id FROM users WHERE id IN (?,?)',(p1,p2)).fetchall()

    lineup_problem = await _tournament_lineup_problem(p1, p2)
    if lineup_problem:
        await _return_match_to_waiting(match_id, lineup_problem)
        return False, lineup_problem, None
    busy_problem = await _tournament_busy_problem(p1, p2)
    if busy_problem:
        await _return_match_to_waiting(match_id, busy_problem)
        return False, busy_problem, None

    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        changed=c.execute(
            "UPDATE creator_tournament_matches SET status=?,started_at=CURRENT_TIMESTAMP,last_activity_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,attempt_count=attempt_count+1,error_message=NULL WHERE id=? AND status!='completed'",
            (STATUS_PLAYING,match_id),
        ).rowcount
        c.commit()
    if not changed: return False,'Матч уже обрабатывается или завершён.',None
    tele={int(r['id']):int(r['telegram_id']) for r in users}
    if p1 not in tele or p2 not in tele:
        await _mark_match_failed(match_id,'Не найден Telegram-профиль одного из участников.')
        return False,'Не удалось запустить симуляцию: профиль участника недоступен.',None
    from app.services.matches import play_player_match
    try:
        r1,r2=await play_player_match(tele[p1],tele[p2],match_type='tournament')
    except Exception as error:
        await _mark_match_failed(match_id,str(error)); return False,'Не удалось запустить симуляцию.',None
    if not r1 or not r2:
        busy_problem = await _tournament_busy_problem(p1, p2)
        if busy_problem:
            await _return_match_to_waiting(match_id, busy_problem)
            return False,busy_problem,None
        lineup_problem = await _tournament_lineup_problem(p1, p2)
        if lineup_problem:
            await _return_match_to_waiting(match_id, lineup_problem)
            return False,lineup_problem,None
        await _mark_match_failed(match_id,'Движок матча не вернул результат после успешной проверки составов и блокировок.')
        return False,'Не удалось завершить симуляцию.',None
    winner=p1 if r1.user_score>r1.opponent_score else p2
    await complete_match(match_id,winner,r1.user_score,r1.opponent_score,'creator_simulation')
    with get_connection() as c:
        _log(c,int(m['tournament_id']),actor_user_id,'match_force_simulated',{'match_id':match_id}); c.commit()
    return True,'Матч завершён симуляцией.',{'score1':r1.user_score,'score2':r1.opponent_score,'winner_user_id':winner}


async def submit_manual_result(match_id:int,actor_user_id:int,score1:int,score2:int,source:str='creator_manual')->tuple[bool,str]:
    with get_connection() as c:
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        if not m: return False,'Матч не найден.'
        if m['status']=='completed': return False,f"Матч уже завершён со счётом {m['score1']}:{m['score2']}."
        ok,_=await _check_creator(int(m['tournament_id']),actor_user_id)
        if not ok: return False,'Только создатель турнира может назначить результат.'
        if not m['player1_user_id'] or not m['player2_user_id']: return False,'Оба участника матча ещё не определены.'
    winner=int(m['player1_user_id']) if score1>score2 else int(m['player2_user_id'])
    await complete_match(match_id,winner,score1,score2,source)
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        fresh=c.execute('SELECT status,score1,score2 FROM creator_tournament_matches WHERE id=?',(match_id,)).fetchone()
        _log(c,int(m['tournament_id']),actor_user_id,'manual_result',{'match_id':match_id,'score':f'{score1}:{score2}'})
        c.commit()
    if fresh and fresh['status']=='completed':
        return True,f"Результат сохранён: {fresh['score1']}:{fresh['score2']}."
    return False,'Не удалось сохранить результат.'


async def create_pending_result(creator_user_id:int,tournament_id:int,match_id:int,chat_id:int)->tuple[bool,str,int|None]:
    """Создаёт ожидание ввода результата — переживает restart/redeploy (хранится в БД,
    не в aiogram FSM). Одно активное ожидание на креатора одновременно."""
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        m=c.execute('SELECT * FROM creator_tournament_matches WHERE id=? AND tournament_id=?',(match_id,tournament_id)).fetchone()
        if not m: c.rollback(); return False,'Матч не найден.',None
        if m['status']=='completed': c.rollback(); return False,f"Матч уже завершён со счётом {m['score1']}:{m['score2']}.",None
        t=c.execute('SELECT creator_user_id FROM creator_tournaments WHERE id=?',(tournament_id,)).fetchone()
        if not t or int(t['creator_user_id'])!=creator_user_id: c.rollback(); return False,'Только создатель турнира может назначить результат.',None
        c.execute("UPDATE creator_tournament_pending_results SET status='cancelled' WHERE creator_user_id=? AND status='pending'",(creator_user_id,))
        expires=_dt(_utcnow()+timedelta(minutes=PENDING_RESULT_TTL_MINUTES))
        cur=c.execute('INSERT INTO creator_tournament_pending_results(creator_user_id,tournament_id,match_id,chat_id,expires_at) VALUES(?,?,?,?,?)',(creator_user_id,tournament_id,match_id,chat_id,expires))
        pending_id=int(cur.lastrowid)
        c.commit()
    return True,'ok',pending_id


async def set_pending_result_prompt_message(pending_id:int,message_id:int)->None:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('UPDATE creator_tournament_pending_results SET prompt_message_id=? WHERE id=?',(message_id,pending_id))
        c.commit()


async def get_active_pending_result(creator_user_id:int)->dict|None:
    with get_connection() as c:
        row=c.execute("SELECT * FROM creator_tournament_pending_results WHERE creator_user_id=? AND status='pending' AND expires_at>CURRENT_TIMESTAMP ORDER BY id DESC LIMIT 1",(creator_user_id,)).fetchone()
    return dict(row) if row else None


async def cancel_pending_result(creator_user_id:int)->bool:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        changed=c.execute("UPDATE creator_tournament_pending_results SET status='cancelled' WHERE creator_user_id=? AND status='pending'",(creator_user_id,)).rowcount
        c.commit()
    return bool(changed)


async def resolve_pending_result(pending_id:int)->None:
    with get_connection() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE creator_tournament_pending_results SET status='completed' WHERE id=?",(pending_id,))
        c.commit()
