from html import escape

from app.services.community import (
    ClanProfile,
    ClansPage,
    CommunityPlayersPage,
    PublicPlayerProfile,
    TradeCardChoicesPage,
    TradeCosmeticChoicesPage,
    TradeCosmeticsPage,
    TradeOffersPage,
    TradeOfferProfile,
    TradeUserCardsPage,
)
from app.services.card_sorting import sort_label
from app.services.war2_cosmetics import cosmetic_type_title

COMMUNITY_MAIN_TEXT = """
<b>🤝 Сообщество</b>

Здесь игроки встречаются вне льда: смотрят профили, создают обмены и собираются в кланы.

Выбери раздел ниже.
""".strip()

PLAYERS_SEARCH_TEXT = """
<b>🔎 Поиск игроков</b>

Введи никнейм, username или ID игрока.
""".strip()

TRADE_MAIN_TEXT = """
<b>🔁 Рынок обменов</b>

Создавай предложения и обменивайся с другими игроками.

Можно обменивать:
• карточки и косметику на карточки;
• карточки и косметику на косметику;
• карточки и косметику на валюту.

Каждая рамка, приписка, фон и титул — отдельный трейдабл-экземпляр. Экипированные и установленные на карты предметы сначала нужно снять.
""".strip()

TRADE_DIRECT_SEARCH_TEXT = """
<b>🎯 Личный обмен</b>

Найди игрока по никнейму, username или ID.

Личный обмен можно отправить только игроку с открытой коллекцией карточек.
""".strip()

TRADE_DIRECT_PLAYERS_TEXT = """
<b>🎯 Выбор игрока</b>

Выбери игрока для личного предложения.
""".strip()

TRADE_CREATE_TEXT = """
<b>➕ Новый обмен</b>

Сначала выбери карточки и/или косметику, которые готов отдать.

Карточки из состава и заблокированные карточки не участвуют в обменах. Косметика должна быть снята с профиля и не установлена на карту.
""".strip()

TRADE_WANTED_TEXT = """
<b>🎯 Что хочешь получить?</b>

Выбери формат обмена.
""".strip()

TRADE_CURRENCY_AMOUNT_TEXT = """
<b>💰 Сумма обмена</b>

Введи сумму валюты, которую хочешь получить за выбранные карточки.
""".strip()

TRADE_WANTED_CARDS_TEXT = """
<b>🎴 Карточки для обмена</b>

Выбери карточки, на которые готов обменяться.
""".strip()

TRADE_WANTED_COSMETICS_TEXT = """
<b>🎨 Косметика для обмена</b>

Выбери тип косметики, который хочешь получить. При принятии передаётся один свободный экземпляр каждого выбранного предмета.
""".strip()

CLANS_MAIN_TEXT = """
<b>🏰 Кланы</b>

Создай свою команду или вступи в уже существующий клан.
""".strip()

CLAN_CREATE_NAME_TEXT = """
<b>🏰 Новый клан</b>

Введи название клана от 3 до 32 символов.
""".strip()

CLAN_CREATE_DESCRIPTION_TEXT = """
<b>📝 Описание клана</b>

Введи короткое описание клана до 300 символов.
""".strip()

CLAN_SEARCH_TEXT = """
<b>🔎 Поиск клана</b>

Введи название или часть описания.
""".strip()

ADMIN_CLANS_TEXT = """
<b>🤝 Управление кланами</b>

Здесь можно смотреть кланы, включать, закрывать и расформировывать команды.
""".strip()

ADMIN_TRADES_TEXT = """
<b>🔁 Управление обменами</b>

Здесь видны предложения игроков и их статусы.
""".strip()


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_card_line(card) -> str:
    return f"🏒 <b>{card.name}</b> • {card.position} • {card.overall} OVR • {card.rarity}"


