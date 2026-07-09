import asyncio
from html import escape
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.database.db import get_connection
from app.services.settings import get_int_setting

ATTACK_DURATION_HOURS = 24
INCOME_PERIOD_HOURS = 24
CLAN_WARS_LOOP_SLEEP_SECONDS = 60
MAX_ARENAS = 9


@dataclass(frozen=True)
class ArenaAttackInfo:
    id: int
    clan_id: int
    clan_name: str
    points: int
    defense_points: int
    effective_points: int
    expires_at: str


@dataclass(frozen=True)
class ArenaInfo:
    id: int
    name: str
    description: str
    active: bool
    capture_wins_required: int
    income_currency_code: str | None
    income_currency_name: str | None
    income_currency_icon: str | None
    income_amount: int
    capture_currency_code: str | None
    capture_currency_name: str | None
    capture_currency_icon: str | None
    capture_amount: int
    holder_clan_id: int | None
    holder_clan_name: str | None
    captured_at: str | None
    protected_until: str | None
    attacks: list[ArenaAttackInfo]


@dataclass(frozen=True)
class WarActionResult:
    ok: bool
    title: str
    description: str


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def row_to_arena(row, attacks: list[ArenaAttackInfo]) -> ArenaInfo:
    return ArenaInfo(
        id=int(row["id"]),
        name=row["name"],
        description=row["description"] or "",
        active=bool(row["active"]),
        capture_wins_required=int(row["capture_wins_required"]),
        income_currency_code=row["income_currency_code"],
        income_currency_name=row["income_currency_name"],
        income_currency_icon=row["income_currency_icon"],
        income_amount=int(row["income_amount"] or 0),
        capture_currency_code=row["capture_currency_code"],
        capture_currency_name=row["capture_currency_name"],
        capture_currency_icon=row["capture_currency_icon"],
        capture_amount=int(row["capture_amount"] or 0),
        holder_clan_id=row["holder_clan_id"],
        holder_clan_name=row["holder_clan_name"],
        captured_at=row["captured_at"],
        protected_until=row["protected_until"] if "protected_until" in row.keys() else None,
        attacks=attacks,
    )


ARENA_SELECT_SQL = """
SELECT
    clan_arenas.*,
    holder.name AS holder_clan_name,
    inc.name AS income_currency_name,
    inc.icon AS income_currency_icon,
    cap.name AS capture_currency_name,
    cap.icon AS capture_currency_icon
FROM clan_arenas
LEFT JOIN clans holder ON holder.id = clan_arenas.holder_clan_id
LEFT JOIN currencies inc ON inc.code = clan_arenas.income_currency_code
LEFT JOIN currencies cap ON cap.code = clan_arenas.capture_currency_code
"""


def fetch_arena_attacks(connection, arena_id: int) -> list[ArenaAttackInfo]:
    rows = connection.execute(
        """
        SELECT clan_arena_attacks.id, clan_arena_attacks.clan_id, clans.name AS clan_name,
               clan_arena_attacks.points, clan_arena_attacks.defense_points, clan_arena_attacks.effective_points, clan_arena_attacks.expires_at
        FROM clan_arena_attacks
        JOIN clans ON clans.id = clan_arena_attacks.clan_id
        WHERE clan_arena_attacks.arena_id = ? AND clan_arena_attacks.status = 'active'
        ORDER BY clan_arena_attacks.points DESC
        """,
        (arena_id,),
    ).fetchall()
    return [
        ArenaAttackInfo(
            id=int(row["id"]),
            clan_id=int(row["clan_id"]),
            clan_name=row["clan_name"],
            points=int(row["points"]),
            defense_points=int(row["defense_points"] or 0),
            effective_points=int(row["effective_points"] or 0),
            expires_at=row["expires_at"],
        )
        for row in rows
    ]


async def get_arenas(include_inactive: bool = False) -> list[ArenaInfo]:
    with get_connection() as connection:
        where = "" if include_inactive else "WHERE clan_arenas.active = 1"
        rows = connection.execute(f"{ARENA_SELECT_SQL} {where} ORDER BY clan_arenas.id").fetchall()
        return [row_to_arena(row, fetch_arena_attacks(connection, int(row["id"]))) for row in rows]


