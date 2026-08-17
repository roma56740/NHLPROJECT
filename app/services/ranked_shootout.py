"""Pure rules for the interactive Ranked shootout mini-game.

Telegram waiting/timeout orchestration lives in ``app.handlers.ranked``.  This
module intentionally contains only deterministic rules so they can be tested
without aiogram:

* shooter did not answer -> no goal;
* goalie did not answer -> goal (provided the shooter answered);
* equal corners -> save;
* different corners -> goal.
"""

from __future__ import annotations

from dataclasses import dataclass

CORNERS: tuple[str, ...] = ("TL", "TR", "BL", "BR")
CORNER_TITLES: dict[str, str] = {
    "TL": "↖️ Верхний левый",
    "TR": "↗️ Верхний правый",
    "BL": "↙️ Нижний левый",
    "BR": "↘️ Нижний правый",
}


@dataclass(frozen=True)
class ShootoutAttemptResult:
    shooter_corner: str | None
    goalie_corner: str | None
    is_goal: bool
    reason: str


def normalize_corner(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized if normalized in CORNERS else None


def resolve_attempt(shooter_corner: str | None, goalie_corner: str | None) -> ShootoutAttemptResult:
    """Resolve one penalty shot according to the product rules."""
    shooter = normalize_corner(shooter_corner)
    goalie = normalize_corner(goalie_corner)

    if shooter is None:
        return ShootoutAttemptResult(None, goalie, False, "shooter_timeout")
    if goalie is None:
        return ShootoutAttemptResult(shooter, None, True, "goalie_timeout")
    if shooter == goalie:
        return ShootoutAttemptResult(shooter, goalie, False, "save")
    return ShootoutAttemptResult(shooter, goalie, True, "goal")


def corner_title(value: str | None) -> str:
    normalized = normalize_corner(value)
    return CORNER_TITLES.get(normalized or "", "—")


def is_regulation_clinched(
    user_goals: int,
    opponent_goals: int,
    user_attempts: int,
    opponent_attempts: int,
    *,
    scheduled_attempts: int = 3,
) -> bool:
    """Return True once a side cannot be caught during the first three attempts."""
    user_remaining = max(0, scheduled_attempts - user_attempts)
    opponent_remaining = max(0, scheduled_attempts - opponent_attempts)
    return (
        user_goals > opponent_goals + opponent_remaining
        or opponent_goals > user_goals + user_remaining
    )