def build_players_page_text(page: CommunityPlayersPage) -> str:
    if not page.players:
        return "<b>👤 Игроки</b>\n\nПока никого не найдено."

    lines = [
        "<b>👤 Игроки лиги</b>",
        f"Найдено: <b>{page.total_count}</b>",
        "",
    ]
    for index, player in enumerate(page.players, start=(page.page - 1) * 5 + 1):
        privacy = "🌍" if player.privacy_public_cards else "🔒"
        lines.append(
            f"{index}. {privacy} <b>{escape(player.nickname, quote=False)}</b> • {player.league} • {format_number(player.rating_points)} очков"
        )
        lines.append(f"   ✅ {player.wins} • ❌ {player.losses} • 🏟 {player.matches_played}")

    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_public_player_profile_text(profile: PublicPlayerProfile) -> str:
    username = f"@{escape(profile.username, quote=False)}" if profile.username else "не указан"
    winrate = round(profile.wins / profile.matches_played * 100) if profile.matches_played else 0
    cards_status = "открыта" if profile.privacy_public_cards else "скрыта"

    lines = [
        f"<b>👤 {escape(profile.nickname, quote=False)}</b>",
        f"🔗 Username: <b>{username}</b>",
        "",
        f"🏆 Лига: <b>{profile.league}</b>",
        f"⭐ Рейтинг: <b>{format_number(profile.rating_points)}</b>",
        f"🎟 Hockey Pass: <b>{profile.hockey_pass_level}</b> уровень",
        "",
        f"📊 Матчи: <b>{profile.matches_played}</b>",
        f"✅ Победы: <b>{profile.wins}</b>",
        f"❌ Поражения: <b>{profile.losses}</b>",
        f"📈 Победы: <b>{winrate}%</b>",
        f"🥅 Голы: <b>{profile.goals_scored}</b> / пропущено <b>{profile.goals_allowed}</b>",
        "",
        f"🧩 Состав: <b>{profile.lineup_count}/6</b>",
        f"💪 OVR состава: <b>{profile.lineup_ovr}</b>",
        f"🃏 Коллекция: <b>{cards_status}</b>",
    ]

    if profile.lineup_cards:
        lines.append("")
        lines.append("<b>🧩 Состав</b>")
        for card in profile.lineup_cards:
            lines.append(format_card_line(card))

    if profile.top_cards:
        lines.append("")
        lines.append("<b>⭐ Лучшие карточки</b>")
        for card in profile.top_cards:
            lines.append(format_card_line(card))
    elif not profile.privacy_public_cards:
        lines.append("")
        lines.append("🔒 Игрок скрыл коллекцию карточек.")

    return "\n".join(lines)


def build_trade_user_cards_page_text(page: TradeUserCardsPage) -> str:
    lines = [
        "<b>🎴 Выбери карточки для обмена</b>",
        f"Выбрано: <b>{len(page.selected_ids)}/3</b>",
        f"Сортировка: <b>{sort_label(page.sort_order)}</b>",
        "",
    ]
    if not page.cards:
        lines.append("Свободных карточек пока нет.")
    else:
        for card in page.cards:
            lines.append(format_card_line(card))
    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_trade_card_choices_page_text(page: TradeCardChoicesPage) -> str:
    lines = [
        "<b>🎯 Выбери желаемые карточки</b>",
        f"Выбрано: <b>{len(page.selected_card_ids)}/3</b>",
        f"Сортировка: <b>{sort_label(page.sort_order)}</b>",
        "",
    ]
    if not page.cards:
        lines.append("Карточки не найдены.")
    else:
        for card in page.cards:
            lines.append(f"🏒 <b>{card.name}</b> • {card.position} • {card.overall} OVR • {card.rarity}")
    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)



def _format_cosmetic_line(item) -> str:
    badge = f" · [{escape(item.badge_text, quote=False)}]" if item.badge_text else ""
    return f"🎨 <b>{escape(item.title, quote=False)}</b>{badge} · {cosmetic_type_title(item.type)} · {item.rarity}"


