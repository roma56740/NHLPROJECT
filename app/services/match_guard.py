"""ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK — капча перед стартом (#3) и физическая, на уровне
БД, блокировка одновременных матчей одного пользователя (#2), общая для ВСЕХ
игровых режимов (Ranked, The Stronghold, Clan War 2, обычные матчи/матчмейкинг,
турниры, и любых будущих режимов, вызывающих `app.services.matches`).

Источник правды — таблица `player_match_locks` (см. app/database/schema.py) с
partial unique index по `user_id` для активных статусов (ACQUIRING/ACTIVE/
RESOLVING). Это физическое ограничение SQLite: второй `INSERT` с тем же user_id и
активным статусом получает `sqlite3.IntegrityError` НЕЗАВИСИМО от того, сколько
процессов/воркеров бота сейчас запущено и сколько запросов пришло одновременно —
"SELECT потом INSERT" здесь не используется как единственная защита (это было бы
гонкой), UNIQUE-индекс — это гарантия на уровне файла БД.

Старая таблица `active_matches` (PRIMARY KEY user_id, только started_at) НЕ
удаляется и не используется новым кодом — она была самодостаточной для
Ranked/Stronghold/Clan War 2 (там её реально дергали перед стартом), но НЕ была
подключена вообще нигде в обычном режиме/матчмейкинге/турнирах (`app.services.
matches.py`: `play_quick_match`/`play_player_match` создавали и сохраняли
результат матча без единого вызова guard). Обычный режим и турниры используют
`play_player_match`/`play_quick_match` из `app.services.matches` — единственная
"общая точка", которая теперь и получает lock, поэтому все текущие и будущие
режимы, вызывающие эти функции, защищены автоматически.

`try_acquire_match_lock()`/`release_match_lock()`/`has_active_match()` оставлены
как совместимые обёртки (их уже вызывают ranked_core.py/stronghold_fortress.py/
stronghold_endless.py/war2_core.py/handlers/matches.py/stronghold_upgrade.py) —
они переведены на новую таблицу, поэтому даже необновлённый вызывающий код
автоматически получает межрежимную защиту. Каждая из этих точек, однако,
обновлена в этой сессии на использование новой явной сигнатуры с match_type для
диагностики (см. PATCH_NOTES.md).
"""

from __future__ import annotations

import logging
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.database.db import get_connection

logger = logging.getLogger(__name__)

CAPTCHA_TTL_SECONDS = 30

# Активные (не завершённые) статусы — ровно эти участвуют в partial unique index
# idx_player_match_locks_active_user (см. app/database/schema.py). Изменение этого
# списка ТРЕБУЕТ синхронного изменения индекса в schema.py.
ACTIVE_LOCK_STATUSES = ("ACQUIRING", "ACTIVE", "RESOLVING")
TERMINAL_LOCK_STATUSES = ("COMPLETED", "CANCELLED", "EXPIRED", "FAILED")

# TTL по типу матча. Инстант-режимы (Ranked/Stronghold/обычный/турниры) считают
# матч синхронно за один вызов (симуляция + запись результата в одной операции,
# без промежуточного "идёт" состояния, которое могло бы пережить рестарт) —
# короткого TTL достаточно, он лишь страхует от упавшего процесса/зависшего
# запроса. CLAN WAR 2.0 — единственный режим с реальной многошаговой фазой
# ожидания ввода игрока (драфт) — получает значительно больший TTL, чтобы
# истечение lock не могло случиться, пока пользователь ещё реально в драфте.
DEFAULT_TTL_SECONDS = 300
MATCH_TYPE_TTL_SECONDS: dict[str, int] = {
    "normal": 300,
    "normal_pvp": 300,
    "ranked": 300,
    "stronghold_fortress": 300,
    "stronghold_endless": 300,
    "tournament": 300,
    "war2": 1800,
    "legacy": 300,
}

# Обратная совместимость: старое имя константы, которое могло использоваться где-то
# ещё (не найдено вызовов вне этого файла на момент рефакторинга, оставлено на
# случай внешних потребителей).
ACTIVE_MATCH_TTL_SECONDS = MATCH_TYPE_TTL_SECONDS["normal"]

_EMOJI_POOL = ["🏒", "🥅", "🏆", "⚡", "🔥", "⭐", "🎯", "🧤"]


@dataclass(frozen=True)
class Captcha:
    prompt: str
    correct: str
    options: list[str]


