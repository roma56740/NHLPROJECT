"""Ranked-боты по лигам (ТЗ "РАНЖИРОВАННЫЕ БОТЫ ПО ЛИГАМ").

Сила бота больше не зависит от OVR/зарплаты/карт пользователя — она определяется
ИСКЛЮЧИТЕЛЬНО текущей Ranked-лигой (`app.services.matches.LEAGUES`: NCAA/AHL/NHL/
OLYMPICS, поле `users.league`), через фиксированные включительные диапазоны OVR
состава бота ниже. Состав бота собирается из РЕАЛЬНЫХ карт каталога `cards`
(никаких синтетических/сгенерированных карточек), теми же позиционными правилами,
что и у пользовательского состава (`app.services.lineup.LINEUP_SLOT_ORDER`), и
рендерится тем же `render_lineup_image()`, что и составы игроков.

Правило округления среднего OVR — Python `round()` (round-half-to-even), то же
самое, что уже использует `get_lineup_overview()` в app/services/lineup.py —
единое правило и в проде, и в тестах.
"""

from __future__ import annotations

import logging
import random
import sqlite3
from dataclasses import dataclass

from app.database.db import get_connection
from app.services.bot_card_policy import BOT_BLOCKED_COLLECTION_CODE, BOT_BLOCKED_COLLECTION_NAME
from app.services.chemistry import ChemistryCard, calculate_chemistry
from app.services.lineup import LINEUP_SLOT_ORDER, LineupCard, LineupOverview, get_slot_info

logger = logging.getLogger(__name__)

# Диапазоны OVR состава бота по Ranked-лиге — ВКЛЮЧИТЕЛЬНЫЕ границы.
RANKED_BOT_LEAGUE_OVR_RANGES: dict[str, tuple[int, int]] = {
    "NCAA": (70, 80),
    "AHL": (80, 90),
    "NHL": (90, 95),
    "OLYMPICS": (95, 99),
}
DEFAULT_BOT_OVR_RANGE = RANKED_BOT_LEAGUE_OVR_RANGES["NCAA"]

# Предохранитель от бесконечного расширения диапазона при пустом каталоге.


def get_league_ovr_range(league: str | None) -> tuple[int, int]:
    return RANKED_BOT_LEAGUE_OVR_RANGES.get((league or "").upper(), DEFAULT_BOT_OVR_RANGE)


def pick_target_ovr(league: str | None) -> int:
    """Legacy/admin helper: random target inside a league range.

    Live Ranked matchmaking no longer uses this function. It uses
    `pick_match_target_ovr()` so the bot is always the player's effective OVR
    or exactly one point higher.
    """
    low, high = get_league_ovr_range(league)
    return random.randint(low, high)


def _catalog_has_exact_lineup(target_ovr: int) -> bool:
    """Return True when exact target OVR can fill 3F/2D/1G.

    Duplicates are allowed by the bot lineup builder, so one real active card of
    each position is enough to fill every required slot without inventing cards
    or changing the requested OVR.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT cards.position, COUNT(*) AS n
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1 AND collections.active = 1
              AND TRIM(collections.name) COLLATE NOCASE != ?
              AND TRIM(COALESCE(collections.code, '')) COLLATE NOCASE != ?
              AND cards.overall = ? AND cards.position IN ('F', 'D', 'G')
            GROUP BY cards.position
            """,
            (BOT_BLOCKED_COLLECTION_NAME, BOT_BLOCKED_COLLECTION_CODE, target_ovr),
        ).fetchall()
    counts = {str(row["position"]): int(row["n"] or 0) for row in rows}
    return all(counts.get(position, 0) > 0 for position in ("F", "D", "G"))


def pick_match_target_ovr(user_ovr: int) -> int:
    """Pick a Ranked bot OVR: same as the player or exactly +1.

    99 is the hard card ceiling. If both allowed ratings exist in the catalog,
    selection is random. If only one can produce a full real-card lineup, that
    one is used. We never fall back to an unrelated rating.
    """
    base = max(1, min(99, int(user_ovr)))
    candidates = [base]
    if base < 99:
        candidates.append(base + 1)

    available = [target for target in candidates if _catalog_has_exact_lineup(target)]
    if available:
        return random.choice(available)
    return base


def _select_real_card(
    connection: sqlite3.Connection,
    *,
    position: str,
    target_ovr: int,
    exclude_card_ids: set[int],
) -> sqlite3.Row | None:
    """Pick a real active card with exactly target_ovr.

    Bots never manufacture cards and never silently substitute another rating.
    """
    exclude_sql = ""
    params: list[object] = [BOT_BLOCKED_COLLECTION_NAME, BOT_BLOCKED_COLLECTION_CODE, position, target_ovr]
    if exclude_card_ids:
        exclude_sql = f"AND cards.id NOT IN ({','.join('?' for _ in exclude_card_ids)})"
        params.extend(sorted(exclude_card_ids))
    row = connection.execute(
        f"""
        SELECT cards.*, collections.name AS collection_name, collections.code AS collection_code
        FROM cards
        JOIN collections ON collections.id = cards.collection_id
        WHERE cards.active = 1 AND collections.active = 1
          AND TRIM(collections.name) COLLATE NOCASE != ?
          AND TRIM(COALESCE(collections.code, '')) COLLATE NOCASE != ?
          AND cards.position = ? AND cards.overall = ?
          {exclude_sql}
        ORDER BY RANDOM()
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row is not None:
        return row
    # If there are too few unique cards of the position, duplicates are allowed,
    # but the printed OVR still must match exactly.
    return connection.execute(
        """
        SELECT cards.*, collections.name AS collection_name, collections.code AS collection_code
        FROM cards
        JOIN collections ON collections.id = cards.collection_id
        WHERE cards.active = 1 AND collections.active = 1
          AND TRIM(collections.name) COLLATE NOCASE != ?
          AND TRIM(COALESCE(collections.code, '')) COLLATE NOCASE != ?
          AND cards.position = ? AND cards.overall = ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (BOT_BLOCKED_COLLECTION_NAME, BOT_BLOCKED_COLLECTION_CODE, position, target_ovr),
    ).fetchone()