async def get_arena(arena_id: int) -> ArenaInfo | None:
    with get_connection() as connection:
        row = connection.execute(f"{ARENA_SELECT_SQL} WHERE clan_arenas.id = ?", (arena_id,)).fetchone()
        if row is None:
            return None
        return row_to_arena(row, fetch_arena_attacks(connection, arena_id))


async def get_active_currency_choices() -> list[tuple[str, str, str]]:
    """Returns (code, name, icon) for active currencies."""
    with get_connection() as connection:
        rows = connection.execute("SELECT code, name, icon FROM currencies WHERE active = 1 ORDER BY code").fetchall()
    return [(row["code"], row["name"], row["icon"]) for row in rows]


# ---------------------------------------------------------------------------
# Атаки
# ---------------------------------------------------------------------------

async def declare_attack(actor_user_id: int, arena_id: int) -> WarActionResult:
    now = utc_now()

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        member = connection.execute(
            "SELECT clan_id, role FROM clan_members WHERE user_id = ?",
            (actor_user_id,),
        ).fetchone()
        if member is None:
            connection.rollback()
            return WarActionResult(False, "Нет клана", "Сначала вступи в клан или создай свой.")
        if member["role"] not in ("leader", "officer"):
            connection.rollback()
            return WarActionResult(False, "Нет прав", "Объявлять атаку могут только президент и вице-президент клана.")

        clan_id = int(member["clan_id"])

        arena = connection.execute(
            "SELECT id, name, active, holder_clan_id, last_holder_clan_id, captured_at, protected_until FROM clan_arenas WHERE id = ?",
            (arena_id,),
        ).fetchone()
        if arena is None or not int(arena["active"]):
            connection.rollback()
            return WarActionResult(False, "Арена недоступна", "Эта арена закрыта или удалена.")
        if arena["holder_clan_id"] is not None and int(arena["holder_clan_id"]) == clan_id:
            connection.rollback()
            return WarActionResult(False, "Арена уже ваша", "Клан уже удерживает эту арену. Защита включается автоматически: победы участников уменьшают прогресс атакующих.")

        shield_until = parse_dt(arena["protected_until"] if "protected_until" in arena.keys() else None)
        if shield_until is not None and shield_until > now:
            connection.rollback()
            return WarActionResult(False, "Арена под щитом", f"После захвата арену нельзя атаковать до {format_dt(shield_until)}.")

        max_owned = await get_int_setting("clan_war_max_owned_arenas", 3, minimum=0, maximum=50)
        if max_owned > 0:
            owned_count = int(connection.execute("SELECT COUNT(*) AS c FROM clan_arenas WHERE holder_clan_id = ?", (clan_id,)).fetchone()["c"] or 0)
            if owned_count >= max_owned:
                connection.rollback()
                return WarActionResult(False, "Лимит арен", f"Клан уже держит максимум арен: {max_owned}. Это ограничение не даёт одному клану стать вечным лидером.")

        cooldown_hours = await get_int_setting("clan_war_same_arena_cooldown_hours", 24, minimum=0, maximum=720)
        captured_at = parse_dt(arena["captured_at"] if "captured_at" in arena.keys() else None)
        if cooldown_hours > 0 and arena["last_holder_clan_id"] is not None and int(arena["last_holder_clan_id"]) == clan_id and captured_at is not None:
            until = captured_at + timedelta(hours=cooldown_hours)
            if until > now:
                connection.rollback()
                return WarActionResult(False, "КД на повторный захват", f"Этот клан недавно потерял арену и сможет атаковать её после {format_dt(until)}.")

        active_attack = connection.execute(
            "SELECT id FROM clan_arena_attacks WHERE clan_id = ? AND status = 'active' LIMIT 1",
            (clan_id,),
        ).fetchone()
        if active_attack is not None:
            connection.rollback()
            return WarActionResult(False, "Атака уже идёт", "Клан может вести только одну атаку одновременно. Дождись её завершения.")

        owned_count = int(connection.execute("SELECT COUNT(*) AS c FROM clan_arenas WHERE holder_clan_id = ?", (clan_id,)).fetchone()["c"] or 0)
        extra_per_arena = await get_int_setting("clan_war_leader_capture_extra_wins", 2, minimum=0, maximum=50)
        effective_required = int(arena["capture_wins_required"] or 0) + owned_count * extra_per_arena

        expires_at = format_dt(now + timedelta(hours=ATTACK_DURATION_HOURS))
        connection.execute(
            """
            INSERT INTO clan_arena_attacks (arena_id, clan_id, started_by_user_id, points, defense_points, effective_points, status, started_at, expires_at)
            VALUES (?, ?, ?, 0, 0, 0, 'active', ?, ?)
            """,
            (arena_id, clan_id, actor_user_id, format_dt(now), expires_at),
        )
        connection.commit()

    return WarActionResult(
        True,
        "Атака объявлена",
        f"У клана есть {ATTACK_DURATION_HOURS} часа. Каждая победа участника в матче приближает захват арены. Если у клана уже есть арены, для захвата нужно больше побед: действует анти-монополия.",
    )