def generate_captcha() -> Captcha:
    """Простая проверка: выбрать нужную цифру среди 4 вариантов."""
    numbers = random.sample(range(1, 10), 4)
    correct = random.choice(numbers)
    return Captcha(
        prompt=f"Нажми число <b>{correct}</b>, чтобы начать матч",
        correct=str(correct),
        options=[str(n) for n in numbers],
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def _fmt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def ttl_for(match_type: str) -> int:
    return MATCH_TYPE_TTL_SECONDS.get(match_type, DEFAULT_TTL_SECONDS)


@dataclass(frozen=True)
class LockInfo:
    id: int
    user_id: int
    match_id: int | None
    match_type: str
    status: str
    request_id: str | None
    acquired_at: str | None
    heartbeat_at: str | None
    expires_at: str | None
    released_at: str | None
    release_reason: str | None


def _row_to_lock_info(row: sqlite3.Row) -> LockInfo:
    return LockInfo(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        match_id=int(row["match_id"]) if row["match_id"] is not None else None,
        match_type=row["match_type"],
        status=row["status"],
        request_id=row["request_id"],
        acquired_at=row["acquired_at"],
        heartbeat_at=row["heartbeat_at"],
        expires_at=row["expires_at"],
        released_at=row["released_at"],
        release_reason=row["release_reason"],
    )


def _is_expired(lock: LockInfo, now: datetime) -> bool:
    expires = _parse(lock.expires_at)
    return expires is not None and now >= expires


@dataclass(frozen=True)
class LockAcquireResult:
    acquired: bool
    lock_id: int | None
    idempotent_replay: bool
    existing: LockInfo | None


async def get_active_match(user_id: int) -> LockInfo | None:
    """Текущая активная (ACQUIRING/ACTIVE/RESOLVING) блокировка пользователя, если
    есть — используется и для UI ("у вас уже есть активный матч"), и внутри
    acquire-конфликта, и диагностикой."""
    placeholders = ",".join("?" for _ in ACTIVE_LOCK_STATUSES)
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM player_match_locks WHERE user_id = ? AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",
            (user_id, *ACTIVE_LOCK_STATUSES),
        ).fetchone()
    return _row_to_lock_info(row) if row is not None else None


async def _check_match_status(match_type: str, match_id: int | None) -> str:
    """'missing' | 'completed' | 'running' | 'unknown' — используется recovery,
    чтобы НЕ аннулировать реально идущий матч. Ленивые импорты внутри функции —
    иначе циклический импорт (ranked_core/war2_core и т.д. импортируют этот
    модуль на верхнем уровне).

    Сейчас реальное "running" (матч ещё физически идёт спустя TTL) возможно
    только для Clan War 2.0 (фаза 'drafting' — единственный режим с ожиданием
    ввода игрока между стартом и завершением). Ranked/Stronghold/обычный
    режим/турниры считают матч синхронно за один вызов (симуляция и запись
    результата — одна операция без паузы на ввод), поэтому для них "match_id
    отсутствует или не найден" всегда значит "процесс упал/завис", а не "матч
    ещё реально идёт"."""
    if match_id is None:
        return "missing"

    if match_type == "war2":
        with get_connection() as connection:
            row = connection.execute("SELECT status FROM war2_matches WHERE id = ?", (match_id,)).fetchone()
        if row is None:
            return "missing"
        return "running" if row["status"] == "drafting" else "completed"

    if match_type == "ranked":
        with get_connection() as connection:
            row = connection.execute("SELECT id FROM ranked_matches WHERE id = ?", (match_id,)).fetchone()
        return "completed" if row is not None else "missing"

    if match_type in ("normal", "normal_pvp", "tournament", "stronghold_fortress", "stronghold_endless", "legacy"):
        with get_connection() as connection:
            row = connection.execute("SELECT id FROM matches WHERE id = ?", (match_id,)).fetchone()
        return "completed" if row is not None else "missing"

    return "unknown"


