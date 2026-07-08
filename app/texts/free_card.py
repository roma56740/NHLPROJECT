from html import escape

FREE_CARD_BUTTON_TEXT = "🎁 Бесплатная карточка"

FREE_CARD_NOTIFICATION_TEXT = """
<b>🎁 Бесплатная карточка готова!</b>

На льду появился новый шанс усилить коллекцию.
Нажми кнопку ниже и забери 1 случайную карточку.
""".strip()

FREE_CARD_SET_COLLECTION_TEXT = """
<b>🗂 Коллекция бесплатной карточки</b>

Отправь название, код или ID коллекции.
Именно из неё игроки будут получать случайную карточку раз в 6 часов.
""".strip()

FREE_CARD_COLLECTION_NOT_FOUND_TEXT = """
<b>Коллекция не найдена</b>

Проверь название, код или ID коллекции и попробуй ещё раз.
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()
    if not text:
        return "не указано"

    return escape(text, quote=False)


def format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "0 минут"

    hours = seconds // 3600
    minutes = (seconds % 3600 + 59) // 60

    if minutes == 60:
        hours += 1
        minutes = 0

    parts: list[str] = []

    if hours:
        parts.append(f"{hours} ч.")

    if minutes:
        parts.append(f"{minutes} мин.")

    return " ".join(parts) if parts else "меньше минуты"


def build_free_card_user_text(status) -> str:
    if status.collection is None:
        return """
<b>🎁 Бесплатная карточка</b>

Сейчас бесплатная карточка недоступна.
Администрация лиги скоро выберет коллекцию для подарков.
""".strip()

    if not status.collection.active:
        return f"""
<b>🎁 Бесплатная карточка</b>

Коллекция <b>{safe(status.collection.name)}</b> сейчас закрыта.
Как только подарки снова появятся, здесь можно будет забрать карточку.
""".strip()

    if status.collection.active_cards_count <= 0:
        return f"""
<b>🎁 Бесплатная карточка</b>

Коллекция <b>{safe(status.collection.name)}</b> пока пустая.
Как только в ней появятся карточки, подарок станет доступен.
""".strip()

    if status.is_ready:
        return f"""
<b>🎁 Бесплатная карточка готова!</b>

Можно забрать 1 случайную карточку из коллекции:
<b>{safe(status.collection.name)}</b>

⏳ Новая карточка доступна раз в <b>{status.cooldown_hours} ч.</b>
""".strip()

    return f"""
<b>🎁 Бесплатная карточка</b>

Коллекция подарков:
<b>{safe(status.collection.name)}</b>

Следующая карточка будет доступна через:
<b>{format_remaining(status.remaining_seconds)}</b>
""".strip()


def build_free_card_admin_text(status) -> str:
    collection_line = "не выбрана"
    cards_line = "0"
    status_line = "нужно выбрать коллекцию"

    if status.collection is not None:
        collection_line = f"{safe(status.collection.name)} <code>{safe(status.collection.code)}</code>"
        cards_line = str(status.collection.active_cards_count)

        if not status.collection.active:
            status_line = "коллекция закрыта"
        elif status.collection.active_cards_count <= 0:
            status_line = "в коллекции пока нет активных карточек"
        else:
            status_line = "подарки доступны игрокам"

    return f"""
<b>🎁 Бесплатная карточка</b>

Здесь выбирается коллекция, из которой игроки получают случайную карточку раз в <b>{status.cooldown_hours} ч.</b>

🗂 Коллекция: <b>{collection_line}</b>
🃏 Активных карточек: <b>{cards_line}</b>
📌 Статус: <b>{status_line}</b>

Игроки видят отдельную кнопку и могут сами проверить таймер.
Когда карточка готова, бот отправляет уведомление с кнопкой получения.
""".strip()


def build_free_card_collection_saved_text(collection) -> str:
    return f"""
<b>✅ Коллекция выбрана</b>

Теперь бесплатные карточки будут выпадать из коллекции:
<b>{safe(collection.name)}</b>

Активных карточек внутри: <b>{collection.active_cards_count}</b>
""".strip()


def build_free_card_reward_text(reward) -> str:
    return f"""
<b>🎉 Бесплатная карточка получена!</b>

🏒 Игрок: <b>{safe(reward.name)}</b>
⭐ OVR: <b>{reward.overall}</b>
📍 Позиция: <b>{safe(reward.position)}</b>
🛡 Команда: <b>{safe(reward.team)}</b>
🌍 Страна: <b>{safe(reward.country)}</b>
🗂 Коллекция: <b>{safe(reward.collection_name)}</b>
✨ Редкость: <b>{safe(reward.rarity)}</b>

Следующая бесплатная карточка будет доступна через <b>6 часов</b>.
""".strip()
