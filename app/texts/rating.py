from html import escape

from app.services.rating import (
    LEAGUE_LIMIT,
    LeaderboardPage,
    RatingProfile,
    get_league_progress_items,
)


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def percent(wins: int, matches: int) -> int:
    if matches <= 0:
        return 0

    return round(wins / matches * 100)


def place(value: int | None) -> str:
    if value is None:
        return "—"

    return f"#{value}"


def build_rating_main_text(profile: RatingProfile) -> str:
    ovr = profile.lineup_ovr if profile.lineup_ovr is not None else "—"
    winrate = percent(profile.wins, profile.matches_played)

    if profile.next_league is None:
        progress = "🏆 Высшая лига открыта. Вылет из OLYMPICS отключён."
    else:
        progress = (
            f"До лиги <b>{safe(profile.next_league)}</b>: "
            f"<b>{profile.points_to_next_league}</b> / {LEAGUE_LIMIT} очков"
        )

    return f"""
<b>🏆 Рейтинг</b>

👤 Игрок: <b>{safe(profile.nickname)}</b>
🏒 Лига: <b>{safe(profile.league)}</b>
📈 Очки: <b>{profile.rating_points}</b>

{progress}

<b>📊 Позиции</b>
🏆 В своей лиге: <b>{place(profile.league_place)}</b>
🌍 Общий зачёт: <b>{place(profile.global_place)}</b>

<b>🧩 Состав</b>
⭐ OVR: <b>{ovr}</b>
📌 Заполнено: <b>{profile.lineup_filled_count}/{profile.lineup_total_slots}</b>

<b>🏒 Статистика</b>
📊 Матчи: <b>{profile.matches_played}</b>
✅ Победы: <b>{profile.wins}</b>
❌ Поражения: <b>{profile.losses}</b>
🎯 Победы: <b>{winrate}%</b>
🥅 Голы: <b>{profile.goals_scored}</b>
🧤 Пропущено: <b>{profile.goals_allowed}</b>
""".strip()


def build_leaderboard_text(page: LeaderboardPage) -> str:
    if page.total_count == 0:
        return f"""
<b>{safe(page.title)}</b>

Пока нет игроков в таблице.
Первые матчи сразу откроют борьбу за места.
""".strip()

    lines: list[str] = []

    for entry in page.entries:
        medal = get_medal(entry.place)
        ovr = entry.lineup_ovr if entry.lineup_ovr > 0 else "—"
        winrate = percent(entry.wins, entry.matches_played)
        lines.append(
            f"{medal} <b>{entry.place}. {safe(entry.nickname)}</b> · {safe(entry.league)}\n"
            f"📈 {entry.rating_points} очков · ✅ {entry.wins} · 🎯 {winrate}% · ⭐ OVR {ovr}"
        )

    return f"""
<b>{safe(page.title)}</b>

Игроков в зачёте: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

{chr(10).join(lines)}
""".strip()


def get_medal(place_number: int) -> str:
    if place_number == 1:
        return "🥇"
    if place_number == 2:
        return "🥈"
    if place_number == 3:
        return "🥉"
    return "🏒"


def build_leagues_text(current_league: str | None = None) -> str:
    lines: list[str] = []

    for item in get_league_progress_items():
        mark = "✅" if item.code == current_league else "▫️"
        lines.append(
            f"{mark} <b>{safe(item.title)}</b>\n"
            f"{safe(item.description)}\n"
            f"🎁 {safe(item.reward)}"
        )

    return f"""
<b>🏒 Лиги</b>

Для перехода между лигами нужно набрать <b>{LEAGUE_LIMIT}</b> очков.
Очки начисляются за матчи и зависят от силы соперника.

{chr(10).join(lines)}
""".strip()
