from html import escape

from app.services.packs import (
    AdminPackDetails,
    AdminPacksPage,
    PackChoicePage,
    PackDraft,
    PackCardsPage,
    PackHistoryPage,
    PackInfo,
    PackInventoryPage,
    PackOpeningResult,
)


USER_PACKS_MAIN_TEXT = """
<b>🎁 Паки</b>

Здесь хранятся все паки игрока. Открывай паки, забирай карточки и пополняй коллекцию.
""".strip()

ADMIN_PACKS_MAIN_TEXT = """
<b>🎁 Паки</b>

Создавай паки, добавляй обложки, настраивай цену, количество карточек и шансы редкостей.

Игроки будут открывать паки и получать карточки по заданным правилам.
""".strip()

ADMIN_PACK_IMAGE_TEXT = """
<b>➕ Новый пак</b>

Отправь обложку пака.

Лучше использовать PNG/JPG с красивым изображением набора карточек.
""".strip()

ADMIN_PACK_NAME_TEXT = """
<b>🎁 Название пака</b>

Отправь название пака.

Например: Elite Pack, Summer Pack, Winners Pack.
""".strip()

ADMIN_PACK_DESCRIPTION_TEXT = """
<b>📝 Описание пака</b>

Коротко напиши, что игрок может получить внутри.
""".strip()

ADMIN_PACK_CURRENCY_TEXT = """
<b>💰 Валюта пака</b>

Выбери валюту покупки.
""".strip()

ADMIN_PACK_PRICE_TEXT = """
<b>💰 Цена пака</b>

Отправь цену числом.
""".strip()

ADMIN_PACK_COUNT_TEXT = """
<b>🃏 Карточки внутри</b>

Отправь количество карточек, которые выпадут при открытии одного пака.

Можно указать число от 1 до 20.
""".strip()

ADMIN_PACK_SHOP_TEXT = """
<b>🛒 Доступность пака</b>

Выбери, где будет доступен пак.
""".strip()

ADMIN_PACK_BAD_IMAGE_TEXT = """
<b>🖼 Нужна обложка</b>

Отправь картинку пака как фото или файл PNG/JPG.
""".strip()

ADMIN_PACK_BAD_NAME_TEXT = """
<b>🎁 Название не подошло</b>

Название должно быть от 2 до 50 символов.
""".strip()

ADMIN_PACK_BAD_DESCRIPTION_TEXT = """
<b>📝 Описание не подошло</b>

Описание должно быть от 2 до 300 символов.
""".strip()

ADMIN_PACK_BAD_PRICE_TEXT = """
<b>💰 Цена не подошла</b>

Отправь целое число от 0 до 999999999.
""".strip()

ADMIN_PACK_BAD_COUNT_TEXT = """
<b>🃏 Количество не подошло</b>

Отправь число от 1 до 20.
""".strip()

ADMIN_PACK_ODDS_TEXT = """
<b>🎲 Шансы редкостей</b>

Отправь шансы в процентах. Сумма должна быть 100%.

Пример:
<code>Common 70
Rare 20
Epic 8
Legendary 2</code>

Можно использовать Common, Rare, Epic, Legendary, Event, Icon.
""".strip()

ADMIN_PACK_SEARCH_TEXT = """
<b>🔎 Поиск пака</b>

Отправь название, код или описание пака.
""".strip()

ADMIN_GIVE_PACK_SEARCH_TEXT = """
<b>🔎 Поиск пака</b>

Отправь название пака или короткий код.
""".strip()

