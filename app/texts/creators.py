from html import escape

from app.services.creators import (
    CREATOR_LEVELS,
    CreatorApplication,
    CreatorPanel,
    CreatorLevelConfig,
    format_int,
    format_level_config_for_admin,
)

CREATOR_BUTTON_TEXT = "⭐ Программа креаторов"
ADMIN_CREATORS_BUTTON_TEXT = "⭐ Креаторы"


CREATOR_INTRO_TEXT = """
<b>⭐ Программа официальных креаторов</b>

Креаторы получают банк выдачи для розыгрышей. В банк можно добавить монеты, рубли, Rank-point, паки и карточки. После добавления вывести награду обратно нельзя.

Уровень не повышается автоматически — администрация выставляет его вручную. Система только считает подписчиков и сумму уже выданных наград.

<b>Требования уровней</b>
1 ур. — 30 подписчиков + 0 разыгранных монет
2 ур. — 100 подписчиков + 500 000 разыгранных монет
3 ур. — 200 подписчиков + 2 000 000 разыгранных монет
4 ур. — 300 подписчиков + 4 000 000 разыгранных монет
5 ур. — 400 подписчиков + 10 000 000 разыгранных монет

Минимум для заявки — 30 подписчиков.
""".strip()

CREATOR_APPLY_CHANNEL_TEXT = "<b>⭐ Заявка — шаг 1 из 3</b>\n\nОтправь ссылку на свой канал или чат."
CREATOR_APPLY_SUBS_TEXT = "<b>⭐ Заявка — шаг 2 из 3</b>\n\nСколько у тебя подписчиков/участников? (число)"
CREATOR_APPLY_DESC_TEXT = "<b>⭐ Заявка — шаг 3 из 3</b>\n\nКоротко опиши, где будешь продвигать проект."


def _safe(value: object | None) -> str:
    text = "" if value is None else str(value).strip()
    return escape(text or "—", quote=False)


def build_creator_panel_text(panel: CreatorPanel) -> str:
    channel = _safe(panel.channel)
    items = []
    for item in panel.bank_items[:20]:
        items.append(
            f"• {escape(item.title, quote=False)} ×<b>{format_int(item.quantity)}</b> "
            f"= <b>{format_int(item.total_value)}</b> монет"
        )
    items_text = "\n".join(items) if items else "банк пуст"

    requirements = ""
    if panel.level > 0:
        sub_ok = "✅" if panel.subscribers >= panel.required_subscribers else "❌"
        value_ok = "✅" if panel.distributed_value >= panel.required_distributed_value else "❌"
        requirements = (
            f"\n<b>Требования текущего уровня</b>\n"
            f"{sub_ok} Подписчики: <b>{format_int(panel.subscribers)}</b> / {format_int(panel.required_subscribers)}\n"
            f"{value_ok} Разыграно: <b>{format_int(panel.distributed_value)}</b> / {format_int(panel.required_distributed_value)} монет\n"
        )
    else:
        requirements = f"\n📊 Разыграно: <b>{format_int(panel.distributed_value)}</b> монет\n"

    perks = f"\n<b>Возможности уровня</b>\n{escape(panel.perks_text, quote=False)}\n" if panel.perks_text else ""
    personal = f"\n<b>Личные награды</b>\n{escape(panel.personal_rewards_text, quote=False)}\n" if panel.personal_rewards_text else ""

    return (
        f"<b>⭐ Панель креатора</b>\n\n"
        f"🎖 Уровень: <b>{panel.level_title}</b>\n"
        f"📢 Канал: {channel}\n"
        f"👥 Подписчики: <b>{format_int(panel.subscribers)}</b>\n"
        f"🎁 Всего разыграно: <b>{format_int(panel.distributed_value)}</b> монет\n"
        f"🏦 Банк сейчас: <b>{format_int(panel.bank_total_value)}</b> монет\n"
        f"{requirements}"
        f"\n<b>Банк выдачи</b>\n{items_text}\n"
        f"{perks}{personal}\n"
        f"Награда засчитывается в статистику только после выдачи игроку."
    )