def pay_clan_members(connection, clan_id: int, currency_code: str, amount: int) -> int:
    """Начисляет amount валюты каждому участнику клана. Возвращает число получателей."""
    members = connection.execute(
        "SELECT user_id FROM clan_members WHERE clan_id = ?",
        (clan_id,),
    ).fetchall()

    for member in members:
        connection.execute(
            """
            INSERT INTO currency_balances (user_id, currency_code, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, currency_code) DO UPDATE SET
                amount = amount + excluded.amount,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(member["user_id"]), currency_code, amount),
        )

    return len(members)


async def apply_clan_war_win(user_id: int) -> None:
    """Вызывается после победы игрока в матче.

    Если клан атакует арену — победа прибавляет прогресс атаки.
    Если клан защищает свою арену — победа уменьшает прогресс атакующего клана.
    """
    now = utc_now()
    defense_power = await get_int_setting("clan_war_defense_win_power", 1, minimum=1, maximum=25)
    leader_extra = await get_int_setting("clan_war_leader_capture_extra_wins", 2, minimum=0, maximum=50)
    shield_hours = await get_int_setting("clan_war_capture_shield_hours", 6, minimum=0, maximum=720)

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        member = connection.execute(
            "SELECT clan_id FROM clan_members WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if member is None:
            connection.rollback()
            return

        clan_id = int(member["clan_id"])

        # 1) Защита: если на арену клана идёт атака, победы владельца сбивают прогресс атакующих.
        defense = connection.execute(
            """
            SELECT a.id, a.points, a.defense_points, a.effective_points, a.expires_at,
                   ar.id AS arena_id, ar.name AS arena_name
            FROM clan_arena_attacks a
            JOIN clan_arenas ar ON ar.id = a.arena_id
            WHERE ar.holder_clan_id = ? AND a.status = 'active' AND a.clan_id != ?
            ORDER BY a.points DESC, a.started_at ASC
            LIMIT 1
            """,
            (clan_id, clan_id),
        ).fetchone()
        if defense is not None:
            expires_dt = parse_dt(defense["expires_at"])
            if expires_dt is not None and expires_dt <= now:
                connection.rollback()
                return
            new_defense = int(defense["defense_points"] or 0) + defense_power
            new_effective = max(0, int(defense["points"] or 0) - new_defense)
            connection.execute(
                "UPDATE clan_arena_attacks SET defense_points = ?, effective_points = ? WHERE id = ?",
                (new_defense, new_effective, int(defense["id"])),
            )
            # Защитные победы тоже пишем в личный вклад клана, но отдельно от атакующих побед.
            connection.execute(
                """
                INSERT INTO clan_war_player_stats (clan_id, user_id, wins_contributed)
                VALUES (?, ?, 1)
                ON CONFLICT(clan_id, user_id) DO UPDATE SET
                    wins_contributed = wins_contributed + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (clan_id, user_id),
            )
            connection.commit()
            return

        # 2) Атака: обычный прогресс активной атаки клана.
        attack = connection.execute(
            """
            SELECT clan_arena_attacks.id, clan_arena_attacks.arena_id, clan_arena_attacks.points,
                   clan_arena_attacks.defense_points, clan_arena_attacks.effective_points,
                   clan_arena_attacks.expires_at,
                   clan_arenas.capture_wins_required, clan_arenas.capture_currency_code, clan_arenas.capture_amount,
                   clan_arenas.holder_clan_id
            FROM clan_arena_attacks
            JOIN clan_arenas ON clan_arenas.id = clan_arena_attacks.arena_id
            WHERE clan_arena_attacks.clan_id = ? AND clan_arena_attacks.status = 'active'
            LIMIT 1
            """,
            (clan_id,),
        ).fetchone()
        if attack is None:
            connection.rollback()
            return

        expires_dt = parse_dt(attack["expires_at"])
        if expires_dt is not None and expires_dt <= now:
            connection.rollback()
            return

        connection.execute(
            """
            INSERT INTO clan_war_player_stats (clan_id, user_id, wins_contributed)
            VALUES (?, ?, 1)
            ON CONFLICT(clan_id, user_id) DO UPDATE SET
                wins_contributed = wins_contributed + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (clan_id, user_id),
        )

        owned_count = int(connection.execute("SELECT COUNT(*) AS c FROM clan_arenas WHERE holder_clan_id = ?", (clan_id,)).fetchone()["c"] or 0)
        required = int(attack["capture_wins_required"]) + owned_count * leader_extra
        new_points = int(attack["points"] or 0) + 1
        new_effective = max(0, new_points - int(attack["defense_points"] or 0))

        if new_effective < required:
            connection.execute(
                "UPDATE clan_arena_attacks SET points = ?, effective_points = ? WHERE id = ?",
                (new_points, new_effective, int(attack["id"])),
            )
            connection.commit()
            return

        arena_id = int(attack["arena_id"])
        previous_holder_id = attack["holder_clan_id"]
        finished_at = format_dt(now)
        protected_until = format_dt(now + timedelta(hours=shield_hours)) if shield_hours > 0 else None

        connection.execute(
            "UPDATE clan_arena_attacks SET points = ?, effective_points = ?, status = 'won', finished_at = ? WHERE id = ?",
            (new_points, new_effective, finished_at, int(attack["id"])),
        )
        connection.execute(
            "UPDATE clan_arena_attacks SET status = 'failed', finished_at = ? WHERE arena_id = ? AND status = 'active'",
            (finished_at, arena_id),
        )
        connection.execute(
            """
            UPDATE clan_arenas
            SET holder_clan_id = ?, last_holder_clan_id = ?, captured_at = ?, last_income_at = ?, protected_until = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (clan_id, previous_holder_id, finished_at, finished_at, protected_until, arena_id),
        )

        capture_currency = attack["capture_currency_code"]
        capture_amount = int(attack["capture_amount"] or 0)
        if capture_currency and capture_amount > 0:
            pay_clan_members(connection, clan_id, capture_currency, capture_amount)

        connection.commit()


