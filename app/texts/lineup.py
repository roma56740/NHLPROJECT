from html import escape

from app.services.lineup import (
    LINEUP_SLOT_ORDER,
    LineupCardsPage,
    LineupOverview,
    get_slot_info,
)


LINEUP_EMPTY_TEXT = """
<b>🧩 Состав</b>

Команда пока не собрана.
Выбери слоты ниже и поставь карточки из коллекции.

Формат состава:
🥅 1 вратарь
🛡 2 защитника
⚡ 3 нападающих
""".strip()

LINEUP_CLEAR_CONFIRM_TEXT = """
<b>🧹 Очистить состав?</b>

Все карточки будут сняты со своих позиций и останутся в коллекции.
""".strip()

LINEUP_COMPLETE_NOTE = "🏒 Состав готов к матчам."
LINEUP_INCOMPLETE_NOTE = "⏳ Для матчей нужно заполнить все 6 слотов."


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def build_lineup_text(overview: LineupOverview) -> str:
    if overview.filled_count == 0:
        return LINEUP_EMPTY_TEXT

    lines: list[str] = []

    for slot_code in LINEUP_SLOT_ORDER:
        slot = get_slot_info(slot_code)
        card = overview.slots.get(slot_code)

        if card is None:
            lines.append(f"{slot.icon} <b>{safe(slot.title)}</b>: свободно")
            continue

        lines.append(
            f"{slot.icon} <b>{safe(slot.title)}</b>: {safe(card.name)} · {card.overall} OVR · {safe(card.rarity)}"
        )

    average_line = "—" if overview.average_overall is None else str(overview.average_overall)
    final_line = "—" if overview.final_overall is None else str(overview.final_overall)
    chemistry_line = f"+{overview.chemistry_bonus}" if overview.chemistry_bonus > 0 else "—"
    note = LINEUP_COMPLETE_NOTE if overview.is_complete else LINEUP_INCOMPLETE_NOTE

    chemistry_lines: list[str] = []

    for bonus in overview.chemistry_bonuses:
        chemistry_lines.append(
            f"{bonus.icon} <b>{safe(bonus.value)}</b>: {bonus.matched_cards}/{bonus.required_cards} · +{bonus.bonus_ovr} OVR"
        )

    chemistry_block = "\n".join(chemistry_lines) if chemistry_lines else "Пока нет активных бонусов."

    return f"""
<b>🧩 Состав</b>

Готовность: <b>{overview.filled_count}/{overview.total_slots}</b>
Средний OVR: <b>{average_line}</b>
🧪 Химия: <b>{chemistry_line}</b>
⭐ Итоговый OVR: <b>{final_line}</b>

{chr(10).join(lines)}

<b>🧪 Активная химия</b>
{chemistry_block}

{note}
""".strip()


def build_slot_cards_text(page: LineupCardsPage) -> str:
    slot = get_slot_info(page.slot_code)

    if page.total_count == 0:
        return f"""
<b>{slot.icon} {safe(slot.title)}</b>

Подходящих карточек пока нет.
Открой паки или получи нужные карты, затем вернись к составу.
""".strip()

    return f"""
<b>{slot.icon} {safe(slot.title)}</b>

Подходящих карточек: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

Выбери карточку для позиции.
""".strip()