ADMIN_PACK_CANCEL_TEXT = """
<b>🎁 Действие отменено</b>

Раздел паков открыт снова.
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def build_pack_price_text(pack: PackInfo | AdminPackDetails) -> str:
    if pack.price_amount <= 0 or pack.price_currency_code is None:
        return "бесплатно"

    titles = {
        "coins": "Coins",
        "energy": "Energy",
        "rank_point": "Rank-point",
    }

    currency_title = titles.get(pack.price_currency_code, pack.price_currency_code)
    return f"{pack.price_amount:,} {currency_title}".replace(",", " ")


def build_rarity_chances_text(chances: dict[str, int]) -> str:
    if not chances:
        return "Шансы не заданы"

    icons = {
        "Common": "⚪",
        "Rare": "🔵",
        "Epic": "🟣",
        "Legendary": "🟠",
        "Event": "🔴",
        "Icon": "✨",
    }

    lines = []

    for rarity, chance in chances.items():
        lines.append(f"{icons.get(rarity, '•')} {safe(rarity)} — <b>{chance}%</b>")

    return "\n".join(lines)


def build_user_pack_inventory_text(page: PackInventoryPage) -> str:
    if page.total_count == 0:
        return """
<b>🎁 Мои паки</b>

Паков пока нет.

Паки можно получить в наградах, событиях, Hockey Pass или через магазин.
""".strip()

    return f"""
<b>🎁 Мои паки</b>

Всего паков: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

Выбери пак для просмотра и открытия.
""".strip()


def build_user_pack_profile_text(pack: PackInfo, quantity: int) -> str:
    return f"""
<b>🎁 {safe(pack.name)}</b>

{safe(pack.description)}

Карточек внутри: <b>{pack.cards_count}</b>
Карт в розыгрыше: <b>{pack.selected_cards_count}</b>
Доступно: <b>{quantity}</b>
Цена: <b>{build_pack_price_text(pack)}</b>

Нажми кнопку ниже, чтобы открыть пак.
""".strip()


def build_pack_opening_result_text(result: PackOpeningResult) -> str:
    rewards_lines = []

    for index, reward in enumerate(result.rewards, start=1):
        rewards_lines.append(
            f"{index}. <b>{safe(reward.name)}</b> · {reward.position} · {reward.overall} OVR\n"
            f"   🏆 {safe(reward.collection_name)} · 🏒 {safe(reward.team)} · 🌍 {safe(reward.country)} · 💎 {safe(reward.rarity)}"
        )

    rewards_text = "\n".join(rewards_lines) if rewards_lines else "Пока пусто"

    return f"""
<b>✨ Пак открыт</b>

🎁 Пак: <b>{safe(result.pack_name)}</b>

<b>Выпали карточки:</b>
{rewards_text}

Карточки уже добавлены в коллекцию.
""".strip()


def build_pack_opening_start_text(result: PackOpeningResult) -> str:
    cards_count = len(result.rewards)
    cards_word = "карта" if cards_count == 1 else "карт"

    return f"""
<b>✨ Открываем пак</b>

🎁 Пак: <b>{safe(result.pack_name)}</b>
🃏 Внутри: <b>{cards_count}</b> {cards_word}

Сейчас начнётся раскрытие карточек.
Сначала появится дивизион, затем команда, потом национальность игрока.
""".strip()


def build_pack_animation_division_text(result: PackOpeningResult, reward, index: int, total: int, division_name: str | None = None) -> str:
    division_title = division_name or getattr(reward, "division_name", None) or "Без дивизиона"
    return f"""
<b>✨ Открытие пака</b>

🎁 <b>{safe(result.pack_name)}</b>
🃏 Карточка <b>{index}/{total}</b>

┏━━━━━━━━━━━━━━━━━━━━┓
┃ 🏆 ДИВИЗИОН
┃ <b>{safe(division_title)}</b>
┗━━━━━━━━━━━━━━━━━━━━┛

Команда скоро появится...
""".strip()


def build_pack_animation_team_text(result: PackOpeningResult, reward, index: int, total: int, division_name: str | None = None) -> str:
    division_title = division_name or getattr(reward, "division_name", None) or "Без дивизиона"
    return f"""
<b>✨ Открытие пака</b>

🎁 <b>{safe(result.pack_name)}</b>
🃏 Карточка <b>{index}/{total}</b>

┏━━━━━━━━━━━━━━━━━━━━┓
┃ 🏆 Дивизион
┃ <b>{safe(division_title)}</b>
┣━━━━━━━━━━━━━━━━━━━━┫
┃ 🏒 КОМАНДА
┃ <b>{safe(reward.team)}</b>
┗━━━━━━━━━━━━━━━━━━━━┛

