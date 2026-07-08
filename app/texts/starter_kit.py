from html import escape

from app.services.starter_kit import (
    POSITION_NAMES,
    STARTER_KIT_SLOTS,
    StarterKitCardsPage,
    StarterKitOverview,
)


def safe(value: object | None) -> str:
    text = str(value or "").strip()
    return escape(text, quote=False) if text else "не указано"


def build_starter_kit_main_text(overview: StarterKitOverview) -> str:
    status = "✅ готов" if overview.is_complete else "⏳ не заполнен полностью"
    rows: list[str] = []

    for slot_code, slot in STARTER_KIT_SLOTS.items():
        card = overview.slots.get(slot_code)

        if card is None:
            rows.append(f"{slot.icon} <b>{safe(slot.title)}</b>: не выбран")
            continue

        rows.append(
            f"{slot.icon} <b>{safe(slot.title)}</b>: {safe(card.name)} • {card.overall} OVR • {safe(card.collection_name)}"
        )

    return f"""
<b>🏁 Стартовый набор</b>

Здесь выбираются карточки, которые новый игрок получит при первом запуске бота.

Статус: <b>{status}</b>
Заполнено: <b>{overview.filled_count}/{overview.total_count}</b>

{chr(10).join(rows)}

После входа нового игрока бот тихо выдаст выбранные карточки и сразу поставит их в состав.
Если набор пустой, игрок начнёт без стартовых карт.
""".strip()


def build_starter_kit_cards_text(page: StarterKitCardsPage) -> str:
    slot = STARTER_KIT_SLOTS[page.slot_code]
    position_name = POSITION_NAMES.get(slot.position, slot.position)

    if page.total_count == 0:
        return f"""
<b>{slot.icon} {safe(slot.title)}</b>

Для этой позиции пока нет активных карточек.
Сначала добавь карточки в разделе <b>🃏 Карточки</b>, потом вернись к стартовому набору.
""".strip()

    return f"""
<b>{slot.icon} {safe(slot.title)}</b>

Выбери карточку для стартового состава.
Ниже показаны активные {safe(position_name)} от самого слабого OVR к более сильному.

Карточек: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>
""".strip()


STARTER_KIT_CARD_SELECTED_TEXT = "✅ Карточка добавлена в стартовый набор."
STARTER_KIT_SLOT_CLEARED_TEXT = "🧹 Слот стартового набора очищен."
STARTER_KIT_CLEARED_TEXT = "🧹 Стартовый набор очищен."
STARTER_KIT_NOT_FOUND_TEXT = "Карточка не найдена или не подходит для этого слота."
