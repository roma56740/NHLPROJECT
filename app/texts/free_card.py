from html import escape

FREE_CARD_BUTTON_TEXT = "🎁 Бесплатная карточка"

FREE_CARD_NOTIFICATION_TEXT = """
<b>🎁 Бесплатная карточка готова!</b>

На льду появился новый шанс усилить коллекцию.
Нажми кнопку ниже и забери 1 случайную карточку.
""".strip()

FREE_CARD_SET_COLLECTION_TEXT = """
<b>🗂 Заменить список коллекций</b>

Отправь название, код или ID коллекции.
Текущий список будет заменён одной выбранной коллекцией.
""".strip()

FREE_CARD_ADD_COLLECTION_TEXT = """
<b>➕ Добавить коллекцию бесплатных карточек</b>

Отправь название, код или ID коллекции.
Она добавится в общий пул бесплатных карточек.
""".strip()

FREE_CARD_REMOVE_COLLECTION_TEXT = """
<b>➖ Убрать коллекцию из бесплатных карточек</b>

Отправь название, код или ID коллекции.
Она удалится только из пула бесплатных карточек, сама коллекция и карты не удаляются.
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
    collections = list(getattr(status, "collections", []) or ([status.collection] if status.collection else []))
    active_cards = sum(c.active_cards_count for c in collections if c and c.active)
    collections_text = ", ".join(safe(c.name) for c in collections[:5])
    if len(collections) > 5:
        collections_text += f" и ещё {len(collections) - 5}"

    if not collections:
        return """
<b>🎁 Бесплатная карточка</b>

Сейчас бесплатная карточка недоступна.
Администрация лиги скоро выберет коллекции для подарков.
""".strip()

    if active_cards <= 0:
        return f"""
<b>🎁 Бесплатная карточка</b>

В выбранных коллекциях пока нет активных карточек.
Коллекции: <b>{collections_text}</b>

Как только в них появятся карточки, подарок станет доступен.
""".strip()

    if status.is_ready:
        return f"""
<b>🎁 Бесплатная карточка готова!</b>

Можно забрать 1 случайную карточку из пула коллекций:
<b>{collections_text}</b>

🃏 Активных карточек в пуле: <b>{active_cards}</b>

⏳ Новая карточка доступна раз в <b>{status.cooldown_hours} ч.</b>
""".strip()

    return f"""
<b>🎁 Бесплатная карточка</b>

Пул подарков:
<b>{collections_text}</b>

🃏 Активных карточек в пуле: <b>{active_cards}</b>

Следующая карточка будет доступна через:
<b>{format_remaining(status.remaining_seconds)}</b>
""".strip()


def build_free_card_admin_text(status) -> str:
    collections = list(getattr(status, "collections", []) or ([status.collection] if status.collection else []))
    if not collections:
        collections_block = "не выбраны"
        total_cards = 0
        status_line = "нужно добавить хотя бы одну коллекцию"
    else:
        lines = []
        total_cards = 0
        active_available = False
        for collection in collections:
            marker = "🟢" if collection.active else "🔴"
            total_cards += collection.active_cards_count if collection.active else 0
            if collection.active and collection.active_cards_count > 0:
                active_available = True
            lines.append(f"{marker} <b>{safe(collection.name)}</b> <code>{safe(collection.code)}</code> — {collection.active_cards_count} активных карт")
        collections_block = "\n".join(lines)
        status_line = "подарки доступны игрокам" if active_available else "нет активных карточек в выбранных коллекциях"

    return f"""
<b>🎁 Бесплатная карточка</b>

Теперь можно подключить сразу несколько коллекций. Игрок получает 1 случайную карточку из общего пула раз в <b>{status.cooldown_hours} ч.</b>

<b>Выбранные коллекции</b>
{collections_block}

🃏 Активных карточек в пуле: <b>{total_cards}</b>
📌 Статус: <b>{status_line}</b>

Игроки видят отдельную кнопку и могут сами проверить таймер.
Когда карточка готова, бот отправляет уведомление с кнопкой получения.
""".strip()


def build_free_card_collection_saved_text(collection) -> str:
    return f"""
<b>✅ Список заменён</b>

Теперь бесплатные карточки будут выпадать из коллекции:
<b>{safe(collection.name)}</b>

Активных карточек внутри: <b>{collection.active_cards_count}</b>
""".strip()


def build_free_card_collection_added_text(collection) -> str:
    return f"""
<b>✅ Коллекция добавлена</b>

В пул бесплатных карточек добавлена коллекция:
<b>{safe(collection.name)}</b>

Активных карточек внутри: <b>{collection.active_cards_count}</b>
""".strip()


def build_free_card_collection_removed_text(collection) -> str:
    return f"""
<b>✅ Коллекция убрана</b>

Из пула бесплатных карточек убрана коллекция:
<b>{safe(collection.name)}</b>

Сама коллекция и карточки не удалялись.
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

Следующая бесплатная карточка будет доступна по таймеру бесплатной карточки.
""".strip()