async def acquire_player_match_lock(
    user_id: int,
    match_type: str,
    *,
    request_id: str | None = None,
    ttl_seconds: int | None = None,
) -> LockAcquireResult:
    """Атомарно получает глобальный lock пользователя. НЕ полагается на "SELECT
    потом INSERT" — INSERT либо проходит (partial unique index свободен), либо
    padает с IntegrityError (индекс занят), и только тогда мы читаем существующую
    запись, чтобы решить: это idempotent-повтор того же request_id, устаревший
    (TTL истёк + матч по факту отсутствует/завершён) lock, который можно
    безопасно снять и повторить попытку, или реально занятый пользователь — тогда
    честный отказ."""
    ttl = ttl_seconds if ttl_seconds is not None else ttl_for(match_type)

    for attempt in range(2):
        now = utc_now()
        now_text = _fmt(now)
        expires_text = _fmt(now + timedelta(seconds=ttl))

        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO player_match_locks
                        (user_id, match_id, match_type, status, request_id, acquired_at, heartbeat_at, expires_at)
                    VALUES (?, NULL, ?, 'ACQUIRING', ?, ?, ?, ?)
                    """,
                    (user_id, match_type, request_id, now_text, now_text, expires_text),
                )
                lock_id = int(cursor.lastrowid)
                connection.commit()
                return LockAcquireResult(acquired=True, lock_id=lock_id, idempotent_replay=False, existing=None)
            except sqlite3.IntegrityError:
                connection.rollback()

        existing = await get_active_match(user_id)
        if existing is None:
            # Конфликт был, но конкурентная транзакция уже освободила lock —
            # безопасно повторить попытку.
            continue

        if request_id is not None and existing.request_id == request_id:
            return LockAcquireResult(acquired=True, lock_id=existing.id, idempotent_replay=True, existing=existing)

        if attempt == 0 and _is_expired(existing, now):
            outcome = await _check_match_status(existing.match_type, existing.match_id)
            if outcome == "missing":
                await expire_stale_lock(existing.id, reason="ACQUIRE_TIME_RECOVERY_MISSING_MATCH")
                logger.warning(
                    "match_guard: recovered stale lock at acquire time (user_id=%s, lock_id=%s, match_type=%s)",
                    user_id, existing.id, existing.match_type,
                )
                continue
            if outcome == "completed":
                await release_player_match_lock(user_id, status="COMPLETED", reason="ACQUIRE_TIME_RECOVERY_ALREADY_COMPLETED")
                logger.warning(
                    "match_guard: recovered already-completed stale lock at acquire time (user_id=%s, lock_id=%s)",
                    user_id, existing.id,
                )
                continue
            # "running" (Clan War 2.0 драфт ещё реально идёт) или "unknown" — НЕ трогаем.

        return LockAcquireResult(acquired=False, lock_id=None, idempotent_replay=False, existing=existing)

    existing = await get_active_match(user_id)
    return LockAcquireResult(acquired=False, lock_id=None, idempotent_replay=False, existing=existing)


async def bind_lock_to_match(lock_id: int, match_id: int) -> None:
    """Привязывает созданную запись матча к уже полученному lock'у и переводит его
    ACQUIRING -> ACTIVE. Идемпотентно: если lock уже не в ACQUIRING (например,
    bind вызван повторно), запрос просто не находит строку для обновления."""
    with get_connection() as connection:
        connection.execute(
            "UPDATE player_match_locks SET match_id = ?, status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'ACQUIRING'",
            (match_id, lock_id),
        )
        connection.commit()


async def heartbeat_lock(user_id: int, *, extend_seconds: int | None = None) -> None:
    """Обновляет heartbeat_at (и опционально продлевает expires_at) для активного
    lock'а пользователя — для многошаговых режимов (Clan War 2.0 драфт), где
    критическое действие пользователя должно продлевать TTL, а не просто ждать
    его короткого умолчания."""
    now = utc_now()
    with get_connection() as connection:
        if extend_seconds is not None:
            connection.execute(
                """
                UPDATE player_match_locks
                SET heartbeat_at = ?, expires_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING')
                """,
                (_fmt(now), _fmt(now + timedelta(seconds=extend_seconds)), user_id),
            )
        else:
            connection.execute(
                """
                UPDATE player_match_locks
                SET heartbeat_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING')
                """,
                (_fmt(now), user_id),
            )
        connection.commit()


async def release_player_match_lock(user_id: int, *, status: str = "CANCELLED", reason: str = "RELEASED") -> None:
    """Общий примитив освобождения — ИДЕМПОТЕНТЕН по конструкции: WHERE ограничен
    активными статусами, поэтому повторный вызов на уже терминальной записи
    просто не находит строк для обновления (0 affected rows, никакой ошибки)."""
    if status not in TERMINAL_LOCK_STATUSES:
        raise ValueError(f"release status must be terminal, got {status!r}")
    now_text = _fmt(utc_now())
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE player_match_locks
            SET status = ?, released_at = ?, release_reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING')
            """,
            (status, now_text, reason, user_id),
        )
        connection.commit()


