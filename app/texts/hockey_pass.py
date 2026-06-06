from html import escape

from app.services.hockey_pass import (
    AdminRewardsPage,
    ClaimResult,
    ChoicePage,
    HockeyPassDraft,
    HockeyPassPage,
    HockeyPassProfile,
    HockeyPassRewardItem,
    PurchaseResult,
    RewardDraft,
    TRACK_TITLES,
    UserHockeyPassInfo,
    UserRewardsPage,
    format_price,
    parse_stored_datetime,
)


ADMIN_HPASS_MAIN_TEXT = """
<b>🎟 Hockey Pass</b>

Здесь создаётся сезонный пропуск, настраивается дата окончания, цена Premium и награды каждого уровня.

Free-ветка доступна всем игрокам. Premium игроки открывают прямо в разделе Hockey Pass.
""".strip()

HPASS_NO_ACTIVE_TEXT = """
<b>🎟 Hockey Pass</b>

Сейчас сезонный пропуск ещё не открыт.

Как только администрация запустит новый сезон, здесь появятся уровни, награды и Premium-ветка.
""".strip()

ADMIN_HPASS_TITLE_TEXT = """
<b>✏️ Название Hockey Pass</b>

Отправь название сезона.

Пример: <b>Season 1</b>
""".strip()

ADMIN_HPASS_DESCRIPTION_TEXT = """
<b>📝 Описание Hockey Pass</b>

Отправь короткое описание для игроков.

Можно отправить <b>-</b>, если описание не нужно.
""".strip()

ADMIN_HPASS_END_TEXT = """
<b>⏰ Дата окончания</b>

Отправь дату и время окончания по МСК.

Формат: <b>31.07.2026 23:59</b>
""".strip()

ADMIN_HPASS_PRICE_TEXT = """
<b>👑 Цена Premium</b>

Отправь стоимость Premium.

Если Premium бесплатный, отправь <b>0</b>.
""".strip()

ADMIN_HPASS_REWARD_LEVEL_TEXT = """
<b>🔢 Уровень награды</b>

Отправь уровень от <b>1</b> до <b>40</b>.
""".strip()

ADMIN_HPASS_REWARD_AMOUNT_TEXT = """
<b>🔢 Количество</b>

Отправь количество награды.

Для валюты — сумма. Для пака или карточки можно отправить <b>1</b>.
""".strip()

ADMIN_HPASS_REWARD_TITLE_TEXT = """
<b>✏️ Название награды</b>

Отправь красивое название награды.

Можно отправить <b>-</b>, чтобы бот создал название сам.
""".strip()

ADMIN_HPASS_PACK_SEARCH_TEXT = """
<b>🔎 Поиск пака</b>

Отправь название или код пака.
""".strip()

ADMIN_HPASS_CARD_SEARCH_TEXT = """
<b>🔎 Поиск карточки</b>

Отправь имя игрока, команду, страну, редкость или коллекцию.
""".strip()

ADMIN_HPASS_BAD_TITLE_TEXT = "Название должно быть от 3 до 80 символов."
ADMIN_HPASS_BAD_DESCRIPTION_TEXT = "Описание должно быть до 300 символов."
ADMIN_HPASS_BAD_DATE_TEXT = "Дата должна быть в формате 31.07.2026 23:59 по МСК."
ADMIN_HPASS_BAD_NUMBER_TEXT = "Отправь целое число."
ADMIN_HPASS_SAVED_TEXT = "✅ Hockey Pass создан."
ADMIN_HPASS_UPDATED_TEXT = "✅ Изменения сохранены."
ADMIN_HPASS_DELETED_TEXT = "🗑 Hockey Pass удалён."
ADMIN_HPASS_REWARD_SAVED_TEXT = "✅ Награда сохранена."
ADMIN_HPASS_REWARD_DELETED_TEXT = "🗑 Награда удалена."
ADMIN_HPASS_NOT_FOUND_TEXT = "Hockey Pass уже недоступен."
ADMIN_HPASS_REWARD_NOT_FOUND_TEXT = "Награда уже недоступна."


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"
    text = str(value).strip()
    return escape(text, quote=False) if text else "не указано"


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_date(value: str | None) -> str:
    parsed = parse_stored_datetime(value)
    if parsed is None:
        return "не указано"
    return parsed.strftime("%d.%m.%Y %H:%M МСК")


def build_progress_bar(level: int, max_level: int = 40, size: int = 10) -> str:
    filled = min(size, max(0, round(level / max_level * size)))
    return "🟦" * filled + "▫️" * (size - filled)


