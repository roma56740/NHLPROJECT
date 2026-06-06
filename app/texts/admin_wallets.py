from html import escape

from app.services.admin_wallets import WalletCurrency, WalletOperationResult, WalletUserProfile, WalletUsersPage
from app.services.currencies import format_currency_amount


ADMIN_WALLETS_MAIN_TEXT = """
<b>💱 Кошельки игроков</b>

Здесь можно быстро пополнить баланс игрока или списать лишнюю сумму.

Доступные валюты:
🪙 Coins
⚡ Energy
🏅 Rank-point
""".strip()

ADMIN_WALLETS_SEARCH_TEXT = """
<b>🔎 Поиск игрока</b>

Отправь никнейм, username или ID игрока.
""".strip()

ADMIN_WALLETS_AMOUNT_TEXT = """
<b>{action_title}</b>

Игрок: <b>{nickname}</b>
Валюта: <b>{currency_title}</b>

Отправь сумму одним сообщением.
Например: <b>10000</b>
""".strip()

ADMIN_WALLETS_EMPTY_TEXT = """
<b>👤 Игроки не найдены</b>

Попробуй изменить запрос или открыть полный список игроков.
""".strip()

ADMIN_WALLETS_BAD_AMOUNT_TEXT = """
<b>⚠️ Сумма не подошла</b>

Отправь целое число больше нуля.
Например: <b>10000</b>
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def format_balances(profile: WalletUserProfile) -> str:
    if not profile.balances:
        return "Пока пусто"

    return "\n".join(format_currency_amount(balance) for balance in profile.balances)


def build_admin_wallets_users_page_text(page: WalletUsersPage) -> str:
    search_line = f"\n🔎 Поиск: <b>{safe(page.search)}</b>" if page.search else ""

    if page.total_count == 0:
        return ADMIN_WALLETS_EMPTY_TEXT

    return f"""
<b>💱 Кошельки игроков</b>

Всего игроков: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>{search_line}

Выбери игрока для пополнения баланса.
""".strip()


def build_admin_wallet_user_text(profile: WalletUserProfile) -> str:
    username = f"@{profile.username}" if profile.username else "не указан"
    status = "🚫 ограничен" if profile.is_banned else "✅ активен"

    return f"""
<b>💱 Кошелёк игрока</b>

🏒 Игрок: <b>{safe(profile.nickname)}</b>
🌐 Username: <b>{safe(username)}</b>
🆔 ID: <b>{profile.telegram_id}</b>
🏆 Лига: <b>{safe(profile.league)}</b>
Статус: <b>{status}</b>

<b>💰 Баланс</b>
{format_balances(profile)}

Выбери валюту и действие ниже.
""".strip()


def build_admin_wallet_currencies_text(profile: WalletUserProfile) -> str:
    return f"""
<b>💱 Выбор валюты</b>

Игрок: <b>{safe(profile.nickname)}</b>

Выбери кошелёк для пополнения или списания.
""".strip()


def build_admin_wallet_action_text(profile: WalletUserProfile, currency: WalletCurrency) -> str:
    return f"""
<b>{currency.icon} {safe(currency.name)}</b>

Игрок: <b>{safe(profile.nickname)}</b>

Выбери действие.
""".strip()


def build_admin_wallet_amount_text(profile: WalletUserProfile, currency: WalletCurrency, action: str) -> str:
    action_title = "➕ Начисление" if action == "add" else "➖ Списание"

    return ADMIN_WALLETS_AMOUNT_TEXT.format(
        action_title=action_title,
        nickname=safe(profile.nickname),
        currency_title=f"{currency.icon} {safe(currency.name)}",
    )


def build_admin_wallet_success_text(result: WalletOperationResult) -> str:
    action_line = "начислено" if result.action == "add" else "списано"

    return f"""
<b>✅ Баланс обновлён</b>

Игрок: <b>{safe(result.profile.nickname)}</b>
Валюта: <b>{result.currency.icon} {safe(result.currency.name)}</b>
{action_line.capitalize()}: <b>{result.amount:,}</b>

<b>💰 Текущий баланс</b>
{format_balances(result.profile)}
""".replace(",", " ").strip()
