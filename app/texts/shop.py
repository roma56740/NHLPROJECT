from html import escape

from app.services.shop import ShopHistoryPage, ShopPackItem, ShopPacksPage, ShopPurchaseResult


SHOP_MAIN_TEXT = """
<b>🛒 Магазин</b>

Здесь можно купить паки за игровые валюты и сразу добавить их в коллекцию.

Выбери раздел ниже.
""".strip()


def safe(value: object | None) -> str:
    if value is None:
        return "не указано"

    text = str(value).strip()

    if not text:
        return "не указано"

    return escape(text, quote=False)


def build_shop_price_text(pack: ShopPackItem | ShopPurchaseResult) -> str:
    amount = int(pack.price_amount or 0)
    currency_code = pack.price_currency_code

    if amount <= 0 or currency_code is None:
        return "бесплатно"

    icon = pack.price_currency_icon or "💠"
    name = pack.price_currency_name or currency_code
    return f"{amount:,} {icon} {safe(name)}".replace(",", " ")


def build_shop_packs_page_text(page: ShopPacksPage) -> str:
    if page.total_count == 0:
        return """
<b>🛒 Магазин</b>

Витрина пока пустая.

Скоро здесь появятся паки, события и специальные предложения.
""".strip()

    return f"""
<b>🛒 Магазин паков</b>

Доступно предложений: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

Выбери пак, чтобы посмотреть обложку, цену и награды.
""".strip()


def build_shop_pack_profile_text(pack: ShopPackItem) -> str:
    selected_note = "✅ Награды готовы" if pack.selected_cards_count > 0 else "⏳ Награды скоро появятся"

    return f"""
<b>🎁 {safe(pack.name)}</b>

{safe(pack.description)}

🃏 Карточек внутри: <b>{pack.cards_count}</b>
🏒 Карт в розыгрыше: <b>{pack.selected_cards_count}</b>
🎒 Уже в инвентаре: <b>{pack.user_quantity}</b>
💰 Цена: <b>{build_shop_price_text(pack)}</b>

{selected_note}
""".strip()


def build_shop_confirm_text(pack: ShopPackItem) -> str:
    return f"""
<b>🛒 Подтверждение покупки</b>

🎁 Пак: <b>{safe(pack.name)}</b>
💰 Цена: <b>{build_shop_price_text(pack)}</b>

После покупки пак появится в разделе 🎁 Паки.
""".strip()


def build_shop_purchase_success_text(result: ShopPurchaseResult) -> str:
    balance_line = ""

    if result.balance_after is not None:
        icon = result.price_currency_icon or "💠"
        name = result.price_currency_name or result.price_currency_code or "валюта"
        balance_line = f"\n💼 Остаток: <b>{result.balance_after:,}</b> {icon} {safe(name)}".replace(",", " ")

    return f"""
<b>✅ Покупка готова</b>

🎁 Пак: <b>{safe(result.pack_name)}</b>
💰 Цена: <b>{build_shop_price_text(result)}</b>{balance_line}

Пак уже добавлен в раздел 🎁 Паки.
""".strip()


def build_shop_purchase_error_text(error: str) -> str:
    return f"""
<b>🛒 Покупка не выполнена</b>

{safe(error)}
""".strip()


def build_shop_history_text(page: ShopHistoryPage) -> str:
    if page.total_count == 0:
        return """
<b>📜 История покупок</b>

Покупок пока нет.
""".strip()

    lines = []

    for item in page.purchases:
        if item.amount <= 0 or item.currency_code is None:
            price = "бесплатно"
        else:
            icon = item.currency_icon or "💠"
            name = item.currency_name or item.currency_code
            price = f"{item.amount:,} {icon} {safe(name)}".replace(",", " ")

        lines.append(f"🎁 <b>{safe(item.pack_name)}</b>\n💰 {price}\n🕒 {safe(item.created_at)}")

    return f"""
<b>📜 История покупок</b>

Всего покупок: <b>{page.total_count}</b>
Страница: <b>{page.page}/{page.pages_count}</b>

{chr(10).join(lines)}
""".strip()
