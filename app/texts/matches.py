from html import escape

from app.services.matches import (
    EVENT_ICONS,
    MatchDetails,
    MatchEventInfo,
    MatchHistoryPage,
    MatchMainInfo,
    MatchPlayResult,
)


MATCH_SEARCH_TEXT = """
<b>🏒 Поиск соперника</b>

Команда вышла на лёд и ждёт достойного соперника.
Сначала ищем реального игрока с похожей силой состава.

Если соперник не найдётся, лига выставит команду-бота.
""".strip()

MATCH_ALREADY_SEARCHING_TEXT = """
<b>🏒 Поиск уже идёт</b>

Команда остаётся на разминке.
Как только соперник появится, матч начнётся автоматически.
""".strip()

MATCH_CANCELLED_TEXT = """
<b>❌ Поиск остановлен</b>

Команда вернулась в раздевалку.
Можно начать новый поиск в любой момент.
""".strip()


def build_match_playing_text(opponent_name: str, opponent_type: str = "bot") -> str:
    opponent_line = "реальный соперник" if opponent_type == "player" else "команда-бот"

    return f"""
<b>🔥 Матч идёт</b>

Соперник найден: <b>{safe(opponent_name)}</b>
Тип соперника: <b>{opponent_line}</b>

🥅 Идут периоды, броски и борьба за шайбу.
Матч длится ровно <b>1 минуту</b>.
Голы будут появляться прямо во время игры.
""".strip()



def build_match_no_goal_live_text(result: MatchPlayResult) -> str:
    opponent_type = "реальный соперник" if result.opponent_type == "player" else "команда-бот"

    return f"""
<b>🔥 Матч идёт</b>

Соперник: <b>{safe(result.opponent_name)}</b>
Тип соперника: <b>{opponent_type}</b>

Счёт: <b>0 — 0</b>

🧤 Вратари ловят всё подряд.
Команды держат темп, трибуны ждут первый гол.
""".strip()


def build_match_goal_live_text(
    result: MatchPlayResult,
    *,
    event: MatchEventInfo | None,
    user_score: int,
    opponent_score: int,
    scorer_side: str,
) -> str:
    if scorer_side == "user":
        title = "🥅 Шайба в воротах!"
        side_line = "Твоя команда выходит вперёд!" if user_score > opponent_score else "Твоя команда возвращается в игру!"
    else:
        title = "🚨 Соперник забивает"
        side_line = f"{safe(result.opponent_name)} меняет ход матча."

    description = safe(event.description) if event is not None else side_line
    moment = ""

    if event is not None:
        moment = f"\n🏒 Момент: <b>{safe(event.period_title)}</b> · {safe(event.time_text)}"

    if user_score == opponent_score:
        score_note = "Матч снова равный. Всё решится дальше."
    elif user_score > opponent_score:
        score_note = "Твоя команда впереди, но расслабляться рано."
    else:
        score_note = "Нужно отыгрываться. Матч ещё не закончен."

    return f"""
<b>{title}</b>

{side_line}

Счёт: <b>{user_score}</b> — <b>{opponent_score}</b>{moment}

🔥 {description}

{score_note}
""".strip()


def build_match_queue_fallback_text() -> str:
    return """
<b>🏒 Соперник не найден</b>

Свободных игроков рядом по силе сейчас нет.
Лига выпускает на лёд команду-бота.
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def signed(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def build_match_main_text(info: MatchMainInfo) -> str:
    ready_line = "✅ Команда готова к игре" if info.is_ready else "⏳ Сначала заполни все 6 слотов состава"
    ovr_line = info.lineup_ovr if info.lineup_ovr is not None else "—"

    return f"""
<b>🏒 Играть</b>

{ready_line}

🧩 Состав: <b>{info.filled_count}/{info.total_slots}</b>
⭐ OVR состава: <b>{ovr_line}</b>
🏆 Лига: <b>{safe(info.league)}</b>
📈 Очки: <b>{info.rating_points}</b>

📊 Матчи: <b>{info.matches_played}</b>
✅ Победы: <b>{info.wins}</b>
❌ Поражения: <b>{info.losses}</b>

Нажми поиск, чтобы найти реального соперника. Если игроков рядом нет, матч пройдёт против команды-бота.
""".strip()


def build_match_not_ready_text(message: str) -> str:
    return f"""
<b>🧩 Состав не готов</b>

{safe(message)}