def build_creator_history_text(history: list[dict]) -> str:
    if not history:
        return "<b>📜 История выдач</b>\n\nПока пусто."
    lines = ["<b>📜 История выдач</b>", ""]
    for h in history:
        value = int(h.get("value_coins") or 0)
        lines.append(
            f"→ <b>{escape(h['target_nickname'], quote=False)}</b>: "
            f"{escape(h['reward_desc'], quote=False)} "
            f"(<b>{format_int(value)}</b> монет)"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

ADMIN_CREATORS_MAIN_TEXT = """
<b>⭐ Креаторы — управление</b>

Здесь можно рассматривать заявки, вручную назначать уровни, менять подписчиков, редактировать бонусы уровней и начислять недельные награды.
""".strip()


def build_admin_application_text(app: CreatorApplication) -> str:
    level = 0
    for lvl in sorted(CREATOR_LEVELS):
        if app.subscribers >= CREATOR_LEVELS[lvl]["min_subs"]:
            level = lvl
    level_note = f"примерно {level} уровень по подписчикам" if level else "ниже минимума"
    return (
        f"<b>⭐ Заявка креатора</b>\n\n"
        f"👤 <b>{escape(app.nickname, quote=False)}</b> (ID {app.telegram_id})\n"
        f"📢 Канал: {escape(app.channel, quote=False)}\n"
        f"👥 Подписчиков: <b>{format_int(app.subscribers)}</b>\n"
        f"🎖 Подсказка: <b>{level_note}</b>\n\n"
        f"После одобрения игрок сразу станет креатором 1 уровня. Дальше уровень 2–5 выставляется вручную.\n\n"
        f"📝 {escape(app.description, quote=False) or '—'}"
    )


def build_admin_creators_list_text(creators: list[dict]) -> str:
    if not creators:
        return ADMIN_CREATORS_MAIN_TEXT + "\n\nКреаторов пока нет."
    lines = ["<b>⭐ Официальные креаторы</b>", ""]
    for c in creators:
        lines.append(
            f"👤 {escape(c['nickname'], quote=False)} · {c['creator_level']} ур. "
            f"· {format_int(int(c.get('creator_subscribers') or 0))} подп. "
            f"· разыграно {format_int(int(c.get('distributed_value') or 0))} монет "
            f"(ID {c['telegram_id']})"
        )
    return "\n".join(lines)


def build_admin_creator_detail_text(creator: dict) -> str:
    author = creator.get("creator_author_code") or "—"
    return (
        f"<b>⭐ {escape(creator['nickname'], quote=False)}</b>\n\n"
        f"🎖 Уровень: <b>{creator['creator_level']}</b>\n"
        f"ID: <b>{creator['telegram_id']}</b>\n"
        f"📢 Канал: {escape(creator.get('creator_channel') or '—', quote=False)}\n"
        f"👥 Подписчики: <b>{format_int(int(creator.get('creator_subscribers') or 0))}</b>\n"
        f"🎁 Разыграно: <b>{format_int(int(creator.get('distributed_value') or 0))}</b> монет\n"
        f"✍️ Код автора: <b>{escape(author, quote=False)}</b>"
    )


def build_admin_levels_text(configs: list[CreatorLevelConfig]) -> str:
    lines = ["<b>⚙️ Настройки уровней креаторов</b>", ""]
    for cfg in configs:
        lines.append(
            f"{cfg.level} ур. — {format_int(cfg.required_subscribers)} подп. + "
            f"{format_int(cfg.required_distributed_value)} разыграно; "
            f"вступ. {format_int(cfg.welcome_coins)}, неделя {format_int(cfg.weekly_coins)}"
        )
    lines.append("\nВсе значения можно менять через кнопки ниже.")
    return "\n".join(lines)


def build_admin_level_config_text(cfg: CreatorLevelConfig) -> str:
    return (
        f"<b>⚙️ Настройки {cfg.level} уровня</b>\n\n"
        f"{format_level_config_for_admin(cfg)}\n\n"
        f"<b>Формат для изменения цифр:</b>\n"
        f"<code>подписчики|разыграно|вступительные|недельные_монеты|elite_qty|legendary_qty|elite_pack_id|legendary_pack_id|промокоды|код_автора_bp|экскл_карта</code>\n\n"
        f"Процент кода автора указывается в basis points: 150 = 1.5%. Pack ID можно поставить 0, тогда бот сам найдёт подходящий активный пак."
    )
