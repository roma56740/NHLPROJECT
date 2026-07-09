from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


SETTING_KEYS = [
    ("maintenance_mode", "🛠 Режим обслуживания"),
    ("season_key", "🎮 Текущий сезон"),
    ("win_coins_reward", "🏆 Coins за победу"),
    ("loss_coins_reward", "💔 Coins за поражение"),
    ("bot_handicap_extra", "🤖 Ослабление ботов"),
    ("matchmaking_min_wait_seconds", "⏱ Минимум поиска"),
    ("matchmaking_max_wait_seconds", "⏱ Максимум поиска"),
    ("start_coins", "🪙 Стартовые Coins"),
    ("start_energy", "💵 Стартовые Рубли"),
    ("start_rank_points", "🏅 Стартовые Rank-point"),
    ("free_card_cooldown_hours", "🎁 Кулдаун бесплатной карты"),
    ("creator_weekly_rewards_enabled", "⭐ Недельные креаторы"),
    ("creator_weekly_rewards_interval_hours", "⭐ Интервал креаторов"),
    ("asset_warning_enabled", "⚠️ Предупреждения картинок"),
    ("asset_warning_interval_hours", "⚠️ Интервал предупреждений"),
    ("subscription_required_enabled", "📢 Обязательная подписка"),
    ("subscription_channel_id", "📢 Канал подписки"),
    ("subscription_channel_url", "🔗 Ссылка на канал"),
    ("start_banner_path", "🖼 Стартовая картинка"),
    ("pack_animation_step_delay_ms", "✨ Скорость анимации"),
]


def build_admin_settings_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for key, title in SETTING_KEYS:
        if key == "maintenance_mode":
            rows.append([InlineKeyboardButton(text=title, callback_data="admin_settings:toggle_maintenance")])
        else:
            rows.append([InlineKeyboardButton(text=title, callback_data=f"admin_settings:edit:{key}")])

    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_settings:main")])
    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_settings_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_settings:main")],
        ]
    )
