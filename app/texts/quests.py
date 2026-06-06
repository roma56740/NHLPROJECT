from html import escape

from app.services.quests import (
    AdminQuestPage,
    AdminQuestProfile,
    QuestDraft,
    QuestList,
    QuestMainInfo,
    QuestProgressItem,
    QuestRewardResult,
    PERIOD_TYPE_TITLES,
    TARGET_TYPE_TITLES,
)


PERIOD_TITLES = {
    "daily": "📅 Ежедневные задания",
    "seasonal": "🏆 Сезонные задания",
}

ADMIN_QUESTS_MAIN_TEXT = """
<b>🎯 Задания</b>

Здесь можно создавать цели для игроков, выбирать срок выполнения и назначать награды.

Игроки будут видеть только активные задания.
""".strip()

ADMIN_QUESTS_SEARCH_TEXT = """
<b>🔎 Поиск задания</b>

Отправь название, описание, тип цели или часть кода задания.
""".strip()

ADMIN_QUEST_TITLE_TEXT = """
<b>✏️ Название задания</b>

Отправь короткое название.

Пример: <b>Выиграть 5 матчей</b>
""".strip()

ADMIN_QUEST_DESCRIPTION_TEXT = """
<b>📝 Описание задания</b>

Отправь красивое описание для игроков.

Можно отправить <b>-</b>, если описание не нужно.
""".strip()

ADMIN_QUEST_TARGET_VALUE_TEXT = """
<b>🔢 Количество</b>

Отправь число, до которого игрок должен дойти.

Пример: <b>15</b>
""".strip()

ADMIN_QUEST_BP_REWARD_TEXT = """
<b>🎟 Награда BP Points</b>

Отправь количество BP Points.

Если награда не нужна, отправь <b>0</b>.
""".strip()

ADMIN_QUEST_COINS_REWARD_TEXT = """
<b>🪙 Награда Coins</b>

Отправь количество Coins.

Если награда не нужна, отправь <b>0</b>.
""".strip()

ADMIN_QUEST_BAD_TITLE_TEXT = "Название должно быть от 3 до 80 символов."
ADMIN_QUEST_BAD_DESCRIPTION_TEXT = "Описание должно быть до 300 символов."
ADMIN_QUEST_BAD_NUMBER_TEXT = "Отправь целое число."
ADMIN_QUEST_SAVED_TEXT = "✅ Задание создано."
ADMIN_QUEST_UPDATED_TEXT = "✅ Задание обновлено."
ADMIN_QUEST_DELETED_TEXT = "🗑 Задание удалено."
ADMIN_QUEST_NOT_FOUND_TEXT = "Задание уже недоступно."


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def build_progress_bar(progress: int, target: int, size: int = 10) -> str:
    if target <= 0:
        return "▫️" * size

    filled = min(size, max(0, round(progress / target * size)))
    empty = size - filled
    return "🟦" * filled + "▫️" * empty


def build_quests_main_text(info: QuestMainInfo) -> str:
    daily_line = f"{info.daily_completed}/{info.daily_total}"
    seasonal_line = f"{info.seasonal_completed}/{info.seasonal_total}"

    return (
        "<b>🎯 Задания</b>\n\n"
        "Выполняй цели на льду, забирай награды и прокачивай Hockey Pass.\n\n"
        f"📅 Ежедневные: <b>{daily_line}</b>\n"
        f"🏆 Сезонные: <b>{seasonal_line}</b>\n"
        f"🎟 BP Points: <b>{info.bp_points}</b>\n"
        f"⭐ Уровень Pass: <b>{info.hockey_pass_level}</b>\n\n"
        "Выбери раздел заданий ниже."
    )


def build_quest_list_text(quest_list: QuestList) -> str:
    title = PERIOD_TITLES.get(quest_list.period_type, "🎯 Задания")

    if not quest_list.items:
        return (
            f"<b>{title}</b>\n\n"
            "Сейчас здесь нет активных целей. Скоро появятся новые испытания."
        )

    lines = [f"<b>{title}</b>", ""]

    for index, item in enumerate(quest_list.items, start=1):
        lines.append(format_quest_item(index, item))
        lines.append("")

    lines.append("Забери награду, когда шкала заполнится полностью.")
    return "\n".join(lines).strip()