# ---------------------------------------------------------------------------
# Фоновый цикл: истечение атак, доход, уведомления
# ---------------------------------------------------------------------------

def expire_attacks(connection, now: datetime) -> None:
    connection.execute(
        "UPDATE clan_arena_attacks SET status = 'failed', finished_at = ? WHERE status = 'active' AND expires_at <= ?",
        (format_dt(now), format_dt(now)),
    )


def process_income(connection, now: datetime) -> None:
    arenas = connection.execute(
        """
        SELECT id, holder_clan_id, income_currency_code, income_amount, captured_at, last_income_at
        FROM clan_arenas
        WHERE active = 1
          AND holder_clan_id IS NOT NULL
          AND income_currency_code IS NOT NULL
          AND income_amount > 0
        """
    ).fetchall()

    for arena in arenas:
        base = parse_dt(arena["last_income_at"]) or parse_dt(arena["captured_at"])
        if base is None:
            connection.execute(
                "UPDATE clan_arenas SET last_income_at = ? WHERE id = ?",
                (format_dt(now), int(arena["id"])),
            )
            continue

        if now - base < timedelta(hours=INCOME_PERIOD_HOURS):
            continue

        pay_clan_members(
            connection,
            int(arena["holder_clan_id"]),
            arena["income_currency_code"],
            int(arena["income_amount"]),
        )
        connection.execute(
            "UPDATE clan_arenas SET last_income_at = ? WHERE id = ?",
            (format_dt(now), int(arena["id"])),
        )


