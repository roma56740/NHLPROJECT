from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminSummary:
    users_count: int
    cards_count: int
    packs_count: int
    matches_count: int
    open_trades_count: int
    clans_count: int
    active_quests_count: int
    active_passes_count: int
    active_admins_count: int


@dataclass(frozen=True)
class AdminListItem:
    telegram_id: int
    source: str
    active: bool
    added_at: str | None = None


ADMIN_PANEL_TEXT = """
<b>📊 Админ-панель</b>

Главный центр управления лигой.

<b>📈 Сводка</b>
👥 Игроков: <b>{users_count}</b>
🃏 Карточек: <b>{cards_count}</b>
🎁 Паков: <b>{packs_count}</b>
🏒 Матчей: <b>{matches_count}</b>
🔁 Открытых обменов: <b>{open_trades_count}</b>
🤝 Кланов: <b>{clans_count}</b>
🎯 Активных заданий: <b>{active_quests_count}</b>
🎟 Активных пропусков: <b>{active_passes_count}</b>
👑 Админов: <b>{active_admins_count}</b>

Выбери действие ниже.
""".strip()


ADMINS_TEXT = """
<b>👑 Админы</b>

Здесь можно добавить нового администратора по Telegram ID или убрать доступ, выданный через панель.

<b>Текущие админы</b>
{admins}
""".strip()


ADMIN_DATA_TEXT = """
<b>📦 Данные проекта</b>

Здесь можно получить резервные файлы проекта:

🗄 файл базы данных
🖼 архив загруженных изображений

Эти файлы пригодятся, чтобы перенести данные в обновлённый проект.
""".strip()


ADMIN_ADD_PROMPT_TEXT = """
<b>➕ Добавить админа</b>

Отправь Telegram ID нового администратора одним сообщением.

После добавления бот попробует отправить ему уведомление.
""".strip()


ADMIN_REMOVE_PROMPT_TEXT = """
<b>➖ Убрать админа</b>

Отправь Telegram ID администратора, которому нужно закрыть доступ через панель.
""".strip()


ADMIN_INPUT_CANCELLED_TEXT = "❌ Действие отменено."
ADMIN_ID_ERROR_TEXT = "⚠️ Отправь только Telegram ID цифрами."
ADMIN_ADD_SUCCESS_TEXT = "✅ Админ добавлен. Доступ открыт."
ADMIN_ADD_NOTIFY_SUCCESS_TEXT = "📩 Уведомление отправлено новому админу."
ADMIN_ADD_NOTIFY_FAILED_TEXT = "📩 Админ добавлен, но уведомление не доставлено. Попроси его открыть бота и нажать /start."
ADMIN_REMOVE_SUCCESS_TEXT = "✅ Доступ закрыт."
ADMIN_REMOVE_MAIN_DENIED_TEXT = "👑 Этот админ закреплён как главный. Его нельзя убрать через панель."
ADMIN_REMOVE_NOT_FOUND_TEXT = "⚠️ Активный админ с таким ID не найден в панели."
ADMIN_DB_NOT_FOUND_TEXT = "⚠️ Файл базы пока не найден."
ADMIN_UPLOADS_NOT_FOUND_TEXT = "🖼 Загруженных изображений пока нет."
ADMIN_EXPORT_START_TEXT = "📦 Готовлю файлы..."


NEW_ADMIN_NOTIFICATION_TEXT = """
<b>👑 Доступ администратора открыт</b>

Теперь тебе доступна админ-панель NHL Card Bot.

Нажми /start, чтобы открыть меню управления.
""".strip()


def build_admin_panel_text(summary: AdminSummary) -> str:
    return ADMIN_PANEL_TEXT.format(
        users_count=summary.users_count,
        cards_count=summary.cards_count,
        packs_count=summary.packs_count,
        matches_count=summary.matches_count,
        open_trades_count=summary.open_trades_count,
        clans_count=summary.clans_count,
        active_quests_count=summary.active_quests_count,
        active_passes_count=summary.active_passes_count,
        active_admins_count=summary.active_admins_count,
    )


def build_admins_text(admins: list[AdminListItem]) -> str:
    if not admins:
        admins_text = "Пока список пуст."
    else:
        lines: list[str] = []
        for admin in admins:
            marker = "👑" if admin.source == "main" else "⭐"
            status = "активен" if admin.active else "закрыт"
            source = "главный доступ" if admin.source == "main" else "добавлен через панель"
            lines.append(f"{marker} <code>{admin.telegram_id}</code> — {source}, {status}")
        admins_text = "\n".join(lines)

    return ADMINS_TEXT.format(admins=admins_text)