def build_user_hockey_pass_text(info: UserHockeyPassInfo) -> str:
    if info.pass_id is None:
        return HPASS_NO_ACTIVE_TEXT

    premium_status = "👑 открыт" if info.premium_unlocked else "🔒 не открыт"
    price = format_price(
        info.premium_price_amount,
        info.premium_currency_icon,
        info.premium_currency_name,
        info.premium_currency_code,
    )

    next_line = "максимальный уровень" if info.points_to_next <= 0 else f"ещё {info.points_to_next} BP Points"

    return (
        f"<b>🎟 {safe(info.title)}</b>\n\n"
        f"{safe(info.description)}\n\n"
        f"{build_progress_bar(info.level, info.levels_count)}\n"
        f"⭐ Уровень: <b>{info.level}/{info.levels_count}</b>\n"
        f"🔥 BP Points: <b>{info.bp_points}</b>\n"
        f"🚀 До следующего уровня: <b>{next_line}</b>\n\n"
        f"🎟 Free: <b>{info.free_claimed}/{info.free_total}</b>\n"
        f"👑 Premium: <b>{premium_status}</b>\n"
        f"🎁 Premium-награды: <b>{info.premium_claimed}/{info.premium_total}</b>\n"
        f"💰 Цена Premium: <b>{price}</b>\n"
        f"⏰ До: <b>{format_date(info.end_at)}</b>\n\n"
        "Открывай уровни, забирай награды и усиливай состав."
    )


def build_user_rewards_page_text(page: UserRewardsPage) -> str:
    if not page.items:
        return "<b>🎁 Награды Hockey Pass</b>\n\nНаграды пока не добавлены."

    lines = ["<b>🎁 Награды Hockey Pass</b>", ""]
    for reward in page.items:
        lines.append(format_reward_line(reward))
    lines.append("Выбери награду ниже, чтобы посмотреть детали или забрать приз.")
    return "\n".join(lines).strip()


def format_reward_line(reward: HockeyPassRewardItem) -> str:
    track = "👑 Premium" if reward.track == "premium" else "🎟 Free"
    status = "✅ получено" if reward.claimed else "🎁 доступно" if reward.available else f"🔒 {reward.locked_reason}"
    return f"<b>Ур. {reward.level}</b> · {track}\n{reward.title}\n{status}\n"


def build_user_reward_profile_text(reward: HockeyPassRewardItem) -> str:
    track = "👑 Premium" if reward.track == "premium" else "🎟 Free"
    status = "✅ Уже получена" if reward.claimed else "🎁 Можно забрать" if reward.available else f"🔒 {reward.locked_reason}"
    return (
        f"<b>🎁 Награда уровня {reward.level}</b>\n\n"
        f"{track}\n"
        f"🏆 {safe(reward.title)}\n"
        f"📌 Статус: <b>{status}</b>"
    )


def build_premium_buy_text(info: UserHockeyPassInfo) -> str:
    price = format_price(info.premium_price_amount, info.premium_currency_icon, info.premium_currency_name, info.premium_currency_code)
    return (
        f"<b>👑 Premium Hockey Pass</b>\n\n"
        f"Откроется Premium-ветка сезона <b>{safe(info.title)}</b>.\n\n"
        f"💰 Цена: <b>{price}</b>\n"
        f"⏰ Сезон до: <b>{format_date(info.end_at)}</b>\n\n"
        "После покупки все доступные Premium-награды можно будет забрать сразу."
    )


def build_premium_purchase_result_text(result: PurchaseResult) -> str:
    balance = "" if result.balance_after is None else f"\n💼 Остаток: <b>{format_number(result.balance_after)}</b>"
    return (
        "<b>👑 Premium открыт!</b>\n\n"
        f"Сезон: <b>{safe(result.title)}</b>\n"
        f"Стоимость: <b>{safe(result.price_text)}</b>{balance}\n\n"
        "Теперь можно забирать Premium-награды."
    )


def build_claim_result_text(result: ClaimResult) -> str:
    return (
        "<b>🎁 Награда получена!</b>\n\n"
        f"{safe(result.reward.title)}\n\n"
        "Продолжай играть и открывать новые уровни."
    )


def build_admin_passes_page_text(page: HockeyPassPage) -> str:
    if not page.items:
        return "<b>🎟 Hockey Pass</b>\n\nПока нет созданных пропусков."

    lines = ["<b>🎟 Hockey Pass</b>", ""]
    for item in page.items:
        status = "✅ активен" if item.active else "⏸ выключен"
        price = "бесплатно" if item.premium_price_amount <= 0 else f"{format_number(item.premium_price_amount)} {item.premium_currency_code or ''}".strip()
        lines.append(f"<b>{safe(item.title)}</b> · {status}\n⏰ До: {format_date(item.end_at)}\n👑 Premium: {price}\n🎁 Наград: {item.rewards_count}\n")
    return "\n".join(lines).strip()


