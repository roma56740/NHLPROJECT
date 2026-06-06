from html import escape

from app.services.chemistry import ChemistryRule, ChemistryRulesPage, get_rule_type_title


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


ADMIN_CHEMISTRY_TEXT = """
<b>🧪 Химия состава</b>

Создавай бонусы для команд, стран и коллекций.
Игроки будут получать дополнительный OVR, если соберут нужные карточки в составе.

Примеры:
🌍 Canada · 3 карты · +2 OVR
🏒 Toronto Maple Leafs · 3 карты · +3 OVR
🗂 TOTS · 2 карты · +4 OVR
""".strip()

CHEMISTRY_CREATE_TYPE_TEXT = """
<b>➕ Новый бонус химии</b>

Выбери, по чему будет работать бонус.
""".strip()

CHEMISTRY_CREATE_VALUE_TEXT = """
<b>🧪 Значение бонуса</b>

Введи название страны, команды или коллекции.

Например:
🇨🇦 Canada
🏒 Toronto Maple Leafs
🗂 TOTS
""".strip()

CHEMISTRY_SEARCH_TEXT = """
<b>🔎 Поиск бонуса</b>

Введи страну, команду, коллекцию или тип бонуса.
""".strip()

CHEMISTRY_DELETE_CONFIRM_TEXT = """
<b>🗑 Удалить бонус?</b>

Он сразу перестанет влиять на составы и матчи.
""".strip()


def build_chemistry_rules_text(page: ChemistryRulesPage) -> str:
    if page.total_count == 0:
        return """
<b>🧪 Бонусы химии</b>

Пока нет ни одного бонуса.
Создай первое правило, чтобы составы игроков стали сильнее.
""".strip()

    lines: list[str] = []

    for rule in page.rules:
        status = "✅ активен" if rule.active else "🚫 выключен"
        lines.append(
            f"{status} · <b>{safe(rule.value)}</b>\n"
            f"{safe(get_rule_type_title(rule.rule_type))} · {rule.required_cards} карт · +{rule.bonus_ovr} OVR"
        )

    search_line = f"\n🔎 Поиск: <b>{safe(page.query)}</b>\n" if page.query else ""

    return f"""
<b>🧪 Бонусы химии</b>
{search_line}
Всего бонусов: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

{chr(10).join(lines)}
""".strip()


def build_chemistry_rule_profile_text(rule: ChemistryRule) -> str:
    status = "✅ Активен" if rule.active else "🚫 Выключен"

    return f"""
<b>🧪 Бонус химии</b>

{status}

🏷 Тип: <b>{safe(get_rule_type_title(rule.rule_type))}</b>
🎯 Значение: <b>{safe(rule.value)}</b>
📌 Нужно карт: <b>{rule.required_cards}</b>
⭐ Бонус: <b>+{rule.bonus_ovr} OVR</b>

Бонус применяется автоматически, если в составе игрока достаточно подходящих карточек.
""".strip()


def build_chemistry_create_confirm_text(data: dict) -> str:
    return f"""
<b>✅ Бонус создан</b>

🏷 Тип: <b>{safe(get_rule_type_title(str(data.get('rule_type'))))}</b>
🎯 Значение: <b>{safe(data.get('value'))}</b>
📌 Нужно карт: <b>{safe(data.get('required_cards'))}</b>
⭐ Бонус: <b>+{safe(data.get('bonus_ovr'))} OVR</b>
""".strip()
