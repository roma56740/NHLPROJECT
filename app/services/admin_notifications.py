from html import escape


def _safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def _format_amount(value: int) -> str:
    return f"{value:,}".replace(",", " ")


async def send_admin_reward_notification(bot, telegram_id: int | None, text: str) -> bool:
    if telegram_id is None:
        return False

    try:
        await bot.send_message(chat_id=telegram_id, text=text)
        return True
    except Exception:
        return False


def build_card_reward_notification(card) -> str:
    return f"""
<b>🎁 Подарок от администрации!</b>

В коллекцию добавлена карточка:

🃏 <b>{_safe(card.name)}</b>
⭐ OVR: <b>{card.overall}</b>
🏒 Позиция: <b>{_safe(card.position)}</b>
💎 Редкость: <b>{_safe(card.rarity)}</b>
🏟 Команда: <b>{_safe(card.team)}</b>
🌍 Страна: <b>{_safe(card.country)}</b>
📚 Коллекция: <b>{_safe(card.collection_name)}</b>

Открой раздел «Карты», чтобы посмотреть новую карточку.
""".strip()


def build_pack_reward_notification(pack_name: str, quantity: int = 1) -> str:
    amount_line = f"Количество: <b>{quantity}</b>" if quantity > 1 else "Количество: <b>1</b>"

    return f"""
<b>🎁 Подарок от администрации!</b>

Получен пак:

🎁 <b>{_safe(pack_name)}</b>
{amount_line}

Открой раздел «Паки», чтобы открыть подарок.
""".strip()


def build_currency_reward_notification(currency_title: str, amount: int) -> str:
    if amount >= 0:
        title = "<b>🎁 Подарок от администрации!</b>"
        action_line = "На баланс начислено:"
        amount_value = amount
    else:
        title = "<b>💱 Баланс обновлён</b>"
        action_line = "С баланса списано:"
        amount_value = abs(amount)

    return f"""
{title}

{action_line}

💰 <b>{_safe(currency_title)}</b>
Сумма: <b>{_format_amount(amount_value)}</b>

Актуальный баланс можно посмотреть в профиле.
""".strip()


def build_premium_reward_notification(pass_title: str | None) -> str:
    season_line = f"\nСезон: <b>{_safe(pass_title)}</b>" if pass_title else ""

    return f"""
<b>👑 Premium Pass открыт!</b>

Администрация открыла Premium-доступ для Hockey Pass.{season_line}

Теперь можно забирать Premium-награды в разделе «Hockey Pass».
""".strip()
