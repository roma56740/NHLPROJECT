from html import escape

from app.services.security import (
    SecurityCardsPage,
    SecurityLogsPage,
    SecuritySummary,
    SecurityUserProfile,
    SecurityUsersPage,
)


ADMIN_SECURITY_MAIN_TEXT = """
<b>🛡 Безопасность</b>

Здесь можно контролировать блокировки игроков, ограничения карточек для обменов и журнал действий.
""".strip()

ADMIN_SECURITY_SEARCH_TEXT = """
<b>🔎 Поиск игрока</b>

Введи никнейм, username, имя или ID игрока.
""".strip()

ADMIN_SECURITY_LOCK_REASON_TEXT = """
<b>🔒 Причина ограничения</b>

Напиши короткую причину, почему карточка временно закрывается для обменов.
""".strip()

ADMIN_SECURITY_CARD_LOCKED_TEXT = """
<b>🔒 Карточка закрыта для обменов</b>

Игрок не сможет выставить её на рынок, пока ограничение активно.
""".strip()

ADMIN_SECURITY_CARD_UNLOCKED_TEXT = """
<b>🔓 Ограничение снято</b>

Карточка снова доступна для обменов.
""".strip()


def build_admin_security_main_text(summary: SecuritySummary) -> str:
    return f"""
<b>🛡 Безопасность</b>

🚫 Заблокированные игроки: <b>{summary.banned_users_count}</b>
🔒 Карточки с Trade Lock: <b>{summary.locked_cards_count}</b>
🔁 Открытые обмены: <b>{summary.open_trades_count}</b>
📜 Записей в журнале: <b>{summary.logs_count}</b>

Выбери действие ниже.
""".strip()


def build_security_users_page_text(page: SecurityUsersPage) -> str:
    if not page.users:
        return "<b>👥 Игроки</b>\n\nИгроки не найдены."

    rows = []
    for user in page.users:
        status = "🚫" if user.is_banned else "✅"
        locked = f" • 🔒 {user.locked_cards_count}" if user.locked_cards_count else ""
        username = f"@{user.username}" if user.username else "без username"
        rows.append(f"{status} <b>{user.nickname}</b> · {username}\n🏆 {user.league}{locked}")

    search = f"\n🔎 Поиск: <b>{page.search}</b>" if page.search else ""
    body = "\n\n".join(rows)

    return f"""
<b>👥 Игроки лиги</b>{search}

{body}

Страница {page.page}/{page.pages_count}
""".strip()


def build_security_user_profile_text(profile: SecurityUserProfile) -> str:
    username = f"@{escape(profile.username, quote=False)}" if profile.username else "не указан"
    status = "🚫 заблокирован" if profile.is_banned else "✅ активен"
    return f"""
<b>🛡 Карточка безопасности</b>

👤 Игрок: <b>{escape(profile.nickname, quote=False)}</b>
🔗 Username: <b>{username}</b>
🆔 Telegram ID: <code>{profile.telegram_id}</code>
🏆 Лига: <b>{profile.league}</b>
⭐ Рейтинг: <b>{profile.rating_points}</b>
🏒 Матчи: <b>{profile.matches_played}</b>

🃏 Карточек: <b>{profile.cards_count}</b>
🔒 Закрыто для обменов: <b>{profile.locked_cards_count}</b>
🔁 Открытых обменов: <b>{profile.open_trades_count}</b>

Статус: <b>{status}</b>
""".strip()


def build_security_cards_page_text(page: SecurityCardsPage) -> str:
    if not page.cards:
        return "<b>🃏 Карточки игрока</b>\n\nУ игрока пока нет карточек."

    rows = []
    for card in page.cards:
        lock = "🔒" if card.trade_locked else "🔓"
        lineup = " • 🧩 в составе" if card.is_in_lineup else ""
        reason = f"\nПричина: <i>{card.lock_reason}</i>" if card.trade_locked and card.lock_reason else ""
        rows.append(
            f"{lock} <b>{card.name}</b> · {card.position} · {card.overall} OVR\n"
            f"{card.rarity} · {card.collection_name}{lineup}{reason}"
        )

    body = "\n\n".join(rows)
    return f"""
<b>🃏 Карточки игрока</b>

{body}

Страница {page.page}/{page.pages_count}
""".strip()


def build_security_logs_page_text(page: SecurityLogsPage) -> str:
    if not page.logs:
        return "<b>📜 Журнал безопасности</b>\n\nПока записей нет."

    rows = []
    for log in page.logs:
        user = f" · игрок #{log.user_id}" if log.user_id else ""
        rows.append(f"🛡 <b>{log.action}</b>{user}\n{log.details}\n<i>{log.created_at}</i>")

    body = "\n\n".join(rows)
    return f"""
<b>📜 Журнал безопасности</b>

{body}

Страница {page.page}/{page.pages_count}
""".strip()