async def finalize_match(user_id: int, *, match_id: int | None = None, reason: str = "COMPLETED") -> None:
    """Успешное завершение матча -> COMPLETED. Идемпотентно (см.
    release_player_match_lock). Если match_id ещё не был привязан bind_lock_to_match
    (инстант-режимы часто создают запись матча и сразу же финализируют в одном
    шаге), привязывает его здесь же."""
    if match_id is not None:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE player_match_locks SET match_id = COALESCE(match_id, ?), updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING')
                """,
                (match_id, user_id),
            )
            connection.commit()
    await release_player_match_lock(user_id, status="COMPLETED", reason=reason)


async def cancel_match(user_id: int, *, reason: str = "CANCELLED") -> None:
    """Разрешённая отмена (отклонённое приглашение, отмена драфта и т.п.) -> CANCELLED."""
    await release_player_match_lock(user_id, status="CANCELLED", reason=reason)


async def expire_stale_lock(lock_id: int, *, reason: str = "TTL_EXPIRED") -> None:
    """Явное истечение КОНКРЕТНОГО lock'а по id (используется recovery, которая уже
    прочитала строку и проверила состояние реального матча) -> EXPIRED. Идемпотентно."""
    now_text = _fmt(utc_now())
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE player_match_locks
            SET status = 'EXPIRED', released_at = ?, release_reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING')
            """,
            (now_text, reason, lock_id),
        )
        connection.commit()
    logger.warning("match_guard: lock id=%s marked EXPIRED (reason=%s)", lock_id, reason)


@dataclass(frozen=True)
class RecoveryAction:
    lock_id: int
    user_id: int
    match_type: str
    match_id: int | None
    outcome: str  # "expired" | "extended" | "released_completed"


@dataclass(frozen=True)
class RecoveryReport:
    scanned: int
    actions: list[RecoveryAction]


async def recover_stale_matches() -> RecoveryReport:
    """Boot recovery / периодическая проверка: находит все активные lock'и с
    истёкшим expires_at, для каждого сначала проверяет РЕАЛЬНОЕ состояние матча
    (если он есть) — истечение lock НЕ должно автоматически аннулировать реально
    существующий валидный матч (Clan War 2.0 в драфте продлевается, а не рвётся).
    Отсутствующий/повреждённый матч -> EXPIRED. Уже фактически завершённый матч
    (гонка/пропущенный finalize) -> лock корректно закрывается как COMPLETED.
    Все автоматические действия логируются."""
    placeholders = ",".join("?" for _ in ACTIVE_LOCK_STATUSES)
    now_text = _fmt(utc_now())
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM player_match_locks WHERE status IN ({placeholders}) AND expires_at <= ? ORDER BY id",
            (*ACTIVE_LOCK_STATUSES, now_text),
        ).fetchall()

    actions: list[RecoveryAction] = []
    for row in rows:
        lock = _row_to_lock_info(row)
        outcome = await _check_match_status(lock.match_type, lock.match_id)

        if outcome == "running":
            await heartbeat_lock(lock.user_id, extend_seconds=ttl_for(lock.match_type))
            actions.append(RecoveryAction(lock.id, lock.user_id, lock.match_type, lock.match_id, "extended"))
            logger.info(
                "match_guard.recover_stale_matches: extended still-running lock id=%s user_id=%s match_type=%s",
                lock.id, lock.user_id, lock.match_type,
            )
            continue

        if outcome == "completed":
            await release_player_match_lock(lock.user_id, status="COMPLETED", reason="RECOVERY_MATCH_ALREADY_COMPLETED")
            actions.append(RecoveryAction(lock.id, lock.user_id, lock.match_type, lock.match_id, "released_completed"))
            logger.warning(
                "match_guard.recover_stale_matches: released lock for already-completed match id=%s user_id=%s match_type=%s match_id=%s",
                lock.id, lock.user_id, lock.match_type, lock.match_id,
            )
            continue

        # "missing" или "unknown" — безопасный дефолт: процесс упал/завис, реального
        # матча нет (или мы не умеем его проверить), lock не должен держать
        # пользователя заблокированным навсегда.
        await expire_stale_lock(lock.id, reason="RECOVERY_TTL_EXPIRED")
        actions.append(RecoveryAction(lock.id, lock.user_id, lock.match_type, lock.match_id, "expired"))

    if actions:
        logger.warning("match_guard.recover_stale_matches: processed %d stale lock(s)", len(actions))

    return RecoveryReport(scanned=len(rows), actions=actions)