def fetch_unnotified_attacks(connection) -> list:
    return connection.execute(
        """
        SELECT clan_arena_attacks.id, clan_arena_attacks.status, clan_arena_attacks.clan_id,
               clan_arenas.name AS arena_name,
               clan_arenas.capture_currency_code, clan_arenas.capture_amount,
               cap.icon AS capture_currency_icon, cap.name AS capture_currency_name
        FROM clan_arena_attacks
        JOIN clan_arenas ON clan_arenas.id = clan_arena_attacks.arena_id
        LEFT JOIN currencies cap ON cap.code = clan_arenas.capture_currency_code
        WHERE clan_arena_attacks.status IN ('won', 'failed') AND clan_arena_attacks.notified = 0
        LIMIT 20
        """
    ).fetchall()


def fetch_clan_member_telegram_ids(connection, clan_id: int) -> list[int]:
    rows = connection.execute(
        """
        SELECT users.telegram_id
        FROM clan_members
        JOIN users ON users.id = clan_members.user_id
        WHERE clan_members.clan_id = ? AND users.is_banned = 0
        """,
        (clan_id,),
    ).fetchall()
    return [int(row["telegram_id"]) for row in rows]


async def clan_wars_loop(bot) -> None:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

    while True:
        try:
            now = utc_now()

            with get_connection() as connection:
                expire_attacks(connection, now)
                process_income(connection, now)
                connection.commit()

            with get_connection() as connection:
                pending = fetch_unnotified_attacks(connection)
                notifications: list[tuple[int, str]] = []

                for attack in pending:
                    if attack["status"] == "won":
                        reward_line = ""
                        if attack["capture_currency_code"] and int(attack["capture_amount"] or 0) > 0:
                            reward_line = (
                                f"\n🎁 Награда каждому: {attack['capture_currency_icon']} "
                                f"{attack['capture_currency_name']} — <b>{int(attack['capture_amount'])}</b>"
                            )
                        text = (
                            f"🏟 <b>Арена захвачена!</b>\n\n"
                            f"Клан взял под контроль арену <b>{escape(attack['arena_name'], quote=False)}</b>.{reward_line}\n\n"
                            f"Пока арена ваша — клан получает ежедневный доход."
                        )
                    else:
                        text = (
                            f"⏰ <b>Атака завершена</b>\n\n"
                            f"Клан не успел захватить арену <b>{escape(attack['arena_name'], quote=False)}</b>. "
                            f"Соберитесь с силами и попробуйте снова!"
                        )

                    for telegram_id in fetch_clan_member_telegram_ids(connection, int(attack["clan_id"])):
                        notifications.append((telegram_id, text))

                    connection.execute(
                        "UPDATE clan_arena_attacks SET notified = 1 WHERE id = ?",
                        (int(attack["id"]),),
                    )

                connection.commit()

            for telegram_id, text in notifications:
                try:
                    await bot.send_message(chat_id=telegram_id, text=text)
                except TelegramRetryAfter as error:
                    await asyncio.sleep(error.retry_after + 1)
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass
                except Exception:
                    pass

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

        await asyncio.sleep(CLAN_WARS_LOOP_SLEEP_SECONDS)


# ---------------------------------------------------------------------------
# Админ: CRUD арен
# ---------------------------------------------------------------------------