def build_admin_pass_profile_text(profile: HockeyPassProfile) -> str:
    status = "✅ активен" if profile.active else "⏸ выключен"
    finished = "\n🏁 Сезон завершён" if profile.is_finished else ""
    price = format_price(
        profile.premium_price_amount,
        profile.premium_currency_icon,
        profile.premium_currency_name,
        profile.premium_currency_code,
    )
    return (
        f"<b>🎟 {safe(profile.title)}</b>\n\n"
        f"{safe(profile.description)}\n\n"
        f"📌 Статус: <b>{status}</b>{finished}\n"
        f"⭐ Уровней: <b>{profile.levels_count}</b>\n"
        f"🔥 Шаг уровня: <b>{profile.points_per_level} BP Points</b>\n"
        f"👑 Premium: <b>{price}</b>\n"
        f"⏰ Начало: <b>{format_date(profile.start_at)}</b>\n"
        f"⏰ Окончание: <b>{format_date(profile.end_at)}</b>\n\n"
        f"🎁 Наград: <b>{profile.rewards_count}</b>\n"
        f"👥 Участников: <b>{profile.users_count}</b>\n"
        f"👑 Premium-игроков: <b>{profile.premium_users_count}</b>"
    )


def build_pass_draft_text(draft: HockeyPassDraft) -> str:
    price = format_price(draft.premium_price_amount, None, None, draft.premium_currency_code)
    return (
        "<b>✅ Проверка Hockey Pass</b>\n\n"
        f"🎟 Название: <b>{safe(draft.title)}</b>\n"
        f"📝 Описание: <b>{safe(draft.description) if draft.description else 'без описания'}</b>\n"
        f"⏰ Окончание: <b>{format_date(draft.end_at)}</b>\n"
        f"👑 Premium: <b>{price}</b>\n\n"
        "Сохранить сезонный пропуск?"
    )


def build_admin_pass_delete_text(profile: HockeyPassProfile) -> str:
    return (
        f"<b>🗑 Удалить Hockey Pass?</b>\n\n"
        f"{safe(profile.title)}\n\n"
        "Все награды и отметки получения по этому пропуску будут удалены."
    )


def build_admin_rewards_page_text(page: AdminRewardsPage) -> str:
    if not page.items:
        return f"<b>🎁 Награды</b>\n\nВ Pass <b>{safe(page.pass_title)}</b> пока нет наград."

    lines = [f"<b>🎁 Награды: {safe(page.pass_title)}</b>", ""]
    for reward in page.items:
        status = "✅" if reward.active else "⏸"
        track = "👑 Premium" if reward.track == "premium" else "🎟 Free"
        lines.append(f"{status} <b>Ур. {reward.level}</b> · {track}\n{reward.title}\n")
    return "\n".join(lines).strip()


def build_admin_reward_profile_text(reward: HockeyPassRewardItem) -> str:
    status = "✅ активна" if reward.active else "⏸ выключена"
    track = "👑 Premium" if reward.track == "premium" else "🎟 Free"
    return (
        f"<b>🎁 Награда уровня {reward.level}</b>\n\n"
        f"📌 Статус: <b>{status}</b>\n"
        f"🌿 Ветка: <b>{track}</b>\n"
        f"🎁 Тип: <b>{safe(reward.reward_type)}</b>\n"
        f"🏆 Название: <b>{safe(reward.title)}</b>\n"
        f"🔢 Количество: <b>{reward.amount}</b>"
    )


def build_reward_draft_text(draft: RewardDraft) -> str:
    track = "👑 Premium" if draft.track == "premium" else "🎟 Free"
    type_text = {"currency": "💱 Валюта", "pack": "🎁 Пак", "card": "🃏 Карточка"}.get(draft.reward_type, draft.reward_type)
    title = draft.title or "название будет создано автоматически"
    return (
        "<b>✅ Проверка награды</b>\n\n"
        f"🔢 Уровень: <b>{draft.level}</b>\n"
        f"🌿 Ветка: <b>{track}</b>\n"
        f"🎁 Тип: <b>{type_text}</b>\n"
        f"🏆 Название: <b>{safe(title)}</b>\n"
        f"🔢 Количество: <b>{draft.amount}</b>\n\n"
        "Сохранить награду?"
    )


def build_admin_reward_delete_text(reward: HockeyPassRewardItem) -> str:
    return (
        f"<b>🗑 Удалить награду?</b>\n\n"
        f"Уровень {reward.level}\n"
        f"{safe(reward.title)}"
    )


def build_choice_page_text(title: str, page: ChoicePage) -> str:
    if not page.items:
        return f"<b>{title}</b>\n\nНичего не найдено."

    lines = [f"<b>{title}</b>", ""]
    for item in page.items:
        lines.append(f"<b>{safe(item.title)}</b>\n{safe(item.subtitle)}\n")
    return "\n".join(lines).strip()
