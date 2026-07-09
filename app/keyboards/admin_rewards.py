from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_admin_rewards_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Награды за матчи", callback_data="admin_settings:main")],
        [InlineKeyboardButton(text="📅 Ежедневный вход", callback_data="admin_daily:main")],
        [InlineKeyboardButton(text="🔄 Награды сезона", callback_data="season:tiers")],
        [InlineKeyboardButton(text="🏆 Награды кланового сезона", callback_data="clan_season:main")],
        [InlineKeyboardButton(text="⭐ Награды креаторов", callback_data="admin_creators:settings")],
        [InlineKeyboardButton(text="🎯 Квесты", callback_data="admin_quests:main")],
        [InlineKeyboardButton(text="🎪 События", callback_data="admin_events:main")],
        [InlineKeyboardButton(text="🎟 Hockey Pass", callback_data="admin_hpass:main")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
    ])