async def create_arena(
    name: str,
    description: str,
    capture_wins_required: int,
    income_currency_code: str | None,
    income_amount: int,
    capture_currency_code: str | None,
    capture_amount: int,
) -> WarActionResult:
    clean_name = " ".join((name or "").strip().split())
    clean_description = " ".join((description or "").strip().split())

    if len(clean_name) < 3 or len(clean_name) > 48:
        return WarActionResult(False, "Арена не создана", "Название должно быть от 3 до 48 символов.")
    if len(clean_description) > 300:
        return WarActionResult(False, "Арена не создана", "Описание должно быть до 300 символов.")
    if capture_wins_required < 1 or capture_wins_required > 500:
        return WarActionResult(False, "Арена не создана", "Число побед для захвата — от 1 до 500.")

    with get_connection() as connection:
        total = int(connection.execute("SELECT COUNT(*) AS total_count FROM clan_arenas").fetchone()["total_count"])
        if total >= MAX_ARENAS:
            return WarActionResult(False, "Лимит арен", f"Максимум {MAX_ARENAS} арен. Удали одну, чтобы создать новую.")

        connection.execute(
            """
            INSERT INTO clan_arenas (
                name, description, capture_wins_required,
                income_currency_code, income_amount,
                capture_currency_code, capture_amount
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_name,
                clean_description,
                capture_wins_required,
                income_currency_code,
                max(0, income_amount),
                capture_currency_code,
                max(0, capture_amount),
            ),
        )
        connection.commit()

    return WarActionResult(True, "Арена создана", "Арена уже доступна кланам для атак.")


async def update_arena_field(arena_id: int, field: str, value: object) -> WarActionResult:
    allowed_fields = {
        "name",
        "description",
        "capture_wins_required",
        "income_currency_code",
        "income_amount",
        "capture_currency_code",
        "capture_amount",
    }
    if field not in allowed_fields:
        return WarActionResult(False, "Поле не найдено", "Это поле нельзя изменить.")

    if field == "name":
        value = " ".join(str(value or "").strip().split())
        if len(value) < 3 or len(value) > 48:
            return WarActionResult(False, "Не сохранено", "Название должно быть от 3 до 48 символов.")

    if field == "description":
        value = " ".join(str(value or "").strip().split())
        if len(value) > 300:
            return WarActionResult(False, "Не сохранено", "Описание должно быть до 300 символов.")

    if field in ("capture_wins_required", "income_amount", "capture_amount"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return WarActionResult(False, "Не сохранено", "Нужно целое число.")
        if field == "capture_wins_required" and (value < 1 or value > 500):
            return WarActionResult(False, "Не сохранено", "Число побед для захвата — от 1 до 500.")
        if field in ("income_amount", "capture_amount") and (value < 0 or value > 1000000):
            return WarActionResult(False, "Не сохранено", "Сумма должна быть от 0 до 1 000 000.")

    with get_connection() as connection:
        row = connection.execute("SELECT id FROM clan_arenas WHERE id = ?", (arena_id,)).fetchone()
        if row is None:
            return WarActionResult(False, "Арена не найдена", "Арена уже удалена.")
        connection.execute(
            f"UPDATE clan_arenas SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, arena_id),
        )
        connection.commit()

    return WarActionResult(True, "Сохранено", "Параметр арены обновлён.")


async def toggle_arena_active(arena_id: int) -> WarActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT active FROM clan_arenas WHERE id = ?", (arena_id,)).fetchone()
        if row is None:
            return WarActionResult(False, "Арена не найдена", "Арена уже удалена.")
        new_value = 0 if int(row["active"]) else 1
        connection.execute(
            "UPDATE clan_arenas SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_value, arena_id),
        )
        if new_value == 0:
            connection.execute(
                "UPDATE clan_arena_attacks SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE arena_id = ? AND status = 'active'",
                (arena_id,),
            )
        connection.commit()
    return WarActionResult(True, "Статус обновлён", "Арена включена." if new_value else "Арена выключена, активные атаки остановлены.")


async def release_arena(arena_id: int) -> WarActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM clan_arenas WHERE id = ?", (arena_id,)).fetchone()
        if row is None:
            return WarActionResult(False, "Арена не найдена", "Арена уже удалена.")
        connection.execute(
            "UPDATE clan_arenas SET holder_clan_id = NULL, captured_at = NULL, last_income_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (arena_id,),
        )
        connection.commit()
    return WarActionResult(True, "Арена освобождена", "Теперь арена снова нейтральная.")


async def delete_arena(arena_id: int) -> WarActionResult:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM clan_arenas WHERE id = ?", (arena_id,)).fetchone()
        if row is None:
            return WarActionResult(False, "Арена не найдена", "Арена уже удалена.")
        connection.execute("DELETE FROM clan_arenas WHERE id = ?", (arena_id,))
        connection.commit()
    return WarActionResult(True, "Арена удалена", "Арена и все связанные атаки удалены.")
