from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.shop import ShopPackItem, ShopPurchaseItem
from app.texts.shop import build_shop_price_text


SHOP_PACKS_PER_PAGE = 5
SHOP_HISTORY_PER_PAGE = 5


def build_shop_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Паки в магазине", callback_data="shop:packs:1")],
            [InlineKeyboardButton(text="💵 Купить Рубли", callback_data="shop:buy_rubles")],
            [InlineKeyboardButton(text="📜 История покупок", callback_data="shop:history:1")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def build_shop_pack_list_keyboard(packs: list[ShopPackItem], page: int, pages_count: int) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for pack in packs:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🎁 {pack.name} · {build_shop_price_text(pack)}",
                    callback_data=f"shop:view:{pack.id}:{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"shop:packs:{page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="shop:page_info"))

    if page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"shop:packs:{page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="📜 История покупок", callback_data="shop:history:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_shop_pack_profile_keyboard(pack_id: int, page: int, can_buy: bool = True) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    if can_buy:
        keyboard.append([InlineKeyboardButton(text="🛒 Купить пак", callback_data=f"shop:confirm:{pack_id}:{page}")])

    keyboard.append([InlineKeyboardButton(text="🎁 К магазину", callback_data=f"shop:packs:{page}")])
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_shop_confirm_keyboard(pack_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить покупку", callback_data=f"shop:buy:{pack_id}:{page}")],
            [InlineKeyboardButton(text="⬅️ Назад к паку", callback_data=f"shop:view:{pack_id}:{page}")],
        ]
    )


def build_shop_purchase_result_keyboard(pack_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Открыть мои паки", callback_data="packs:inventory:1")],
            [InlineKeyboardButton(text="🛒 Вернуться в магазин", callback_data="shop:packs:1")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def build_shop_history_keyboard(purchases: list[ShopPurchaseItem], page: int, pages_count: int) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []

    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"shop:history:{page - 1}"))

    navigation.append(InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data="shop:page_info"))

    if page < pages_count:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"shop:history:{page + 1}"))

    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton(text="🎁 Паки в магазине", callback_data="shop:packs:1")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