Заполни вратаря, двух защитников и трёх нападающих, затем возвращайся на лёд.
""".strip()


def build_match_result_text(result: MatchPlayResult) -> str:
    status = "✅ Победа" if result.result == "win" else "❌ Поражение"
    opponent_type = "реальный игрок" if result.opponent_type == "player" else "команда-бот"
    extra = ""

    if result.is_overtime:
        extra = "\n⏱ Матч завершился в овертайме."
    elif result.is_shootout:
        extra = "\n🎯 Матч завершился по буллитам."

    coins = ""
    if result.coins_reward > 0:
        coins = f"\n🪙 Coins: <b>+{result.coins_reward}</b>"

    rank_points = ""
    if result.rank_points_reward > 0:
        rank_points = f"\n🏅 Rank-point: <b>+{result.rank_points_reward}</b>"

    league = ""
    if result.league_before != result.league_after:
        league = f"\n🏆 Новая лига: <b>{safe(result.league_after)}</b>"

    periods = ""
    if result.periods:
        period_lines = [
            f"{safe(period.title)}: <b>{period.user_goals}-{period.opponent_goals}</b> · броски {period.user_shots}-{period.opponent_shots}"
            for period in result.periods
        ]
        periods = "\n\n<b>Периоды</b>\n" + "\n".join(period_lines)

    event_lines: list[str] = []
    if result.events:
        for event in result.events[:10]:
            icon = EVENT_ICONS.get(event.event_type, "🏒")
            event_lines.append(
                f"{icon} {safe(event.period_title)} · {safe(event.time_text)} — {safe(event.description)}"
            )

    events = ""
    if event_lines:
        events = "\n\n<b>Главные моменты</b>\n" + "\n".join(event_lines)

    return f"""
<b>🏒 Матч завершён</b>

{status}

Ты <b>{result.user_score}</b> — <b>{result.opponent_score}</b> {safe(result.opponent_name)}{extra}

👥 Соперник: <b>{opponent_type}</b>
⭐ OVR: <b>{result.user_lineup_ovr}</b> — <b>{result.opponent_lineup_ovr}</b>
🏅 MVP: <b>{safe(result.mvp_title)}</b>
📈 Очки рейтинга: <b>{signed(result.rating_delta)}</b>{coins}{rank_points}{league}{periods}{events}
""".strip()


def build_match_history_text(page: MatchHistoryPage) -> str:
    if page.total_count == 0:
        return """
<b>📜 История матчей</b>

Матчей пока нет.
Собери состав и выходи на лёд.
""".strip()

    lines: list[str] = []

    for match in page.matches:
        status = "✅" if match.result == "win" else "❌"
        lines.append(
            f"{status} <b>{match.user_score}-{match.opponent_score}</b> против {safe(match.opponent_name)}\n"
            f"📈 {signed(match.rating_delta)} · 🕒 {safe(match.created_at)}"
        )

    return f"""
<b>📜 История матчей</b>

Всего матчей: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

{chr(10).join(lines)}
""".strip()


def build_match_details_text(match: MatchDetails) -> str:
    status = "✅ Победа" if match.result == "win" else "❌ Поражение"
    opponent_type = "реальный игрок" if match.opponent_type == "player" else "команда-бот"
    extra = ""

    if match.is_overtime:
        extra = "\n⏱ Овертайм"
    elif match.is_shootout:
        extra = "\n🎯 Буллиты"

    period_lines = [
        f"{safe(period.title)}: <b>{period.user_goals}-{period.opponent_goals}</b> · броски {period.user_shots}-{period.opponent_shots} · владение {period.possession_user}%"
        for period in match.periods
    ]
    events = [
        f"{EVENT_ICONS.get(event.event_type, '🏒')} {safe(event.period_title)} · {safe(event.time_text)} — {safe(event.description)}"
        for event in match.events[:14]
    ]

    rewards = ""
    if match.coins_reward > 0:
        rewards += f"\n🪙 Coins: <b>+{match.coins_reward}</b>"
    if match.rank_points_reward > 0:
        rewards += f"\n🏅 Rank-point: <b>+{match.rank_points_reward}</b>"

    league = ""
    if match.league_before != match.league_after:
        league = f"\n🏆 Лига: <b>{safe(match.league_before)}</b> → <b>{safe(match.league_after)}</b>"

    return f"""
<b>🏒 Матч #{match.id}</b>

{status}

Ты <b>{match.user_score}</b> — <b>{match.opponent_score}</b> {safe(match.opponent_name)}{extra}

👥 Соперник: <b>{opponent_type}</b>
⭐ OVR: <b>{match.user_lineup_ovr}</b> — <b>{match.opponent_lineup_ovr}</b>
🏅 MVP: <b>{safe(match.mvp_title)}</b>
📈 Очки рейтинга: <b>{signed(match.rating_delta)}</b>{rewards}{league}
🕒 {safe(match.created_at)}

<b>Периоды</b>
{chr(10).join(period_lines) if period_lines else 'Периоды не найдены.'}

<b>Моменты</b>
{chr(10).join(events) if events else 'Главные моменты не найдены.'}
""".strip()


def build_match_captcha_text(prompt: str, retry: str = "") -> str:
    head = f"{retry}\n\n" if retry else ""
    return (
        f"{head}<b>🤖 Проверка перед матчем</b>\n\n"
        f"{prompt}\n\n"
        f"<i>Это защита от автокликеров. Займёт пару секунд.</i>"
    )