Страна игрока раскрывается...
""".strip()


def build_pack_animation_country_text(result: PackOpeningResult, reward, index: int, total: int, division_name: str | None = None) -> str:
    division_title = division_name or getattr(reward, "division_name", None) or "Без дивизиона"
    return f"""
<b>✨ Открытие пака</b>

🎁 <b>{safe(result.pack_name)}</b>
🃏 Карточка <b>{index}/{total}</b>

┏━━━━━━━━━━━━━━━━━━━━┓
┃ 🏆 Дивизион
┃ <b>{safe(division_title)}</b>
┣━━━━━━━━━━━━━━━━━━━━┫
┃ 🏒 Команда
┃ <b>{safe(reward.team)}</b>
┣━━━━━━━━━━━━━━━━━━━━┫
┃ 🌍 НАЦИОНАЛЬНОСТЬ
┃ <b>{safe(reward.country)}</b>
┗━━━━━━━━━━━━━━━━━━━━┛

Финальное раскрытие...
""".strip()


def build_pack_animation_reveal_text(result: PackOpeningResult, reward, index: int, total: int) -> str:
    return f"""
<b>🔥 Карточка раскрыта</b>

🎁 <b>{safe(result.pack_name)}</b>
🃏 Карточка <b>{index}/{total}</b>

┏━━━━━━━━━━━━━━━━━━━━┓
┃ <b>{safe(reward.name)}</b>
┃ ⭐ {reward.overall} OVR · {safe(reward.position)}
┃ 🏒 {safe(reward.team)}
┃ 🌍 {safe(reward.country)}
┃ 💎 {safe(reward.rarity)}
┗━━━━━━━━━━━━━━━━━━━━┛
""".strip()


def build_pack_reward_caption(reward) -> str:
    return f"""
🃏 <b>{safe(reward.name)}</b>

⭐ <b>{reward.overall} OVR</b> · {safe(reward.position)}
🏒 {safe(reward.team)}
🌍 {safe(reward.country)}
🏆 {safe(reward.collection_name)}
💎 {safe(reward.rarity)}
""".strip()


def build_pack_opening_finish_text(result: PackOpeningResult) -> str:
    return f"""
<b>✅ Пак открыт</b>

🎁 <b>{safe(result.pack_name)}</b>
🃏 Карточки добавлены в коллекцию.

Можно открыть другие паки, посмотреть историю или перейти к своим карточкам.
""".strip()


def build_pack_opening_error_text(error: str) -> str:
    return f"""
<b>🎁 Пак не открыт</b>

{safe(error)}
""".strip()


def build_pack_history_text(page: PackHistoryPage) -> str:
    if page.total_count == 0:
        return """
<b>📜 История открытий</b>

История пока пустая.
""".strip()

    lines = []

    for opening in page.openings:
        lines.append(
            f"🎁 <b>{safe(opening.pack_name)}</b> · {opening.rewards_count} карт.\n"
            f"   {safe(opening.created_at)}"
        )

    return f"""
<b>📜 История открытий</b>

Всего открытий: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

{chr(10).join(lines)}
""".strip()


def build_admin_packs_page_text(page: AdminPacksPage) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return f"""
<b>🎁 Паки</b>

Паки не найдены.{search_line}
""".strip()

    lines = []

    for pack in page.packs:
        status = "активен" if pack.active else "выключен"
        shop = "в магазине" if pack.is_shop_available else "только выдача"
        price = "бесплатно"

        if pack.price_amount > 0 and pack.price_currency_code:
            price = f"{pack.price_amount:,} {pack.price_currency_code}".replace(",", " ")

        lines.append(
            f"🎁 <b>{safe(pack.name)}</b>\n"
            f"   Карт внутри: <b>{pack.cards_count}</b> · Выбрано: <b>{pack.selected_cards_count}</b> · Цена: <b>{safe(price)}</b> · {status} · {shop}"
        )

    return f"""
