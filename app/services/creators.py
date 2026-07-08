"""Программа официальных креаторов (#23).

Поток: заявка -> одобрение админом -> статус креатора + галочка -> уровень по подписчикам.
Еженедельные награды копятся в отдельной панели креатора (creator_inventory / creator_pack_inventory),
откуда он выдаёт их подписчикам по ID. Все выдачи логируются.
"""

from dataclasses import dataclass

from app.database.db import get_connection
from app.services.rewards import grant_currency, grant_pack

# Уровни креаторов: (мин. подписчиков, недельные coins, недельные паки).
CREATOR_LEVELS = {
    1: {"min_subs": 30, "coins": 100000, "packs": 1, "title": "1 уровень (30–99)"},
    2: {"min_subs": 100, "coins": 300000, "packs": 1, "title": "2 уровень (100–199)"},
    3: {"min_subs": 200, "coins": 350000, "packs": 1, "title": "3 уровень (200–299)"},
    4: {"min_subs": 300, "coins": 400000, "packs": 3, "title": "4 уровень (300–499)"},
    5: {"min_subs": 500, "coins": 500000, "packs": 5, "title": "5 уровень (500+)"},
}
MIN_SUBSCRIBERS = 30


def level_for_subscribers(subs: int) -> int:
    level = 0
    for lvl in sorted(CREATOR_LEVELS):
        if subs >= CREATOR_LEVELS[lvl]["min_subs"]:
            level = lvl
    return level


@dataclass(frozen=True)
class CreatorApplication:
    id: int
    user_id: int
    nickname: str
    telegram_id: int
    channel: str
    subscribers: int
    description: str
    status: str


@dataclass(frozen=True)
class CreatorPanel:
    is_creator: bool
    level: int
    level_title: str
    channel: str | None
    coins_available: int
    packs: list[tuple[int, str, int]]  # (pack_id, name, qty)


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------

async def submit_application(user_id: int, channel: str, subscribers: int, description: str) -> tuple[bool, str]:
    channel = channel.strip()
    description = " ".join(description.strip().split())
    if len(channel) < 3 or len(channel) > 128:
        return False, "Укажи корректную ссылку на канал/чат."
    if subscribers < 0 or subscribers > 100000000:
        return False, "Некорректное число подписчиков."

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
        if creator and int(creator["is_creator"]):
            connection.rollback()
            return False, "Ты уже официальный креатор."
        pending = connection.execute(
            "SELECT id FROM creator_applications WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
        if pending is not None:
            connection.rollback()
            return False, "Твоя заявка уже на рассмотрении."
        connection.execute(
            "INSERT INTO creator_applications (user_id, channel, subscribers, description) VALUES (?, ?, ?, ?)",
            (user_id, channel, subscribers, description[:500]),
        )
        connection.commit()
    return True, "Заявка отправлена. Админы рассмотрят её и свяжутся с тобой."


async def get_pending_applications() -> list[CreatorApplication]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT a.id, a.user_id, u.nickname, u.telegram_id, a.channel, a.subscribers, a.description, a.status
            FROM creator_applications a
            JOIN users u ON u.id = a.user_id
            WHERE a.status = 'pending'
            ORDER BY a.created_at
            """
        ).fetchall()
    return [CreatorApplication(**dict(row)) for row in rows]


async def get_application(app_id: int) -> CreatorApplication | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT a.id, a.user_id, u.nickname, u.telegram_id, a.channel, a.subscribers, a.description, a.status
            FROM creator_applications a
            JOIN users u ON u.id = a.user_id
            WHERE a.id = ?
            """,
            (app_id,),
        ).fetchone()
    return CreatorApplication(**dict(row)) if row else None