def build_trade_cosmetics_page_text(page: TradeCosmeticsPage) -> str:
    lines = [
        "<b>🎨 Выбери косметику для обмена</b>",
        f"Выбрано экземпляров: <b>{len(page.selected_ids)}/3</b>",
        "",
    ]
    if not page.items:
        lines.append("Свободной косметики нет. Сними предмет с профиля или карты, чтобы обменять его.")
    else:
        for item in page.items:
            lines.append(_format_cosmetic_line(item) + f" · экземпляр #{item.id}")
    lines.extend(["", f"Страница {page.page}/{page.pages_count}"])
    return "\n".join(lines)


def build_trade_cosmetic_choices_page_text(page: TradeCosmeticChoicesPage) -> str:
    lines = [
        "<b>🎯 Выбери желаемую косметику</b>",
        f"Выбрано: <b>{len(page.selected_item_ids)}/3</b>",
        "",
    ]
    if not page.items:
        lines.append("Косметика не найдена.")
    else:
        for item in page.items:
            lines.append(_format_cosmetic_line(item))
    lines.extend(["", f"Страница {page.page}/{page.pages_count}"])
    return "\n".join(lines)

def build_trade_offers_page_text(page: TradeOffersPage) -> str:
    title = "<b>🔁 Рынок обменов</b>" if page.mode != "my" else "<b>📦 Мои обмены</b>"
    if page.mode == "admin":
        title = "<b>🔁 Все обмены</b>"

    lines = [title, f"Всего: <b>{page.total_count}</b>", ""]
    if not page.offers:
        lines.append("Предложений пока нет.")
    else:
        for offer in page.offers:
            if offer.wanted_type == "currency":
                wanted = f"{offer.wanted_currency_icon or '💰'} {format_number(offer.wanted_currency_amount)} {offer.wanted_currency_name or offer.wanted_currency_code}"
            elif offer.wanted_asset_type == "cosmetics":
                wanted = f"🎨 {offer.wanted_cosmetics_count} предмет(а)"
            else:
                wanted = f"🎴 {offer.wanted_cards_count} карт."
            status = {
                "open": "🟢 открыто",
                "accepted": "✅ принято",
                "cancelled": "🚫 отменено",
            }.get(offer.status, offer.status)
            target = f" → 🎯 {escape(offer.target_nickname, quote=False)}" if offer.target_nickname else ""
            giving_parts = []
            if offer.offered_count:
                giving_parts.append(f"🎴 {offer.offered_count}")
            if offer.offered_cosmetics_count:
                giving_parts.append(f"🎨 {offer.offered_cosmetics_count}")
            giving = " + ".join(giving_parts) or "ничего"
            lines.append(f"#{offer.id} • <b>{escape(offer.creator_nickname, quote=False)}</b>{target} • отдаёт {giving} → {wanted} • {status}")
    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_trade_offer_profile_text(offer: TradeOfferProfile) -> str:
    status = {
        "open": "🟢 открыто",
        "accepted": "✅ принято",
        "cancelled": "🚫 отменено",
    }.get(offer.status, offer.status)
    target_line = f"🎯 Получатель: <b>{escape(offer.target_nickname, quote=False)}</b>" if offer.target_nickname else "🌍 Тип: <b>рынок обменов</b>"
    lines = [
        f"<b>🔁 Обмен #{offer.id}</b>",
        f"👤 Автор: <b>{escape(offer.creator_nickname, quote=False)}</b>",
        target_line,
        f"📌 Статус: <b>{status}</b>",
        "",
        "<b>Отдаёт</b>",
    ]
    for card in offer.offered_cards:
        lines.append(format_card_line(card))
    for item in offer.offered_cosmetics:
        lines.append(_format_cosmetic_line(item) + f" · экземпляр #{item.id}")
    if not offer.offered_cards and not offer.offered_cosmetics:
        lines.append("—")

    lines.append("")
    lines.append("<b>Хочет получить</b>")
    if offer.wanted_type == "currency":
        lines.append(f"{offer.wanted_currency_icon or '💰'} <b>{format_number(offer.wanted_currency_amount)}</b> {offer.wanted_currency_name or offer.wanted_currency_code}")
    elif offer.wanted_asset_type == "cosmetics":
        for item, quantity in offer.wanted_cosmetics:
            lines.append(f"{quantity}× {_format_cosmetic_line(item)}")
    else:
        for card, quantity in offer.wanted_cards:
            lines.append(f"{quantity}× {format_card_line(card)}")

    if offer.accepted_by_nickname:
        lines.append("")
        lines.append(f"🤝 Принял: <b>{escape(offer.accepted_by_nickname, quote=False)}</b>")

    return "\n".join(lines)