@dataclass(frozen=True)
class TwoPlayerLockResult:
    success: bool
    first_user_id: int | None
    second_user_id: int | None
    blocked_user_id: int | None
    lock_a: LockAcquireResult | None
    lock_b: LockAcquireResult | None


async def acquire_two_player_match_lock(
    user_a: int,
    user_b: int,
    match_type: str,
    *,
    request_id: str | None = None,
    ttl_seconds: int | None = None,
) -> TwoPlayerLockResult:
    """Атомарно (насколько это возможно в SQLite — последовательно, но со строгими
    гарантиями отката) блокирует ОБОИХ участников PvP. Порядок блокировки —
    ВСЕГДА по возрастанию user_id, независимо от того, кто "первый" в вызове, —
    это единственный порядок, которым может быть заблокирован ЛЮБОЙ конкретный
    пользователь во ВСЕХ одновременных попытках его матчить с разными
    соперниками, что физически исключает deadlock/circular-wait между двумя
    параллельными запросами матчинга. Если второй участник занят — первый lock
    немедленно освобождается, никто не остаётся заблокированным навсегда."""
    if user_a == user_b:
        single = await acquire_player_match_lock(user_a, match_type, request_id=request_id, ttl_seconds=ttl_seconds)
        blocked = None if single.acquired else user_a
        return TwoPlayerLockResult(single.acquired, user_a, user_b, blocked, single, single)

    first_id, second_id = (user_a, user_b) if user_a < user_b else (user_b, user_a)

    lock_first = await acquire_player_match_lock(first_id, match_type, request_id=request_id, ttl_seconds=ttl_seconds)
    if not lock_first.acquired:
        return TwoPlayerLockResult(False, first_id, second_id, first_id, lock_first, None)

    lock_second = await acquire_player_match_lock(second_id, match_type, request_id=request_id, ttl_seconds=ttl_seconds)
    if not lock_second.acquired:
        await release_player_match_lock(first_id, status="CANCELLED", reason="PARTNER_BUSY")
        return TwoPlayerLockResult(False, first_id, second_id, second_id, None, lock_second)

    return TwoPlayerLockResult(True, first_id, second_id, None, lock_first, lock_second)


async def release_two_player_match_lock(result: TwoPlayerLockResult, *, reason: str = "RELEASED") -> None:
    if result.first_user_id is not None:
        await release_player_match_lock(result.first_user_id, status="CANCELLED", reason=reason)
    if result.second_user_id is not None and result.second_user_id != result.first_user_id:
        await release_player_match_lock(result.second_user_id, status="CANCELLED", reason=reason)


async def finalize_two_player_match(result: TwoPlayerLockResult, *, match_id: int | None = None, reason: str = "COMPLETED") -> None:
    if result.first_user_id is not None:
        await finalize_match(result.first_user_id, match_id=match_id, reason=reason)
    if result.second_user_id is not None and result.second_user_id != result.first_user_id:
        await finalize_match(result.second_user_id, match_id=match_id, reason=reason)


# ---------------------------------------------------------------------------
# Пользовательское сообщение "у вас уже есть активный матч"
# ---------------------------------------------------------------------------

MATCH_TYPE_LABELS: dict[str, str] = {
    "normal": "Обычный матч",
    "normal_pvp": "Обычный матч (PvP)",
    "ranked": "Ranked Mode",
    "stronghold_fortress": "The Stronghold — Fortress",
    "stronghold_endless": "The Stronghold — Endless Siege",
    "war2": "Clan War 2.0",
    "tournament": "Турнир",
    "legacy": "Матч",
}

# Правила отмены зависят от режима — где отмена разрешена правилами самого
# режима (см. war2_core.cancel_war2_match — только пока матч в 'drafting'),
# остальные считаются недоступными для отмены пользователем напрямую.
MATCH_TYPE_CANCELLABLE: dict[str, bool] = {
    "war2": True,
}


def is_match_type_cancellable(match_type: str) -> bool:
    return MATCH_TYPE_CANCELLABLE.get(match_type, False)