async def resolve_application(app_id: int, approve: bool) -> tuple[bool, str, int | None]:
    """Возвращает (ok, msg, telegram_id заявителя)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT a.user_id, a.subscribers, a.channel, a.status, u.telegram_id FROM creator_applications a JOIN users u ON u.id = a.user_id WHERE a.id = ?",
            (app_id,),
        ).fetchone()
        if row is None or row["status"] != "pending":
            connection.rollback()
            return False, "Заявка недоступна.", None

        user_id = int(row["user_id"])
        telegram_id = int(row["telegram_id"])

        if not approve:
            connection.execute("UPDATE creator_applications SET status='rejected', resolved_at=CURRENT_TIMESTAMP WHERE id=?", (app_id,))
            connection.commit()
            return True, "Заявка отклонена.", telegram_id

        level = level_for_subscribers(int(row["subscribers"]))
        if level == 0:
            connection.rollback()
            return False, f"Меньше {MIN_SUBSCRIBERS} подписчиков — минимум для программы не достигнут.", None

        connection.execute(
            "UPDATE users SET is_creator = 1, creator_level = ?, creator_channel = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (level, row["channel"], user_id),
        )
        connection.execute("INSERT OR IGNORE INTO creator_inventory (user_id, coins) VALUES (?, 0)", (user_id,))
        connection.execute("UPDATE creator_applications SET status='approved', resolved_at=CURRENT_TIMESTAMP WHERE id=?", (app_id,))
        connection.commit()
        return True, f"Игрок стал креатором ({CREATOR_LEVELS[level]['title']}).", telegram_id


# ---------------------------------------------------------------------------
# Уровень / статус / бейдж
# ---------------------------------------------------------------------------

async def is_creator(user_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and int(row["is_creator"]))


async def set_creator_level(user_id: int, level: int) -> tuple[bool, str]:
    if level not in CREATOR_LEVELS and level != 0:
        return False, "Уровень должен быть 0–5."
    with get_connection() as connection:
        row = connection.execute("SELECT is_creator FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return False, "Игрок не найден."
        connection.execute(
            "UPDATE users SET creator_level = ?, is_creator = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (level, 1 if level > 0 else 0, user_id),
        )
        connection.commit()
    return True, "Уровень обновлён."


async def revoke_creator(user_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET is_creator = 0, creator_level = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        connection.commit()
    return True, "Статус креатора снят."


# ---------------------------------------------------------------------------
# Панель креатора: инвентарь и выдача
# ---------------------------------------------------------------------------

async def get_panel(user_id: int) -> CreatorPanel:
    with get_connection() as connection:
        user = connection.execute("SELECT is_creator, creator_level, creator_channel FROM users WHERE id = ?", (user_id,)).fetchone()
        inv = connection.execute("SELECT coins FROM creator_inventory WHERE user_id = ?", (user_id,)).fetchone()
        packs = connection.execute(
            """
            SELECT cpi.pack_id, p.name, cpi.quantity
            FROM creator_pack_inventory cpi
            JOIN packs p ON p.id = cpi.pack_id
            WHERE cpi.user_id = ? AND cpi.quantity > 0
            ORDER BY p.name
            """,
            (user_id,),
        ).fetchall()

    level = int(user["creator_level"]) if user else 0
    return CreatorPanel(
        is_creator=bool(user and int(user["is_creator"])),
        level=level,
        level_title=CREATOR_LEVELS.get(level, {}).get("title", "—"),
        channel=user["creator_channel"] if user else None,
        coins_available=int(inv["coins"]) if inv else 0,
        packs=[(int(r["pack_id"]), r["name"], int(r["quantity"])) for r in packs],
    )


async def get_distribution_history(user_id: int, limit: int = 10) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT d.reward_desc, d.created_at, u.nickname AS target_nickname
            FROM creator_distributions d
            JOIN users u ON u.id = d.target_user_id
            WHERE d.creator_user_id = ?
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


async def distribute_coins(creator_user_id: int, target_telegram_id: int, amount: int) -> tuple[bool, str]:
    if amount <= 0:
        return False, "Сумма должна быть больше 0."

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (creator_user_id,)).fetchone()
        if not creator or not int(creator["is_creator"]):
            connection.rollback()
            return False, "Только официальные креаторы могут выдавать награды."

        target = connection.execute("SELECT id, nickname FROM users WHERE telegram_id = ?", (target_telegram_id,)).fetchone()
        if target is None:
            connection.rollback()
            return False, "Игрок с таким ID не найден."
        target_id = int(target["id"])

        # атомарно списываем из инвентаря креатора
        spent = connection.execute(
            "UPDATE creator_inventory SET coins = coins - ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND coins >= ?",
            (amount, creator_user_id, amount),
        )
        if spent.rowcount != 1:
            connection.rollback()
            return False, "Недостаточно Coins в панели креатора."

        grant_currency(connection, target_id, "coins", amount)
        connection.execute(
            "INSERT INTO creator_distributions (creator_user_id, target_user_id, reward_desc) VALUES (?, ?, ?)",
            (creator_user_id, target_id, f"{amount} Coins"),
        )
        connection.commit()

    return True, f"Выдано {amount} Coins игроку {target['nickname']}."


async def distribute_pack(creator_user_id: int, target_telegram_id: int, pack_id: int) -> tuple[bool, str]:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        creator = connection.execute("SELECT is_creator FROM users WHERE id = ?", (creator_user_id,)).fetchone()
        if not creator or not int(creator["is_creator"]):
            connection.rollback()
            return False, "Только официальные креаторы могут выдавать награды."

        target = connection.execute("SELECT id, nickname FROM users WHERE telegram_id = ?", (target_telegram_id,)).fetchone()
        if target is None:
            connection.rollback()
            return False, "Игрок с таким ID не найден."
        target_id = int(target["id"])

        spent = connection.execute(
            "UPDATE creator_pack_inventory SET quantity = quantity - 1 WHERE user_id = ? AND pack_id = ? AND quantity >= 1",
            (creator_user_id, pack_id),
        )
        if spent.rowcount != 1:
            connection.rollback()
            return False, "Такого пака нет в панели креатора."

        pack_row = connection.execute("SELECT name FROM packs WHERE id = ?", (pack_id,)).fetchone()
        pack_name = pack_row["name"] if pack_row else "Пак"
        grant_pack(connection, target_id, pack_id, 1)
        connection.execute(
            "INSERT INTO creator_distributions (creator_user_id, target_user_id, reward_desc) VALUES (?, ?, ?)",
            (creator_user_id, target_id, f"Пак: {pack_name}"),
        )
        connection.commit()

    return True, f"Выдан пак «{pack_name}» игроку {target['nickname']}."


# ---------------------------------------------------------------------------
# Админ: список креаторов, недельная выплата в панели
# ---------------------------------------------------------------------------

async def list_creators() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, nickname, telegram_id, creator_level, creator_channel FROM users WHERE is_creator = 1 ORDER BY creator_level DESC, nickname"
        ).fetchall()
    return [dict(r) for r in rows]


async def pay_weekly_rewards() -> tuple[int, int, int]:
    """Начисляет всем креаторам недельные награды в их панель. (креаторов, coins всего, паков всего)."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        creators = connection.execute("SELECT id, creator_level FROM users WHERE is_creator = 1").fetchall()

        default_pack = connection.execute("SELECT id FROM packs WHERE active = 1 ORDER BY id LIMIT 1").fetchone()
        default_pack_id = int(default_pack["id"]) if default_pack else None

        total_coins = 0
        total_packs = 0
        for creator in creators:
            level = int(creator["creator_level"])
            cfg = CREATOR_LEVELS.get(level)
            if cfg is None:
                continue
            connection.execute(
                "INSERT INTO creator_inventory (user_id, coins) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET coins = coins + excluded.coins, updated_at = CURRENT_TIMESTAMP",
                (int(creator["id"]), cfg["coins"]),
            )
            total_coins += cfg["coins"]
            if default_pack_id is not None and cfg["packs"] > 0:
                connection.execute(
                    "INSERT INTO creator_pack_inventory (user_id, pack_id, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + excluded.quantity",
                    (int(creator["id"]), default_pack_id, cfg["packs"]),
                )
                total_packs += cfg["packs"]

        connection.commit()
    return len(creators), total_coins, total_packs


async def get_user_id_by_public_id(target_telegram_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM users WHERE telegram_id = ?", (target_telegram_id,)).fetchone()
    return int(row["id"]) if row else None


async def list_packs_for_picker(limit: int = 30) -> list[tuple[int, str]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT id, name FROM packs WHERE active = 1 ORDER BY name LIMIT ?", (limit,)).fetchall()
    return [(int(row["id"]), row["name"]) for row in rows]