def build_clans_page_text(page: ClansPage, admin: bool = False) -> str:
    title = "<b>🏰 Кланы</b>" if not admin else "<b>🤝 Кланы игроков</b>"
    lines = [title, f"Всего: <b>{page.total_count}</b>", ""]
    if not page.clans:
        lines.append("Кланов пока нет.")
    else:
        for clan in page.clans:
            status = "🟢" if clan.active else "🔴"
            lines.append(f"{status} <b>{escape(clan.name, quote=False)}</b> • 👥 {clan.members_count} • ⭐ {format_number(clan.rating_points)}")
            if clan.description:
                lines.append(f"   {escape(clan.description[:70], quote=False)}")
    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_clan_profile_text(profile: ClanProfile, admin: bool = False) -> str:
    status = "открыт" if profile.active else "закрыт"
    role_names = {"leader": "👑 президент", "officer": "🥈 вице-президент", "member": "🏒 участник"}
    lines = [
        f"<b>🏰 {escape(profile.name, quote=False)}</b>",
        f"📌 Статус: <b>{status}</b>",
        f"👥 Участники: <b>{profile.members_count}/10</b>",
        f"⭐ Рейтинг: <b>{format_number(profile.rating_points)}</b>",
        f"✅ Победы: <b>{profile.wins}</b>",
    ]
    if profile.description:
        lines.extend(["", profile.description])
    if profile.created_by_nickname:
        lines.append(f"\n👑 Президент: <b>{escape(profile.created_by_nickname, quote=False)}</b>")
    if profile.viewer_role and not admin:
        lines.append(f"🎖 Твоя роль: <b>{role_names.get(profile.viewer_role, profile.viewer_role)}</b>")

    if profile.members:
        lines.append("\n<b>Состав клана</b>")
        for member in profile.members:
            lines.append(f"{role_names.get(member.role, member.role)} • <b>{escape(member.nickname, quote=False)}</b>")

    return "\n".join(lines)


def build_action_result_text(title: str, description: str) -> str:
    return f"<b>{title}</b>\n\n{description}"


CLAN_MANAGE_TEXT = """
<b>🏰 Управление составом</b>

Выбери игрока, чтобы назначить вице-президента или исключить из клана.

👑 Президент — полный контроль над кланом.
🥈 Вице-президент — может исключать обычных участников. В клане только один вице.
""".strip()


def build_clan_member_manage_text(nickname: str, role: str) -> str:
    role_names = {"leader": "👑 президент", "officer": "🥈 вице-президент", "member": "🏒 участник"}
    return f"""
<b>🏒 Игрок клана</b>

👤 <b>{escape(nickname, quote=False)}</b>
🎖 Роль: <b>{role_names.get(role, role)}</b>

Выбери действие ниже.
""".strip()


def build_clan_requests_text(requests) -> str:
    if not requests:
        return "<b>📥 Заявки в клан</b>\n\nНовых заявок нет."
    lines = ["<b>📥 Заявки в клан</b>", "", f"Ожидают решения: <b>{len(requests)}</b>", ""]
    for req in requests:
        lines.append(f"👤 <b>{escape(req['nickname'], quote=False)}</b>")
    lines.append("")
    lines.append("✅ — принять, ❌ — отклонить.")
    return "\n".join(lines)

