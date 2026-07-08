from html import escape

from app.services.creators import CreatorApplication, CreatorPanel, CREATOR_LEVELS

CREATOR_BUTTON_TEXT = "⭐ Программа креаторов"
ADMIN_CREATORS_BUTTON_TEXT = "⭐ Креаторы"


CREATOR_INTRO_TEXT = """
<b>⭐ Программа официальных креаторов</b>

Продвигай проект и получай еженедельные награды, которые можно раздавать своим подписчикам.

Уровни по количеству подписчиков:
🔹 1 ур. (30–99): 100 000 Coins + 1 Elite Pack
🔹 2 ур. (100–199): 300 000 Coins + 1 Elite Pack
🔹 3 ур. (200–299): 350 000 Coins + 1 Legendary Pack
🔹 4 ур. (300–499): 400 000 Coins + 3 Legendary Pack
🔹 5 ур. (500+): 500 000 Coins + 5 Legendary Pack

Минимум для участия — 30 подписчиков.
""".strip()

CREATOR_APPLY_CHANNEL_TEXT = "<b>⭐ Заявка — шаг 1 из 3</b>\n\nОтправь ссылку на свой канал или чат."
CREATOR_APPLY_SUBS_TEXT = "<b>⭐ Заявка — шаг 2 из 3</b>\n\nСколько у тебя подписчиков/участников? (число)"
CREATOR_APPLY_DESC_TEXT = "<b>⭐ Заявка — шаг 3 из 3</b>\n\nКоротко опиши, где будешь продвигать проект."


def build_creator_panel_text(panel: CreatorPanel) -> str:
    packs = "\n".join(f"🎁 {escape(name, quote=False)} ×{qty}" for _, name, qty in panel.packs) or "нет паков"
    channel = escape(panel.channel, quote=False) if panel.channel else "не указан"
    return (
        f"<b>⭐ Панель креатора</b>\n\n"
        f"🎖 Уровень: <b>{panel.level_title}</b>\n"
        f"📢 Канал: {channel}\n\n"
        f"<b>Доступно для выдачи</b>\n"
        f"🪙 Coins: <b>{panel.coins_available:,}</b>\n".replace(",", " ") +
        f"{packs}\n\n"
        f"Выдавай награды подписчикам по их ID."
    )


def build_creator_history_text(history: list[dict]) -> str:
    if not history:
        return "<b>📜 История выдач</b>\n\nПока пусто."
    lines = ["<b>📜 История выдач</b>", ""]
    for h in history:
        lines.append(f"→ <b>{escape(h['target_nickname'], quote=False)}</b>: {escape(h['reward_desc'], quote=False)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

ADMIN_CREATORS_MAIN_TEXT = """
<b>⭐ Креаторы — управление</b>

Рассматривай заявки, управляй уровнями и начисляй недельные награды.
""".strip()


def build_admin_application_text(app: CreatorApplication) -> str:
    from app.services.creators import level_for_subscribers
    level = level_for_subscribers(app.subscribers)
    level_note = CREATOR_LEVELS.get(level, {}).get("title", "ниже минимума") if level else "ниже минимума (30)"
    return (
        f"<b>⭐ Заявка креатора</b>\n\n"
        f"👤 <b>{escape(app.nickname, quote=False)}</b> (ID {app.telegram_id})\n"
        f"📢 Канал: {escape(app.channel, quote=False)}\n"
        f"👥 Подписчиков: <b>{app.subscribers}</b>\n"
        f"🎖 Уровень при одобрении: <b>{level_note}</b>\n\n"
        f"📝 {escape(app.description, quote=False) or '—'}"
    )


def build_admin_creators_list_text(creators: list[dict]) -> str:
    if not creators:
        return ADMIN_CREATORS_MAIN_TEXT + "\n\nКреаторов пока нет."
    lines = ["<b>⭐ Официальные креаторы</b>", ""]
    for c in creators:
        lines.append(f"👤 {escape(c['nickname'], quote=False)} · {c['creator_level']} ур. (ID {c['telegram_id']})")
    return "\n".join(lines)
