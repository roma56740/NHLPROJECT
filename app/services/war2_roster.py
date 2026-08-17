"""CLAN WAR 2.0 — ростер клана (раздел ТЗ "CLAN WAR CORE": Clan size 5 игроков).

Отдельная таблица `war2_clan_roster`, НЕ переиспользует/не меняет `clan_members`
(общую для всего бота) — просто отмечает, кто из уже
существующих участников клана допущен играть CLAN WAR 2.0. Лидер/офицер клана
управляет составом ростера (до `war2_roster_size`, по умолчанию 5).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.war2_common import War2Error

MANAGER_ROLES = ("leader", "officer")


@dataclass(frozen=True)
class War2RosterMember:
    user_id: int
    nickname: str
    role: str
    added_at: str


async def get_roster_size_limit() -> int:
    from app.services.settings import get_int_setting

    return await get_int_setting("war2_roster_size", 5, minimum=1)


def _get_clan_member_role(connection: sqlite3.Connection, clan_id: int, user_id: int) -> str | None:
    row = connection.execute(
        "SELECT role FROM clan_members WHERE clan_id = ? AND user_id = ?", (clan_id, user_id)
    ).fetchone()
    return row["role"] if row is not None else None


async def get_clan_roster(clan_id: int) -> list[War2RosterMember]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT war2_clan_roster.user_id, war2_clan_roster.created_at, users.nickname, clan_members.role
            FROM war2_clan_roster
            JOIN users ON users.id = war2_clan_roster.user_id
            LEFT JOIN clan_members ON clan_members.clan_id = war2_clan_roster.clan_id AND clan_members.user_id = war2_clan_roster.user_id
            WHERE war2_clan_roster.clan_id = ?
            ORDER BY war2_clan_roster.created_at
            """,
            (clan_id,),
        ).fetchall()
    return [
        War2RosterMember(user_id=int(row["user_id"]), nickname=row["nickname"], role=row["role"] or "member", added_at=row["created_at"])
        for row in rows
    ]


async def is_on_roster(clan_id: int, user_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM war2_clan_roster WHERE clan_id = ? AND user_id = ?", (clan_id, user_id)
        ).fetchone()
    return row is not None


async def _require_manager(connection: sqlite3.Connection, clan_id: int, actor_user_id: int) -> None:
    role = _get_clan_member_role(connection, clan_id, actor_user_id)
    if role not in MANAGER_ROLES:
        raise War2Error("ROSTER_NOT_MANAGER", "Управлять ростером CLAN WAR 2.0 может только лидер или офицер клана.")


async def add_roster_member(clan_id: int, user_id: int, actor_user_id: int) -> None:
    limit = await get_roster_size_limit()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            await _require_manager(connection, clan_id, actor_user_id)

            target_role = _get_clan_member_role(connection, clan_id, user_id)
            if target_role is None:
                raise War2Error("ROSTER_NOT_CLAN_MEMBER", "Этот игрок не состоит в вашем клане.")

            current_size = connection.execute(
                "SELECT COUNT(*) AS n FROM war2_clan_roster WHERE clan_id = ?", (clan_id,)
            ).fetchone()["n"]
            if int(current_size) >= limit:
                raise War2Error("ROSTER_FULL", f"Ростер уже заполнен ({limit}/{limit}). Сначала уберите кого-то.")

            try:
                connection.execute(
                    "INSERT INTO war2_clan_roster (clan_id, user_id, added_by_user_id) VALUES (?, ?, ?)",
                    (clan_id, user_id, actor_user_id),
                )
            except sqlite3.IntegrityError as error:
                raise War2Error("ROSTER_ALREADY_ADDED", "Этот игрок уже в ростере.") from error
        except War2Error:
            connection.rollback()
            raise
        connection.commit()


async def remove_roster_member(clan_id: int, user_id: int, actor_user_id: int) -> None:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            await _require_manager(connection, clan_id, actor_user_id)
            connection.execute("DELETE FROM war2_clan_roster WHERE clan_id = ? AND user_id = ?", (clan_id, user_id))
        except War2Error:
            connection.rollback()
            raise
        connection.commit()
