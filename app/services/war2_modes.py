"""CLAN WAR 2.0 — реестр режимов (WAR MODES) + логика, специфичная для каждого режима.

Реестр = Python dict (реальные правила режима — код, не конфиг) + таблица `war2_modes`
в БД (только on/off без деплоя). Это честный, не переоцененный контракт
расширяемости: новый режим = новая запись в WAR2_MODE_REGISTRY (код) + строка в
war2_modes (админка). См. docs/CLAN_WAR_2_SPEC.md, раздел "War mode registry".
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.bot_card_policy import BOT_BLOCKED_COLLECTION_CODE, BOT_BLOCKED_COLLECTION_NAME
from app.services.lineup import LineupCard, row_to_lineup_card
from app.services.war2_common import War2Error

CLONE_WAR_MIN_OVR = 92
CLONE_WAR_MAX_OVR = 99
CLONE_WAR_ROSTER_SIZE = 6
CLONE_WAR_POSITION_QUOTAS: tuple[tuple[str, int], ...] = (("F", 3), ("D", 2), ("G", 1))


@dataclass(frozen=True)
class War2ModeDefinition:
    code: str
    title: str
    uses_draft: bool
    allow_wild_card: bool = False


WAR2_MODE_REGISTRY: dict[str, War2ModeDefinition] = {
    "CLONE_WAR": War2ModeDefinition("CLONE_WAR", "Clone War", uses_draft=False),
    "SALARY_WAR": War2ModeDefinition("SALARY_WAR", "Salary War", uses_draft=True),
    "WILD_CARD": War2ModeDefinition("WILD_CARD", "Wild Card", uses_draft=True, allow_wild_card=True),
}


async def roll_active_mode() -> War2ModeDefinition:
    """War Roulette with self-heal for legacy databases where all modes were disabled."""
    with get_connection() as connection:
        rows = connection.execute("SELECT code FROM war2_modes WHERE active = 1").fetchall()
        active_codes = [row["code"] for row in rows if row["code"] in WAR2_MODE_REGISTRY]
        if not active_codes:
            registered_codes = list(WAR2_MODE_REGISTRY)
            placeholders = ", ".join("?" for _ in registered_codes)
            connection.execute(
                f"UPDATE war2_modes SET active = 1, updated_at = CURRENT_TIMESTAMP WHERE code IN ({placeholders})",
                registered_codes,
            )
            connection.commit()
            active_codes = registered_codes
    if not active_codes:
        raise War2Error("NO_ACTIVE_WAR_MODES", "Режимы CLAN WAR 2.0 не настроены. Обратитесь к администрации.")
    return WAR2_MODE_REGISTRY[random.choice(active_codes)]


async def build_clone_war_lineup() -> list[int]:
    """CLONE_WAR: одинаковый для обеих сторон полноценный состав 3F/2D/1G
    из случайных карт Base Collection с OVR 92-99."""
    card_ids: list[int] = []
    with get_connection() as connection:
        for position, count in CLONE_WAR_POSITION_QUOTAS:
            rows = connection.execute(
                """
                SELECT cards.id FROM cards
                JOIN collections ON collections.id = cards.collection_id
                WHERE collections.is_exclusive = 0 AND collections.active = 1
                  AND TRIM(collections.name) COLLATE NOCASE != ?
                  AND TRIM(COALESCE(collections.code, '')) COLLATE NOCASE != ?
                  AND cards.active = 1 AND cards.position = ?
                  AND cards.overall BETWEEN ? AND ?
                ORDER BY RANDOM() LIMIT ?
                """,
                (BOT_BLOCKED_COLLECTION_NAME, BOT_BLOCKED_COLLECTION_CODE, position, CLONE_WAR_MIN_OVR, CLONE_WAR_MAX_OVR, count),
            ).fetchall()
            if len(rows) < count:
                raise War2Error(
                    "CLONE_WAR_INSUFFICIENT_CARDS",
                    f"Недостаточно карт позиции {position} с OVR "
                    f"{CLONE_WAR_MIN_OVR}-{CLONE_WAR_MAX_OVR} для Clone War.",
                )
            card_ids.extend(int(row["id"]) for row in rows)
    return card_ids


async def get_effective_salary_cap() -> int:
    from app.services.salary import WAR2_SALARY_CAP
    from app.services.settings import get_int_setting

    return await get_int_setting("war2_salary_cap", WAR2_SALARY_CAP, minimum=1)


async def validate_salary_cap(card_ids: list[int]) -> None:
    """SALARY_WAR: сумма зарплат 6 выбранных карт не может превышать лимит (раздел ТЗ
    "SALARY WAR") — превышение блокирует подтверждение состава."""
    from app.services.salary import format_salary

    if not card_ids:
        return

    placeholders = ", ".join("?" for _ in card_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT COALESCE(SUM(salary), 0) AS total FROM cards WHERE id IN ({placeholders})",
            card_ids,
        ).fetchone()
    total_salary = int(rows["total"])
    cap = await get_effective_salary_cap()

    if total_salary > cap:
        raise War2Error(
            "SALARY_CAP_EXCEEDED",
            f"Потолок зарплат превышен. Лимит: {format_salary(cap)}, состав: {format_salary(total_salary)}.",
        )


async def apply_wild_card_replacement(
    match_id: int,
    user_id: int,
    replace_card_id: int,
    user_card_id: int,
) -> tuple[list[LineupCard], int]:
    """WILD_CARD: заменяет ровно ОДНУ выбранную на драфте карту на любую карту из
    собственной коллекции игрока (раздел ТЗ "WILD CARD") — только для текущего матча,
    исходные `war2_draft_picks` не трогаются (история драфта остаётся достоверной).
    Возвращает (новый ростер с заменой, id вытесненной карты)."""
    from app.services.war2_draft import finalize_lineup_for

    with get_connection() as connection:
        match_row = connection.execute(
            "SELECT status, mode_code, used_wild_card FROM war2_matches WHERE id = ? AND user_id = ?",
            (match_id, user_id),
        ).fetchone()
        if match_row is None:
            raise War2Error("MATCH_NOT_FOUND", "Матч не найден.")
        if match_row["status"] != "drafting":
            raise War2Error("MATCH_NOT_DRAFTING", "Матч уже завершён или отменён.")
        if match_row["mode_code"] != "WILD_CARD":
            raise War2Error("WILD_CARD_NOT_ALLOWED", "Wild Card недоступен в этом режиме.")
        if int(match_row["used_wild_card"]):
            raise War2Error("WILD_CARD_ALREADY_USED", "Wild Card уже использован в этом матче.")

        owned_row = connection.execute(
            """
            SELECT user_cards.id AS user_card_id, user_cards.card_id, user_cards.lineup_slot,
                   cards.name, cards.player_key, cards.position, cards.overall, cards.team,
                   cards.country, cards.rarity, cards.image_path, cards.salary,
                   collections.name AS collection_name, collections.code AS collection_code
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE user_cards.id = ? AND user_cards.user_id = ?
            """,
            (user_card_id, user_id),
        ).fetchone()
        if owned_row is None:
            raise War2Error("CARD_NOT_OWNED", "Эта карта вам не принадлежит.")

    picks = await finalize_lineup_for(match_id, "user")
    replaced_ids = [card.card_id for card in picks]
    if replace_card_id not in replaced_ids:
        raise War2Error("WILD_CARD_TARGET_NOT_IN_ROSTER", "Эта карта не входит в ваш выбранный состав.")

    replacement_card = row_to_lineup_card(owned_row)
    replaced_card = next(card for card in picks if card.card_id == replace_card_id)
    if str(replacement_card.position).upper() != str(replaced_card.position).upper():
        raise War2Error(
            "WILD_CARD_POSITION_MISMATCH",
            f"Wild Card должна сохранить позицию: нужна карта {replaced_card.position}.",
        )
    new_roster = [replacement_card if card.card_id == replace_card_id else card for card in picks]

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE war2_matches
            SET used_wild_card = 1, wild_card_replaced_card_id = ?, wild_card_user_card_id = ?
            WHERE id = ? AND user_id = ? AND status = 'drafting' AND used_wild_card = 0
            """,
            (replace_card_id, user_card_id, match_id, user_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            raise War2Error("WILD_CARD_ALREADY_USED", "Wild Card уже использован в этом матче.")
        connection.commit()

    return new_roster, replace_card_id