async def _find_opponent_name(match_type: str, match_id: int | None) -> str | None:
    if match_id is None:
        return None
    try:
        if match_type == "war2":
            with get_connection() as connection:
                row = connection.execute("SELECT opponent_name FROM war2_matches WHERE id = ?", (match_id,)).fetchone()
        elif match_type == "ranked":
            with get_connection() as connection:
                row = connection.execute("SELECT opponent_name FROM ranked_matches WHERE id = ?", (match_id,)).fetchone()
        elif match_type in ("normal", "normal_pvp", "tournament", "stronghold_fortress", "stronghold_endless", "legacy"):
            with get_connection() as connection:
                row = connection.execute("SELECT opponent_name FROM matches WHERE id = ?", (match_id,)).fetchone()
        else:
            return None
    except sqlite3.OperationalError:
        return None
    return row["opponent_name"] if row is not None and "opponent_name" in row.keys() else None


async def describe_active_match_short(lock: LockInfo) -> str:
    """Однострочный, БЕЗ HTML-разметки, вариант для callback.answer(show_alert=True) —
    у Telegram-алертов нет рендеринга HTML и есть жёсткий лимит длины (~200
    символов), в отличие от полноценного текста экрана (describe_active_match)."""
    label = MATCH_TYPE_LABELS.get(lock.match_type, lock.match_type)
    opponent_name = await _find_opponent_name(lock.match_type, lock.match_id)
    opponent_part = f", соперник: {opponent_name}" if opponent_name else ""
    return f"Режим: {label}{opponent_part}. Начат: {lock.acquired_at or '—'}."


async def describe_active_match(lock: LockInfo) -> str:
    """Текст для пользователя, у которого уже есть активный матч — режим,
    соперник (если доступен), время начала, статус. Кнопки (возврат к матчу,
    обновить статус, отмена — только если режим её разрешает) собирает
    вызывающий хендлер, т.к. целевой callback_data у каждого режима свой."""
    label = MATCH_TYPE_LABELS.get(lock.match_type, lock.match_type)
    opponent_name = await _find_opponent_name(lock.match_type, lock.match_id)

    lines = [
        "⛔ <b>У вас уже есть активный матч.</b>",
        "",
        f"Режим: {label}",
    ]
    if opponent_name:
        lines.append(f"Соперник: {opponent_name}")
    lines.append(f"Начат: {lock.acquired_at or '—'}")
    lines.append(f"Статус: {lock.status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Административная диагностика
# ---------------------------------------------------------------------------

async def list_active_locks(limit: int = 50) -> list[LockInfo]:
    placeholders = ",".join("?" for _ in ACTIVE_LOCK_STATUSES)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM player_match_locks WHERE status IN ({placeholders}) ORDER BY acquired_at DESC LIMIT ?",
            (*ACTIVE_LOCK_STATUSES, limit),
        ).fetchall()
    return [_row_to_lock_info(row) for row in rows]


async def admin_force_release_lock(lock_id: int, *, admin_id: int, reason: str) -> LockInfo | None:
    """Принудительное освобождение конкретного lock'а администратором. Возвращает
    lock ДО освобождения (для отображения/аудита) или None, если такого активного
    lock'а уже нет (двойное нажатие — идемпотентно, не ошибка)."""
    placeholders = ",".join("?" for _ in ACTIVE_LOCK_STATUSES)
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM player_match_locks WHERE id = ? AND status IN ({placeholders})",
            (lock_id, *ACTIVE_LOCK_STATUSES),
        ).fetchone()
    if row is None:
        return None

    lock = _row_to_lock_info(row)
    await release_player_match_lock(
        lock.user_id, status="CANCELLED", reason=f"ADMIN_FORCE_RELEASE by {admin_id}: {reason}"
    )

    from app.services.audit_log import record_committed

    record_committed(
        admin_id,
        "match_lock_force_release",
        entity_type="player_match_lock",
        entity_id=lock.id,
        details={"user_id": lock.user_id, "match_type": lock.match_type, "match_id": lock.match_id, "reason": reason},
    )
    return lock


# ---------------------------------------------------------------------------
# Обратная совместимость: старая сигнатура, использованная существующими
# режимами до этой сессии. Переведена на новую таблицу/индекс — ЛЮБОЙ вызывающий
# код, ещё использующий эти три функции, автоматически получает межрежимную
# защиту и физическую БД-гарантию, даже если конкретный вызов не был обновлён на
# новую явную сигнатуру.
# ---------------------------------------------------------------------------

async def try_acquire_match_lock(user_id: int, match_type: str = "legacy") -> bool:
    result = await acquire_player_match_lock(user_id, match_type)
    return result.acquired


async def release_match_lock(user_id: int) -> None:
    await release_player_match_lock(user_id, status="CANCELLED", reason="LEGACY_RELEASE")


async def has_active_match(user_id: int) -> bool:
    return await get_active_match(user_id) is not None
