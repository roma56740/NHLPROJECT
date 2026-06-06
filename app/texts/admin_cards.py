from html import escape
from pathlib import Path

from app.services.admin_cards import CardDraft, CardProfile, CardsPage, CollectionItem


ADMIN_CARDS_MAIN_TEXT = """
<b>🃏 Карточки</b>

Здесь можно добавить новую карточку, найти игрока, открыть список, изменить данные и управлять коллекциями.
""".strip()

ADMIN_CARDS_IMAGE_TEXT = """
<b>➕ Новая карточка</b>

Отправь изображение карточки.

Лучше отправлять картинку как фото или файл в формате PNG/JPG.
""".strip()

ADMIN_CARDS_NAME_TEXT = """
<b>🏒 Имя игрока</b>

Отправь имя игрока.

Пример: <b>Connor McDavid</b>
""".strip()

ADMIN_CARDS_POSITION_TEXT = """
<b>🥅 Позиция</b>

Выбери позицию игрока.
""".strip()

ADMIN_CARDS_OVERALL_TEXT = """
<b>⭐ Рейтинг карточки</b>

Отправь OVR от <b>1</b> до <b>99</b>.

Пример: <b>95</b>
""".strip()

ADMIN_CARDS_TEAM_TEXT = """
<b>🛡 Команда</b>

Отправь название команды.

Пример: <b>Edmonton Oilers</b>
""".strip()

ADMIN_CARDS_COUNTRY_TEXT = """
<b>🌍 Страна</b>

Отправь страну игрока.

Пример: <b>Canada</b>
""".strip()

ADMIN_CARDS_COLLECTION_TEXT = """
<b>🗂 Коллекция</b>

Отправь название коллекции.

Примеры: <b>Base Collection</b>, <b>Prospects 2026</b>, <b>TOTS</b>.

Если коллекции ещё нет, она появится автоматически.
""".strip()

ADMIN_CARDS_RARITY_TEXT = """
<b>💎 Редкость</b>

Выбери редкость карточки.
""".strip()

ADMIN_CARDS_SEARCH_TEXT = """
<b>🔎 Поиск карточки</b>

Отправь имя игрока, команду, страну, коллекцию, редкость, позицию или ID карточки.
""".strip()

ADMIN_CARDS_EMPTY_TEXT = """
<b>🃏 Карточки не найдены</b>

Попробуй изменить запрос или открыть полный список карточек.
""".strip()

ADMIN_CARDS_SAVED_TEXT = """
<b>✅ Карточка сохранена</b>

Карточка добавлена в игру и готова для будущих паков, магазина, состава и коллекции игрока.
""".strip()

ADMIN_CARDS_CANCEL_TEXT = """
<b>❌ Действие отменено</b>

Можно выбрать другой раздел ниже.
""".strip()

ADMIN_CARDS_BAD_IMAGE_TEXT = """
<b>🖼 Нужна картинка</b>

Отправь изображение карточки как фото или файл PNG/JPG.
""".strip()

ADMIN_CARDS_BAD_NAME_TEXT = """
<b>🏒 Имя не подходит</b>

Имя должно быть от 2 до 64 символов.
""".strip()

ADMIN_CARDS_BAD_TEXT_TEXT = """
<b>✍️ Значение не подходит</b>

Текст должен быть от 2 до 64 символов.
""".strip()

ADMIN_CARDS_BAD_OVERALL_TEXT = """
<b>⭐ OVR не подходит</b>

Отправь число от 1 до 99.
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def active_text(value: bool) -> str:
    return "✅ в игре" if value else "⏸ отключена"


def image_file_name(path: str) -> str:
    return Path(path).name


def build_cards_page_text(page: CardsPage) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return ADMIN_CARDS_EMPTY_TEXT

    return f"""
<b>🃏 Карточки</b>

Всего карточек: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери карточку из списка ниже.
""".strip()


def build_card_profile_text(card: CardProfile) -> str:
    return f"""
<b>🃏 Карточка игрока</b>

🏒 Имя: <b>{safe(card.name)}</b>
🥅 Позиция: <b>{safe(card.position)}</b>
⭐ OVR: <b>{card.overall}</b>
🛡 Команда: <b>{safe(card.team)}</b>
🌍 Страна: <b>{safe(card.country)}</b>
🗂 Коллекция: <b>{safe(card.collection_name)}</b>
💎 Редкость: <b>{safe(card.rarity)}</b>
👁 Статус: <b>{active_text(card.active)}</b>

🖼 Фото: <b>{safe(image_file_name(card.image_path))}</b>
🆔 ID карточки: <b>{card.id}</b>
""".strip()


def build_card_draft_text(draft: CardDraft) -> str:
    return f"""
<b>✅ Проверь карточку</b>

🏒 Имя: <b>{safe(draft.name)}</b>
🥅 Позиция: <b>{safe(draft.position)}</b>
⭐ OVR: <b>{draft.overall}</b>
🛡 Команда: <b>{safe(draft.team)}</b>
🌍 Страна: <b>{safe(draft.country)}</b>
🗂 Коллекция: <b>{safe(draft.collection_name)}</b>
💎 Редкость: <b>{safe(draft.rarity)}</b>

После сохранения карточка появится в базе игры.
""".strip()


def build_card_edit_text(card: CardProfile) -> str:
    return f"""
<b>✏️ Редактирование карточки</b>

🏒 Игрок: <b>{safe(card.name)}</b>
⭐ OVR: <b>{card.overall}</b>
🗂 Коллекция: <b>{safe(card.collection_name)}</b>

Выбери, что нужно изменить.
""".strip()


def build_edit_value_text(field_title: str) -> str:
    return f"""
<b>{field_title}</b>

Отправь новое значение одним сообщением.
""".strip()


def build_edit_image_text(card: CardProfile) -> str:
    return f"""
<b>🖼 Новое фото</b>

Игрок: <b>{safe(card.name)}</b>

Отправь новое изображение карточки.
""".strip()


def build_collections_text(collections: list[CollectionItem]) -> str:
    if not collections:
        return "<b>🗂 Коллекции</b>\n\nКоллекций пока нет."

    lines = ["<b>🗂 Коллекции</b>", ""]

    for collection in collections:
        status = "✅" if collection.active else "⏸"
        lines.append(
            f"{status} <b>{safe(collection.name)}</b> — {collection.cards_count} карт"
        )

    lines.append("")
    lines.append("Новые коллекции появляются автоматически при добавлении карточки.")
    return "\n".join(lines)


def get_edit_field_title(field: str) -> str:
    titles = {
        "name": "🏒 Новое имя игрока",
        "overall": "⭐ Новый OVR",
        "team": "🛡 Новая команда",
        "country": "🌍 Новая страна",
        "collection": "🗂 Новая коллекция",
    }

    return titles.get(field, "✍️ Новое значение")
