from html import escape

from app.services.events import (
    AdminEventPage,
    AdminEventProfile,
    EventClaimResult,
    EventDraft,
    EventItem,
    EVENT_REWARD_TITLES,
    EVENT_TARGET_TITLES,
    UserEventPage,
    UserEventProfile,
    format_msk_datetime,
    format_number,
)


ADMIN_EVENTS_MAIN_TEXT = """
<b>🎪 События</b>

Создавай большие игровые события, выбирай цель, награду и объявляй их всем игрокам.

Игроки увидят события в разделе <b>🎯 Задания → 🎪 События</b>.
""".strip()

EVENT_IMAGE_TEXT = """
<b>🖼 Обложка события</b>

Отправь картинку события.

Можно нажать <b>➡️ Без обложки</b>, если картинка не нужна.
""".strip()

EVENT_TITLE_TEXT = """
<b>✏️ Название события</b>

Отправь красивое название.

Пример: <b>DEAD LEGENDS I</b>
""".strip()

EVENT_DESCRIPTION_TEXT = """
<b>📝 Описание события</b>

Отправь описание для игроков.

Можно отправить <b>-</b>, если описание не нужно.
""".strip()

EVENT_TARGET_VALUE_TEXT = """
<b>🔢 Цель события</b>

Отправь число, до которого игрок должен дойти.

Пример: <b>400</b>
""".strip()

EVENT_REWARD_AMOUNT_TEXT = """
<b>🎁 Количество награды</b>

Отправь целое число.

Например: <b>1</b> для одной карточки или <b>50000</b> для валюты.
""".strip()

EVENT_END_AT_TEXT = """
<b>📅 Дата окончания</b>

Отправь дату окончания по МСК.

Формат: <b>31.07.2026 23:59</b>

Если событие постоянное, отправь <b>-</b>.
""".strip()

EVENT_SEARCH_TEXT = """
<b>🔎 Поиск события</b>

Отправь название, описание или тип цели.
""".strip()

EVENT_BAD_TITLE_TEXT = "Название должно быть от 3 до 80 символов."
EVENT_BAD_DESCRIPTION_TEXT = "Описание должно быть до 500 символов."
EVENT_BAD_NUMBER_TEXT = "Отправь целое число больше нуля."
EVENT_BAD_DATE_TEXT = "Отправь дату в формате 31.07.2026 23:59 или знак -."
EVENT_NOT_FOUND_TEXT = "Событие уже недоступно."
EVENT_SAVED_TEXT = "✅ Событие создано."
EVENT_UPDATED_TEXT = "✅ Событие обновлено."


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"
    text = str(value).strip()
    return escape(text, quote=False) if text else "не указано"


def build_progress_bar(progress: int, target: int, size: int = 10) -> str:
    if target <= 0:
        return "▫️" * size
    filled = min(size, max(0, round(progress / target * size)))
    return "🟪" * filled + "▫️" * (size - filled)


def build_user_events_page_text(page: UserEventPage) -> str:
    if page.total_count == 0:
        return """
<b>🎪 События</b>

Других активных событий сейчас нет.
""".strip()

    lines = [
        "<b>🎪 События</b>",
        "",
        f"Активных событий: <b>{page.total_count}</b>",
        f"Страница: <b>{page.page}/{page.pages_count}</b>",
        "",
    ]

    for index, event in enumerate(page.items, start=1):
        lines.append(format_user_event_short(index, event))
        lines.append("")

    lines.append("Открой событие, чтобы посмотреть награду и забрать приз.")
    return "\n".join(lines).strip()


def format_user_event_short(index: int, event: EventItem) -> str:
    progress = min(event.progress, event.target_value)
    status = "✅ Получено" if event.reward_claimed else "🎁 Готово" if event.completed else "🔥 В процессе"
    target = EVENT_TARGET_TITLES.get(event.target_type, event.target_type)
    return (
        f"<b>{index}. {safe(event.title)}</b>\n"
        f"🎯 Цель: <b>{safe(target)} — {event.target_value}</b>\n"
        f"{build_progress_bar(progress, event.target_value)} <b>{progress}/{event.target_value}</b>\n"
        f"🎁 Награда: <b>{safe(event.reward_title)}</b>\n"
        f"{status}"
    )


