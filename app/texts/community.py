from app.services.community import (
    ClanProfile,
    ClansPage,
    CommunityPlayersPage,
    PublicPlayerProfile,
    TradeCardChoicesPage,
    TradeOffersPage,
    TradeOfferProfile,
    TradeUserCardsPage,
)

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

Создавай предложения, выбирай карточки и обменивайся с другими игроками.

Можно обменивать:
• карточки на карточки;
• карточки на валюту;
• несколько карточек на одну или несколько.
""".strip()

TRADE_CREATE_TEXT = """
<b>➕ Новый обмен</b>

Сначала выбери карточки, которые готов отдать.

Карточки из состава и заблокированные карточки не участвуют в обменах.
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
            f"{index}. {privacy} <b>{player.nickname}</b> • {player.league} • {format_number(player.rating_points)} очков"
        )
        lines.append(f"   ✅ {player.wins} • ❌ {player.losses} • 🏟 {player.matches_played}")

    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_public_player_profile_text(profile: PublicPlayerProfile) -> str:
    username = f"@{profile.username}" if profile.username else "не указан"
    winrate = round(profile.wins / profile.matches_played * 100) if profile.matches_played else 0
    cards_status = "открыта" if profile.privacy_public_cards else "скрыта"

    lines = [
        f"<b>👤 {profile.nickname}</b>",
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
            else:
                wanted = f"🎴 {offer.wanted_cards_count} карт."
            status = {
                "open": "🟢 открыто",
                "accepted": "✅ принято",
                "cancelled": "🚫 отменено",
            }.get(offer.status, offer.status)
            lines.append(f"#{offer.id} • <b>{offer.creator_nickname}</b> • отдаёт {offer.offered_count} карт. → {wanted} • {status}")
    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_trade_offer_profile_text(offer: TradeOfferProfile) -> str:
    status = {
        "open": "🟢 открыто",
        "accepted": "✅ принято",
        "cancelled": "🚫 отменено",
    }.get(offer.status, offer.status)
    lines = [
        f"<b>🔁 Обмен #{offer.id}</b>",
        f"👤 Автор: <b>{offer.creator_nickname}</b>",
        f"📌 Статус: <b>{status}</b>",
        "",
        "<b>Отдаёт</b>",
    ]
    for card in offer.offered_cards:
        lines.append(format_card_line(card))

    lines.append("")
    lines.append("<b>Хочет получить</b>")
    if offer.wanted_type == "currency":
        lines.append(f"{offer.wanted_currency_icon or '💰'} <b>{format_number(offer.wanted_currency_amount)}</b> {offer.wanted_currency_name or offer.wanted_currency_code}")
    else:
        for card, quantity in offer.wanted_cards:
            lines.append(f"{quantity}× {format_card_line(card)}")

    if offer.accepted_by_nickname:
        lines.append("")
        lines.append(f"🤝 Принял: <b>{offer.accepted_by_nickname}</b>")

    return "\n".join(lines)


def build_clans_page_text(page: ClansPage, admin: bool = False) -> str:
    title = "<b>🏰 Кланы</b>" if not admin else "<b>🤝 Кланы игроков</b>"
    lines = [title, f"Всего: <b>{page.total_count}</b>", ""]
    if not page.clans:
        lines.append("Кланов пока нет.")
    else:
        for clan in page.clans:
            status = "🟢" if clan.active else "🔴"
            lines.append(f"{status} <b>{clan.name}</b> • 👥 {clan.members_count} • ⭐ {format_number(clan.rating_points)}")
            if clan.description:
                lines.append(f"   {clan.description[:70]}")
    lines.append("")
    lines.append(f"Страница {page.page}/{page.pages_count}")
    return "\n".join(lines)


def build_clan_profile_text(profile: ClanProfile, admin: bool = False) -> str:
    status = "открыт" if profile.active else "закрыт"
    role_names = {"leader": "👑 лидер", "officer": "🛡 офицер", "member": "🏒 участник"}
    lines = [
        f"<b>🏰 {profile.name}</b>",
        f"📌 Статус: <b>{status}</b>",
        f"👥 Участники: <b>{profile.members_count}</b>",
        f"⭐ Рейтинг: <b>{format_number(profile.rating_points)}</b>",
        f"✅ Победы: <b>{profile.wins}</b>",
    ]
    if profile.description:
        lines.extend(["", profile.description])
    if profile.created_by_nickname:
        lines.append(f"\n👑 Основатель: <b>{profile.created_by_nickname}</b>")
    if profile.viewer_role and not admin:
        lines.append(f"🎖 Твоя роль: <b>{role_names.get(profile.viewer_role, profile.viewer_role)}</b>")

    if profile.members:
        lines.append("\n<b>Состав клана</b>")
        for member in profile.members:
            lines.append(f"{role_names.get(member.role, member.role)} • <b>{member.nickname}</b>")

    return "\n".join(lines)


def build_action_result_text(title: str, description: str) -> str:
    return f"<b>{title}</b>\n\n{description}"