def format_quest_item(index: int, item: QuestProgressItem) -> str:
    progress = min(item.progress, item.target_value)
    status = "✅ Получено" if item.reward_claimed else "🎁 Готово" if item.completed else "🏒 В процессе"
    rewards = []

    if item.bp_reward > 0:
        rewards.append(f"{item.bp_reward} BP Points")

    if item.coins_reward > 0:
        rewards.append(f"{format_number(item.coins_reward)} Coins")

    reward_text = " + ".join(rewards) if rewards else "Награда скоро появится"

    return (
        f"<b>{index}. {safe(item.title)}</b>\n"
        f"{safe(item.description)}\n"
        f"{build_progress_bar(progress, item.target_value)} <b>{progress}/{item.target_value}</b>\n"
        f"🎁 Награда: <b>{reward_text}</b>\n"
        f"{status}"
    )


def build_claim_result_text(result: QuestRewardResult) -> str:
    rewards = []

    if result.bp_reward > 0:
        rewards.append(f"🎟 +{result.bp_reward} BP Points")

    if result.coins_reward > 0:
        rewards.append(f"🪙 +{format_number(result.coins_reward)} Coins")

    reward_text = "\n".join(rewards) if rewards else "Награда получена"

    return (
        "🎁 Награда получена!\n\n"
        f"{reward_text}\n\n"
        "Продолжай играть и забирай новые призы."
    )


def build_admin_quests_page_text(page: AdminQuestPage) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return (
            "<b>🎯 Задания</b>\n\n"
            "Список пока пуст. Создай первое задание для игроков."
        )

    return f"""
<b>🎯 Задания</b>

Всего заданий: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери задание из списка ниже.
""".strip()


def build_admin_quest_profile_text(profile: AdminQuestProfile) -> str:
    status = "✅ активно" if profile.active else "⏸ отключено"
    period = PERIOD_TYPE_TITLES.get(profile.period_type, profile.period_type)
    target = TARGET_TYPE_TITLES.get(profile.target_type, profile.target_type)
    rewards = []

    if profile.bp_reward > 0:
        rewards.append(f"🎟 {profile.bp_reward} BP Points")

    if profile.coins_reward > 0:
        rewards.append(f"🪙 {format_number(profile.coins_reward)} Coins")

    reward_text = "\n".join(rewards) if rewards else "без награды"

    return f"""
<b>🎯 Карточка задания</b>

🏒 Название: <b>{safe(profile.title)}</b>
📝 Описание: <b>{safe(profile.description)}</b>

<b>⚙️ Условия</b>
Период: <b>{safe(period)}</b>
Цель: <b>{safe(target)}</b>
Количество: <b>{profile.target_value}</b>

<b>🎁 Награда</b>
{reward_text}

<b>📊 Прогресс игроков</b>
Начали: <b>{profile.progress_count}</b>
Выполнили: <b>{profile.completed_count}</b>
Забрали награду: <b>{profile.claimed_count}</b>

<b>🔐 Статус</b>
{status}
""".strip()


def build_admin_quest_draft_text(draft: QuestDraft) -> str:
    period = PERIOD_TYPE_TITLES.get(draft.period_type, draft.period_type)
    target = TARGET_TYPE_TITLES.get(draft.target_type, draft.target_type)
    rewards = []

    if draft.bp_reward > 0:
        rewards.append(f"🎟 {draft.bp_reward} BP Points")

    if draft.coins_reward > 0:
        rewards.append(f"🪙 {format_number(draft.coins_reward)} Coins")

    reward_text = "\n".join(rewards) if rewards else "без награды"

    return f"""
<b>✅ Проверь задание</b>

🏒 Название: <b>{safe(draft.title)}</b>
📝 Описание: <b>{safe(draft.description)}</b>

<b>⚙️ Условия</b>
Период: <b>{safe(period)}</b>
Цель: <b>{safe(target)}</b>
Количество: <b>{draft.target_value}</b>

<b>🎁 Награда</b>
{reward_text}

Если всё верно, создай задание.
""".strip()


def build_admin_edit_value_text(field: str) -> str:
    titles = {
        "title": ADMIN_QUEST_TITLE_TEXT,
        "description": ADMIN_QUEST_DESCRIPTION_TEXT,
        "target_value": ADMIN_QUEST_TARGET_VALUE_TEXT,
        "bp_reward": ADMIN_QUEST_BP_REWARD_TEXT,
        "coins_reward": ADMIN_QUEST_COINS_REWARD_TEXT,
    }

    return titles.get(field, "Отправь новое значение.")


def build_admin_delete_text(profile: AdminQuestProfile) -> str:
    return f"""
<b>🗑 Удалить задание?</b>

Задание: <b>{safe(profile.title)}</b>

Игроки больше не увидят цель, а сохранённый прогресс по ней исчезнет.
""".strip()
