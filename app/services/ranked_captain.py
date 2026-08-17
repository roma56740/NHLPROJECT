"""Капитан Ranked-состава (см. ТЗ "НОВАЯ СИСТЕМА КАПИТАНОВ В RANKED MODE").

Ranked Mode не имеет отдельной таблицы состава — переиспользует общий
`user_cards.is_in_lineup/lineup_slot` через `app.services.lineup.get_lineup_overview()`
(тот же приём, что и весь остальной Ranked-код, см. `docs/RANKED_MODE_SPEC.md`).
Капитан поэтому хранится минимально — ссылка user_id -> user_card_id
(`ranked_captains`), один активный на пользователя. Дивизион капитана НЕ хранится
отдельным полем (запрет ТЗ на дублирование) — каждый раз заново резолвится через
существующую систему дивизионов карточек (`app.services.admin_divisions.
get_division_for_team`, таблицы `team_divisions`/`team_division_teams`), то есть
если админ поменяет дивизион команды карты, статус капитана это увидит на
следующий же расчёт без какой-либо отдельной миграции данных.

`get_captain_status()` ничего не кэширует и пересчитывается с нуля при каждом
вызове (экран, до матча, после любого изменения состава) — ровно то, что требует
ТЗ ("прогресс должен пересчитываться после ... входа в Ranked Mode, просмотра
состава, запуска матча"). Он же обнаруживает и автоматически снимает капитана,
если тот больше не входит в активный Ranked-состав (карта убрана/заменена).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.database.db import get_connection
from app.services.admin_divisions import get_division_for_team
from app.services.lineup import LineupCard, get_lineup_overview
from app.services.ranked_common import RankedError
from app.services.salary import RANKED_CAPTAIN_BONUS, RANKED_CAPTAIN_MIN_DIVISION_CARDS, RANKED_SALARY_CAP

REQUIRED_DIVISION_CARDS = RANKED_CAPTAIN_MIN_DIVISION_CARDS


@dataclass(frozen=True)
class CaptainStatus:
    user_card_id: int | None
    card_name: str | None
    division_code: str | None
    division_name: str | None
    division_count: int
    required_count: int
    bonus_active: bool
    bonus_amount: int
    base_cap: int
    effective_cap: int
    salary_total: int
    is_over_cap: bool
    overage: int


def _load_captain_user_card_id(user_id: int) -> int | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT user_card_id FROM ranked_captains WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row["user_card_id"]) if row is not None else None


def _clear_captain_row(user_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM ranked_captains WHERE user_id = ?", (user_id,))
        connection.commit()


async def get_captain_status(user_id: int) -> CaptainStatus:
    overview = await get_lineup_overview(user_id)
    lineup_cards: dict[int, LineupCard] = {
        card.user_card_id: card for card in overview.slots.values() if card is not None
    }

    captain_user_card_id = _load_captain_user_card_id(user_id)
    captain_card: LineupCard | None = None
    if captain_user_card_id is not None:
        captain_card = lineup_cards.get(captain_user_card_id)
        if captain_card is None:
            # Капитан больше не в составе (удалён/заменён/перемещён в другой слот
            # не бывает — lineup_slot меняется только через set_lineup_card, но
            # карта могла быть заменена другой) -> капитанство снимается сама собой.
            _clear_captain_row(user_id)
            captain_user_card_id = None

    division_code: str | None = None
    division_name: str | None = None
    division_count = 0
    bonus_active = False

    if captain_card is not None:
        division = await get_division_for_team(captain_card.team)
        if division is not None:
            division_code = division.code
            division_name = division.name
            for card in lineup_cards.values():
                card_division = await get_division_for_team(card.team)
                if card_division is not None and card_division.code == division_code:
                    division_count += 1
            bonus_active = division_count >= REQUIRED_DIVISION_CARDS

    bonus_amount = RANKED_CAPTAIN_BONUS if bonus_active else 0
    effective_cap = RANKED_SALARY_CAP + bonus_amount
    salary_total = overview.salary_total
    overage = max(0, salary_total - effective_cap)

    return CaptainStatus(
        user_card_id=captain_user_card_id,
        card_name=captain_card.name if captain_card is not None else None,
        division_code=division_code,
        division_name=division_name,
        division_count=division_count,
        required_count=REQUIRED_DIVISION_CARDS,
        bonus_active=bonus_active,
        bonus_amount=bonus_amount,
        base_cap=RANKED_SALARY_CAP,
        effective_cap=effective_cap,
        salary_total=salary_total,
        is_over_cap=overage > 0,
        overage=overage,
    )


async def assign_captain(user_id: int, user_card_id: int) -> CaptainStatus:
    """Капитаном можно назначить только карту, реально стоящую в ТЕКУЩЕМ активном
    Ranked-составе ЭТОГО пользователя — `get_lineup_overview(user_id)` уже
    фильтрует по `user_cards.user_id`, поэтому подмена callback_data чужим/
    несуществующим/не-в-составе user_card_id естественно не находит карту здесь
    и получает RankedError, без отдельной ручной проверки владения."""
    overview = await get_lineup_overview(user_id)
    lineup_cards = {card.user_card_id: card for card in overview.slots.values() if card is not None}
    card = lineup_cards.get(user_card_id)
    if card is None:
        raise RankedError(
            "CAPTAIN_CARD_NOT_IN_LINEUP",
            "Эта карточка не найдена в твоём текущем Ranked-составе.",
        )

    division = await get_division_for_team(card.team)
    if division is None:
        raise RankedError(
            "CAPTAIN_NO_DIVISION",
            "У этой карты нет дивизиона, её нельзя назначить капитаном.",
        )

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ranked_captains (user_id, user_card_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_card_id = excluded.user_card_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, user_card_id),
        )
        connection.commit()

    return await get_captain_status(user_id)


async def remove_captain(user_id: int) -> None:
    _clear_captain_row(user_id)