<b>🎁 Паки</b>

Всего паков: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

{chr(10).join(lines)}
""".strip()


def build_admin_pack_profile_text(pack: AdminPackDetails) -> str:
    status = "✅ Активен" if pack.active else "⏸ Выключен"
    shop = "🛒 В магазине" if pack.is_shop_available else "🎯 Только выдача и награды"
    starter = "\n🌟 Стартовый пак" if pack.is_starter else ""
    free_note = "\n🎟 Бесплатный пак открывается один раз" if pack.price_amount <= 0 else ""

    return f"""
<b>🎁 {safe(pack.name)}</b>

{safe(pack.description)}

🆔 Код: <code>{safe(pack.code)}</code>
🃏 Карт внутри: <b>{pack.cards_count}</b>
🏒 Карт в розыгрыше: <b>{pack.selected_cards_count}</b>
💰 Цена: <b>{build_pack_price_text(pack)}</b>
{status}
{shop}{starter}{free_note}

<b>🎲 Шансы редкостей:</b>
{build_rarity_chances_text(pack.rarity_chances)}
""".strip()


def build_pack_draft_text(draft: PackDraft) -> str:
    price = "бесплатно"

    if draft.price_currency_code and draft.price_amount > 0:
        price = f"{draft.price_amount:,} {draft.price_currency_code}".replace(",", " ")

    shop = "🛒 В магазине" if draft.is_shop_available else "🎯 Только награды и выдача"

    return f"""
<b>✅ Проверь пак</b>

🎁 Название: <b>{safe(draft.name)}</b>
📝 Описание: {safe(draft.description)}
🃏 Карт внутри: <b>{draft.cards_count}</b>
💰 Цена: <b>{safe(price)}</b>
{shop}

По умолчанию будут выставлены шансы:
⚪ Common — <b>70%</b>
🔵 Rare — <b>20%</b>
🟣 Epic — <b>8%</b>
🟠 Legendary — <b>2%</b>

После сохранения шансы можно поменять в карточке пака.
""".strip()


def build_admin_give_pack_page_text(page: PackChoicePage, nickname: str) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return f"""
<b>🎁 Выдать пак</b>

Игрок: <b>{safe(nickname)}</b>

Подходящие паки не найдены.
""".strip()

    return f"""
<b>🎁 Выдать пак</b>

Игрок: <b>{safe(nickname)}</b>
Паков найдено: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери пак для выдачи.
""".strip()


def build_admin_pack_cards_text(page: PackCardsPage, pack_name: str) -> str:
    if page.total_count == 0:
        return f"""
<b>🏒 Карты в паке</b>

Пак: <b>{safe(pack_name)}</b>

Карты пока не выбраны. Добавь карточки, из которых игроки будут получать награды при открытии пака.
""".strip()

    lines = []

    for card in page.cards:
        lines.append(
            f"🃏 <b>{safe(card.name)}</b> · {card.position} · {card.overall} OVR\n"
            f"   {safe(card.team)} · {safe(card.country)} · {safe(card.collection_name)} · {safe(card.rarity)}"
        )

    return f"""
<b>🏒 Карты в паке</b>

Пак: <b>{safe(pack_name)}</b>
Выбрано карт: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

{chr(10).join(lines)}

Нажми на карточку, чтобы убрать её из пака.
""".strip()


def build_admin_pack_available_cards_text(page: PackCardsPage, pack_name: str) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return f"""
<b>➕ Добавить карту в пак</b>

Пак: <b>{safe(pack_name)}</b>{search_line}

Подходящие карточки не найдены.
""".strip()

    return f"""
<b>➕ Добавить карту в пак</b>

Пак: <b>{safe(pack_name)}</b>
Найдено карт: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери карточку, чтобы добавить её в розыгрыш пака.
""".strip()


ADMIN_PACK_CARD_SEARCH_TEXT = """
<b>🔎 Поиск карты</b>

Отправь имя игрока, команду, страну, коллекцию, редкость, позицию или ID карточки.
""".strip()
