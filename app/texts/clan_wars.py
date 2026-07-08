from html import escape

from app.services.clan_wars import ArenaInfo, ATTACK_DURATION_HOURS


WARS_MAIN_TEXT = """
<b>🏟 Войны кланов</b>

Кланы сражаются за арены NHL.

⚔️ Президент или вице-президент объявляет атаку на арену — у клана есть 24 часа.
🏒 Каждая победа участника клана в матче приносит +1 очко атаки.
🏰 Набрали нужное число побед — арена ваша.
💰 Пока арена под контролем клана, каждый участник получает ежедневный доход.

Выбери арену ниже.
""".strip()

WARS_NO_ARENAS_TEXT = """
<b>🏟 Войны кланов</b>

Арены пока готовятся к открытию. Загляни позже!
""".strip()


def format_income_line(arena: ArenaInfo) -> str:
    if arena.income_currency_code and arena.income_amount > 0:
        return f"{arena.income_currency_icon} {arena.income_currency_name} — <b>{arena.income_amount}</b> в день каждому"
    return "без дохода"


def format_capture_reward_line(arena: ArenaInfo) -> str:
    if arena.capture_currency_code and arena.capture_amount > 0:
        return f"{arena.capture_currency_icon} {arena.capture_currency_name} — <b>{arena.capture_amount}</b> каждому"
    return "без бонуса"


def build_arena_profile_text(arena: ArenaInfo, viewer_clan_id: int | None = None, admin: bool = False) -> str:
    holder = escape(arena.holder_clan_name, quote=False) if arena.holder_clan_name else "нейтральная"
    lines = [
        f"<b>🏟 {escape(arena.name, quote=False)}</b>",
    ]
    if not arena.active:
        lines.append("📌 Статус: <b>закрыта</b>")
    lines.extend(
        [
            f"🏰 Владелец: <b>{holder}</b>",
            f"🎯 Побед для захвата: <b>{arena.capture_wins_required}</b>",
            f"💰 Доход: {format_income_line(arena)}",
            f"🎁 Бонус за захват: {format_capture_reward_line(arena)}",
        ]
    )

    if arena.description:
        lines.extend(["", escape(arena.description, quote=False)])

    if arena.attacks:
        lines.append("\n<b>⚔️ Идут атаки</b>")
        for attack in arena.attacks:
            marker = " ← ваш клан" if viewer_clan_id is not None and attack.clan_id == viewer_clan_id else ""
            lines.append(
                f"🏰 <b>{escape(attack.clan_name, quote=False)}</b> — {attack.points}/{arena.capture_wins_required} побед{marker}"
            )
    elif not admin:
        lines.append(f"\n⚔️ Атак сейчас нет. Атака длится {ATTACK_DURATION_HOURS} часа.")

    return "\n".join(lines)


ADMIN_ARENAS_MAIN_TEXT = """
<b>🏟 Арены — управление</b>

Здесь настраиваются арены для войн кланов: награды за захват, ежедневный доход и сложность.

Максимум 9 арен. Все параметры каждой арены можно менять в её карточке.
""".strip()

ARENA_CREATE_NAME_TEXT = """
<b>🏟 Новая арена — шаг 1 из 6</b>

Введи название арены (3–48 символов).

Например: Madison Square Garden.
""".strip()

ARENA_CREATE_DESCRIPTION_TEXT = """
<b>🏟 Новая арена — шаг 2 из 6</b>

Введи короткое описание арены (до 300 символов) или отправь «-», чтобы пропустить.
""".strip()

ARENA_CREATE_WINS_TEXT = """
<b>🏟 Новая арена — шаг 3 из 6</b>

Сколько побед нужно клану за 24 часа, чтобы захватить арену?

Введи число от 1 до 500.
""".strip()

ARENA_CREATE_INCOME_CURRENCY_TEXT = """
<b>🏟 Новая арена — шаг 4 из 6</b>

Выбери валюту ежедневного дохода. Её будет получать каждый участник клана-владельца раз в сутки.
""".strip()

ARENA_CREATE_INCOME_AMOUNT_TEXT = """
<b>🏟 Новая арена — шаг 5 из 6</b>

Введи сумму ежедневного дохода (целое число, 0 — без дохода).
""".strip()

ARENA_CREATE_CAPTURE_CURRENCY_TEXT = """
<b>🏟 Новая арена — шаг 6 из 6</b>

Выбери валюту бонуса за захват. Её получит каждый участник клана сразу после захвата арены.
""".strip()

ARENA_CREATE_CAPTURE_AMOUNT_TEXT = """
<b>🏟 Бонус за захват</b>

Введи сумму бонуса за захват (целое число, 0 — без бонуса).
""".strip()

ARENA_EDIT_NAME_TEXT = "<b>✏️ Введи новое название арены</b> (3–48 символов)."
ARENA_EDIT_DESCRIPTION_TEXT = "<b>✏️ Введи новое описание арены</b> (до 300 символов, «-» — очистить)."
ARENA_EDIT_WINS_TEXT = "<b>🎯 Введи число побед для захвата</b> (от 1 до 500)."
ARENA_EDIT_INCOME_AMOUNT_TEXT = "<b>💰 Введи сумму ежедневного дохода</b> (0 — без дохода)."
ARENA_EDIT_CAPTURE_AMOUNT_TEXT = "<b>🎁 Введи сумму бонуса за захват</b> (0 — без бонуса)."