def build_user_event_profile_text(profile: UserEventProfile) -> str:
    progress = min(profile.progress, profile.target_value)
    status = "✅ Награда получена" if profile.reward_claimed else "🎁 Можно забрать" if profile.completed else "🔥 В процессе"
    target = EVENT_TARGET_TITLES.get(profile.target_type, profile.target_type)

    return f"""
<b>🎪 {safe(profile.title)}</b>

{safe(profile.description)}

🎯 Цель: <b>{safe(target)} — {profile.target_value}</b>
{build_progress_bar(progress, profile.target_value)} <b>{progress}/{profile.target_value}</b>

🎁 Награда: <b>{safe(profile.reward_title)}</b>
📅 До: <b>{format_msk_datetime(profile.end_at)}</b>

{status}
""".strip()


def build_event_claim_text(result: EventClaimResult) -> str:
    return f"""
<b>🎁 Награда события получена!</b>

{safe(result.reward_title)}

Продолжай играть и забирай новые призы.
""".strip()


def build_admin_events_page_text(page: AdminEventPage) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return """
<b>🎪 События</b>

Список пока пуст. Создай первое событие для игроков.
""".strip()

    return f"""
<b>🎪 События</b>

Всего событий: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери событие из списка ниже.
""".strip()


def build_admin_event_profile_text(profile: AdminEventProfile) -> str:
    status = "✅ активно" if profile.active else "⏸ отключено"
    announce = "📢 объявлено" if profile.announcement_sent else "▫️ ещё не объявлено"
    target = EVENT_TARGET_TITLES.get(profile.target_type, profile.target_type)
    reward_type = EVENT_REWARD_TITLES.get(profile.reward_type, profile.reward_type)

    return f"""
<b>🎪 Карточка события</b>

🏒 Название: <b>{safe(profile.title)}</b>
📝 Описание: <b>{safe(profile.description)}</b>

🎯 Цель: <b>{safe(target)}</b>
🔢 Нужно: <b>{profile.target_value}</b>
🎁 Награда: <b>{safe(profile.reward_title)}</b>
📦 Тип награды: <b>{safe(reward_type)}</b>

📅 Старт: <b>{format_msk_datetime(profile.start_at)}</b>
🏁 Конец: <b>{format_msk_datetime(profile.end_at)}</b>

📣 Объявление: <b>{announce}</b>
📌 Статус: <b>{status}</b>

👥 Участников: <b>{profile.progress_count}</b>
✅ Выполнили: <b>{profile.completed_count}</b>
🎁 Забрали награду: <b>{profile.claimed_count}</b>
""".strip()


def build_event_draft_text(draft: EventDraft) -> str:
    target = EVENT_TARGET_TITLES.get(draft.target_type, draft.target_type)
    reward_type = EVENT_REWARD_TITLES.get(draft.reward_type, draft.reward_type)

    return f"""
<b>✅ Проверь событие</b>

🏒 Название: <b>{safe(draft.title)}</b>
📝 Описание: <b>{safe(draft.description)}</b>

🎯 Цель: <b>{safe(target)}</b>
🔢 Нужно: <b>{draft.target_value}</b>

🎁 Тип награды: <b>{safe(reward_type)}</b>
📦 Количество: <b>{format_number(draft.reward_amount)}</b>
🏁 Завершение: <b>{format_msk_datetime(draft.end_at)}</b>

Если всё верно, создай событие.
""".strip()


def build_event_delete_text(profile: AdminEventProfile) -> str:
    return f"""
<b>🗑 Удалить событие?</b>

🎪 <b>{safe(profile.title)}</b>

Прогресс игроков по этому событию тоже будет удалён.
""".strip()


def build_event_announcement_text(profile: AdminEventProfile) -> str:
    target = EVENT_TARGET_TITLES.get(profile.target_type, profile.target_type)
    return f"""
<b>🎪 Новое событие!</b>

🔥 <b>{safe(profile.title)}</b>

{safe(profile.description)}

🎯 Цель: <b>{safe(target)} — {profile.target_value}</b>
🎁 Награда: <b>{safe(profile.reward_title)}</b>
🏁 До: <b>{format_msk_datetime(profile.end_at)}</b>

Открой <b>🎯 Задания → 🎪 События</b> и следи за прогрессом.
""".strip()


def validate_title(value: str) -> str | None:
    text = " ".join(value.strip().split())
    if 3 <= len(text) <= 80:
        return text
    return None


def validate_description(value: str) -> str | None:
    text = value.strip()
    if text == "-":
        return ""
    if len(text) <= 500:
        return text
    return None


def parse_positive_int(value: str) -> int | None:
    text = value.replace(" ", "").strip()
    if not text.isdigit():
        return None
    number = int(text)
    return number if number > 0 else None