@dataclass(frozen=True)
class BotLineupResult:
    overview: LineupOverview
    target_ovr: int
    league: str
    missing_slots: tuple[str, ...]


async def build_bot_lineup(league: str | None, *, target_ovr: int | None = None) -> BotLineupResult:
    """Build 3F/2D/1G from real cards with one exact printed OVR.

    `target_ovr` is supplied by live Ranked matchmaking. When omitted, the old
    league-range picker remains available for admin diagnostics and legacy tests.
    """
    league_code = (league or "NCAA").upper()
    target_ovr = pick_target_ovr(league_code) if target_ovr is None else max(1, min(99, int(target_ovr)))

    slots: dict[str, LineupCard | None] = {code: None for code in LINEUP_SLOT_ORDER}
    used_card_ids: set[int] = set()
    missing_slots: list[str] = []

    with get_connection() as connection:
        for slot_code in LINEUP_SLOT_ORDER:
            slot = get_slot_info(slot_code)
            row = _select_real_card(
                connection,
                position=slot.position,
                target_ovr=target_ovr,
                exclude_card_ids=used_card_ids,
            )
            if row is None:
                logger.warning(
                    "ranked_bot: нет реальной карты позиции %s ровно %s OVR (лига %s)",
                    slot.position, target_ovr, league_code,
                )
                missing_slots.append(slot_code)
                continue

            used_card_ids.add(int(row["id"]))
            slots[slot_code] = LineupCard(
                user_card_id=-(1000 * (len(used_card_ids) + 1) + int(row["id"])),
                card_id=int(row["id"]), name=row["name"], player_key=row["player_key"],
                position=row["position"], overall=int(row["overall"]), team=row["team"],
                country=row["country"], collection_name=row["collection_name"], rarity=row["rarity"],
                image_path=row["image_path"], lineup_slot=slot_code, collection_code=row["collection_code"],
                salary=int(row["salary"] or 0),
            )

    cards = [card for card in slots.values() if card is not None]
    filled_count = len(cards)
    average_overall = round(sum(card.overall for card in cards) / filled_count) if filled_count else None

    chemistry_result = await calculate_chemistry([
        ChemistryCard(country=card.country, team=card.team, collection_name=card.collection_name, collection_code=card.collection_code)
        for card in cards
    ])
    final_overall = average_overall + chemistry_result.total_bonus if average_overall is not None else None

    overview = LineupOverview(
        slots=slots, filled_count=filled_count, total_slots=len(LINEUP_SLOT_ORDER),
        average_overall=average_overall, chemistry_bonus=chemistry_result.total_bonus,
        final_overall=final_overall, chemistry_bonuses=chemistry_result.bonuses,
        is_complete=filled_count == len(LINEUP_SLOT_ORDER),
        salary_total=sum(card.salary for card in cards), salary_cap=0,
    )
    return BotLineupResult(overview=overview, target_ovr=target_ovr, league=league_code, missing_slots=tuple(missing_slots))


async def diagnose_catalog_coverage() -> list[dict]:
    """Админ-диагностика: сколько реальных активных карт есть в каталоге рядом с
    диапазоном каждой Ranked-лиги, по позициям — чтобы заранее видеть нехватку карт
    для генерации ботов (ТЗ "Добавь административную диагностику недостатка карт
    по каждой лиге")."""
    report: list[dict] = []
    with get_connection() as connection:
        for league_code, (low, high) in RANKED_BOT_LEAGUE_OVR_RANGES.items():
            position_counts = {}
            for position in ("G", "D", "F"):
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM cards
                    JOIN collections ON collections.id = cards.collection_id
                    WHERE cards.active = 1 AND collections.active = 1
                      AND TRIM(collections.name) COLLATE NOCASE != ?
                      AND TRIM(COALESCE(collections.code, '')) COLLATE NOCASE != ?
                      AND cards.position = ? AND cards.overall BETWEEN ? AND ?
                    """,
                    (BOT_BLOCKED_COLLECTION_NAME, BOT_BLOCKED_COLLECTION_CODE, position, low, high),
                ).fetchone()
                position_counts[position] = int(row["n"])
            report.append(
                {
                    "league": league_code,
                    "range": (low, high),
                    "counts": position_counts,
                    "sufficient": all(count > 0 for count in position_counts.values()),
                }
            )
    return report
