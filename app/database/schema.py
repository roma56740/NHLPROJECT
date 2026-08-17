

CREATE_GAME_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS game_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SECURITY_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS security_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    telegram_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
"""

CREATE_GAME_SETTINGS_UPDATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_game_settings_updated_at ON game_settings(updated_at);
"""

CREATE_SECURITY_LOGS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_security_logs_user_id ON security_logs(user_id);
"""

CREATE_SECURITY_LOGS_CREATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_security_logs_created_at ON security_logs(created_at);
"""

DEFAULT_GAME_SETTINGS = [
    {
        "key": "maintenance_mode",
        "value": "0",
        "title": "Режим обслуживания",
        "description": "Если включён, игроки временно не смогут пользоваться ботом.",
    },
    {
        "key": "maintenance_message_text",
        "value": "",
        "title": "Технический перерыв: текст",
        "description": "Текст, который видят обычные пользователи во время технического перерыва.",
    },
    {
        "key": "maintenance_photo_file_id",
        "value": "",
        "title": "Технический перерыв: фото file_id",
        "description": "Telegram file_id фотографии технического перерыва.",
    },
    {
        "key": "maintenance_photo_file_unique_id",
        "value": "",
        "title": "Технический перерыв: фото file_unique_id",
        "description": "Telegram file_unique_id фотографии технического перерыва.",
    },
    {
        "key": "maintenance_enabled_at",
        "value": "",
        "title": "Технический перерыв: включён когда",
        "description": "Время последнего включения технического перерыва.",
    },
    {
        "key": "maintenance_enabled_by",
        "value": "",
        "title": "Технический перерыв: включил кто",
        "description": "Telegram ID администратора, включившего технический перерыв последним.",
    },
    {
        "key": "maintenance_disabled_at",
        "value": "",
        "title": "Технический перерыв: выключен когда",
        "description": "Время последнего выключения технического перерыва.",
    },
    {
        "key": "maintenance_disabled_by",
        "value": "",
        "title": "Технический перерыв: выключил кто",
        "description": "Telegram ID администратора, выключившего технический перерыв последним.",
    },
    {
        "key": "maintenance_text_updated_by",
        "value": "",
        "title": "Технический перерыв: текст изменил кто",
        "description": "Telegram ID администратора, последним менявшего текст технического перерыва.",
    },
    {
        "key": "maintenance_photo_updated_by",
        "value": "",
        "title": "Технический перерыв: фото изменил кто",
        "description": "Telegram ID администратора, последним менявшего фото технического перерыва.",
    },
    {
        "key": "season_key",
        "value": "season-1",
        "title": "Текущий сезон",
        "description": "Название текущего игрового сезона.",
    },
    {
        "key": "win_coins_reward",
        "value": "100",
        "title": "Награда за победу",
        "description": "Количество Coins за победу в матче.",
    },
    {
        "key": "matchmaking_min_wait_seconds",
        "value": "90",
        "title": "Минимальное ожидание соперника",
        "description": "Через сколько секунд минимум бот может подобрать команду-соперника.",
    },
    {
        "key": "matchmaking_max_wait_seconds",
        "value": "110",
        "title": "Максимальное ожидание соперника",
        "description": "Через сколько секунд максимум бот может подобрать команду-соперника.",
    },
    {
        "key": "start_coins",
        "value": "0",
        "title": "Стартовые Coins",
        "description": "Coins для нового игрока.",
    },
    {
        "key": "start_energy",
        "value": "0",
        "title": "Стартовые Рубли",
        "description": "Рубли для нового игрока.",
    },
    {
        "key": "start_rank_points",
        "value": "0",
        "title": "Стартовые Rank-point",
        "description": "Rank-point для нового игрока.",
    },
    {
        "key": "free_card_collection_code",
        "value": "free-cards",
        "title": "Коллекция бесплатной карточки",
        "description": "Из этой коллекции игроки получают бесплатную карточку раз в 6 часов.",
    },
    {
        "key": "free_card_collection_codes",
        "value": "free-cards",
        "title": "Коллекции бесплатной карточки",
        "description": "Список кодов коллекций через запятую. Бесплатная карточка выбирается случайно из всех указанных активных коллекций.",
    },
    {
        "key": "clan_war_defense_win_power",
        "value": "1",
        "title": "Сила победы защиты арены",
        "description": "На сколько очков победа клана-владельца уменьшает активную атаку на его арену.",
    },
    {
        "key": "clan_war_capture_shield_hours",
        "value": "6",
        "title": "Щит после захвата арены",
        "description": "Сколько часов арену нельзя атаковать после захвата. Защищает от мгновенного перезахвата.",
    },
    {
        "key": "clan_war_max_owned_arenas",
        "value": "3",
        "title": "Максимум арен у клана",
        "description": "Сколько арен один клан может держать одновременно. 0 — без лимита.",
    },
    {
        "key": "clan_war_same_arena_cooldown_hours",
        "value": "24",
        "title": "КД на повторный захват арены",
        "description": "Сколько часов старый владелец не может атаковать эту же арену после потери.",
    },
    {
        "key": "clan_war_leader_capture_extra_wins",
        "value": "2",
        "title": "Анти-лидер: доп. победы",
        "description": "Сколько дополнительных побед нужно клану, который уже держит арены. Применяется за каждую арену клана.",
    },
    {
        "key": "clan_season_reset_password",
        "value": "Ihbsn_3141592",
        "title": "Пароль сброса кланового сезона",
        "description": "Отдельный пароль главного админа для сброса кланового сезона.",
    },
    {
        "key": "free_card_cooldown_hours",
        "value": "6",
        "title": "Ожидание бесплатной карточки",
        "description": "Через сколько часов игрок сможет забрать новую бесплатную карточку.",
    },
    {
        "key": "loss_coins_reward",
        "value": "250",
        "title": "Награда за поражение",
        "description": "Количество Coins за поражение в матче (0 — не начислять).",
    },
    {
        "key": "bot_handicap_extra",
        "value": "0",
        "title": "Ослабление ботов",
        "description": "На сколько дополнительно снизить OVR ботов (0-20). Больше значение — слабее боты.",
    },
    {
        "key": "creator_chat_invite_link",
        "value": "",
        "title": "Ссылка на чат креаторов",
        "description": "Ссылка автоматически отправляется игроку после назначения официальным креатором.",
    },
    {
        "key": "creator_weekly_rewards_enabled",
        "value": "1",
        "title": "Авто-недельные бонусы креаторов",
        "description": "1 — автоматически начислять недельные бонусы креаторов в банк выдачи.",
    },
    {
        "key": "creator_weekly_rewards_interval_hours",
        "value": "168",
        "title": "Интервал недельных бонусов креаторов",
        "description": "Через сколько часов автоматически начислять недельные бонусы креаторам.",
    },
    {
        "key": "creator_weekly_last_paid_at",
        "value": "",
        "title": "Последняя авто-выплата креаторов",
        "description": "Служебная дата последнего автоматического начисления недельных бонусов.",
    },
    {
        "key": "asset_warning_enabled",
        "value": "1",
        "title": "Авто-предупреждения по картинкам",
        "description": "1 — каждые 2 часа отправлять админам список недостающих картинок и данных.",
    },
    {
        "key": "asset_warning_interval_hours",
        "value": "2",
        "title": "Интервал предупреждений по картинкам",
        "description": "Через сколько часов повторять предупреждение администраторам.",
    },
    {
        "key": "asset_warning_last_sent_at",
        "value": "",
        "title": "Последнее предупреждение по картинкам",
        "description": "Служебная дата последней рассылки предупреждения о недостающих данных.",
    },
    {
        "key": "subscription_required_enabled",
        "value": "0",
        "title": "Обязательная подписка",
        "description": "1 — игроки смогут пользоваться ботом только после подписки на Telegram-канал.",
    },
    {
        "key": "subscription_channel_id",
        "value": "",
        "title": "Канал обязательной подписки",
        "description": "Username канала (@channel или t.me/channel) либо числовой ID -100... . Бот должен быть добавлен в канал администратором.",
    },
    {
        "key": "subscription_channel_url",
        "value": "",
        "title": "Ссылка на канал подписки",
        "description": "Ссылка для кнопки подписки. Если оставить пустой и канал указан как @username, ссылка соберётся автоматически.",
    },
    {
        "key": "start_banner_path",
        "value": "assets/visual/start_banner.jpeg",
        "title": "Картинка стартового сообщения",
        "description": "Путь к картинке, которая отправляется вместе со стартовым сообщением /start.",
    },
    {
        "key": "pack_animation_enabled",
        "value": "1",
        "title": "Анимация открытия паков",
        "description": "1 — показывать этапы дивизион → команда → страна → карточка.",
    },
    {
        "key": "ranked_shootout_chance_percent",
        "value": "20",
        "title": "Ranked: шанс серии буллитов, %",
        "description": "Вероятность принудительной ничьей после трёх периодов и запуска интерактивной серии буллитов.",
    },
    {
        "key": "pack_animation_step_delay_ms",
        "value": "900",
        "title": "Пауза между этапами анимации",
        "description": "Задержка между сообщениями анимации открытия пака в миллисекундах.",
    },
    {
        "key": "war2_daily_tickets",
        "value": "5",
        "title": "CLAN WAR 2.0: билетов в день",
        "description": "Сколько матчей CLAN WAR 2.0 игрок может сыграть за день (сброс в 00:00 UTC).",
    },
    {
        "key": "war2_season_length_days",
        "value": "28",
        "title": "CLAN WAR 2.0: длительность сезона (дней)",
        "description": "Длительность одного сезона CLAN WAR 2.0 в днях (по умолчанию 4 недели).",
    },
    {
        "key": "war2_salary_cap",
        "value": "50000",
        "title": "CLAN WAR 2.0: лимит зарплат (SALARY_WAR)",
        "description": "Лимит суммарной зарплаты состава в режиме SALARY_WAR (в тех же единицах, что и зарплаты карт).",
    },
    {
        "key": "war2_bot_fallback_rating_spread",
        "value": "150",
        "title": "CLAN WAR 2.0: разброс рейтинга для подбора соперника",
        "description": "Если среди других кланов нет соперника — подставляется бот-соперник.",
    },
    {
        "key": "war2_roster_size",
        "value": "5",
        "title": "CLAN WAR 2.0: размер ростера клана",
        "description": "Сколько игроков клана могут быть в ростере CLAN WAR 2.0 (участвовать в матчах).",
    },
    {
        "key": "ranked_season_length_days",
        "value": "56",
        "title": "RANKED MODE: длительность сезона (дней)",
        "description": "Длительность одного Ranked-сезона в днях (по умолчанию 56, отдельно от других сезонов).",
    },
    {
        "key": "ranked_xp_per_match",
        "value": "20",
        "title": "RANKED MODE: XP за матч",
        "description": "Ranked Pass XP за каждый сыгранный Ranked-матч (независимо от результата).",
    },
    {
        "key": "ranked_xp_win_bonus",
        "value": "30",
        "title": "RANKED MODE: бонус XP за победу",
        "description": "Дополнительный Ranked Pass XP за победу в Ranked-матче (сверх ranked_xp_per_match).",
    },
    {
        "key": "ranked_xp_division_up_bonus",
        "value": "150",
        "title": "RANKED MODE: бонус XP за новую лигу",
        "description": "Единоразовый бонус Ranked Pass XP за первое достижение новой лиги (дивизиона) за сезон.",
    },
    {
        "key": "render_menu_background_path",
        "value": "",
        "title": "Рендер: сезонный фон главного меню",
        "description": "Фон серверного рендера меню. Персональный купленный фон игрока имеет приоритет.",
    },
    {
        "key": "render_menu_video_path",
        "value": "",
        "title": "Рендер: сезонное видео главного меню",
        "description": "MP4-loop главного меню. Используется, если у игрока не установлен персональный фон.",
    },
    {
        "key": "render_menu_title",
        "value": "NHL CARD LEAGUE",
        "title": "Рендер: заголовок меню",
        "description": "Сезонный заголовок главного меню. Логотип поверх меню не используется.",
    },
    {
        "key": "render_menu_subtitle",
        "value": "SEASON 1",
        "title": "Рендер: подзаголовок меню",
        "description": "Сезонный подзаголовок главного меню.",
    },
    {
        "key": "render_menu_accent",
        "value": "#4CB8FF",
        "title": "Рендер: цвет меню",
        "description": "HEX accent главного меню.",
    },
    {
        "key": "render_lineup_background_path",
        "value": "assets/visual/lineup_match_bg.png",
        "title": "Рендер: дефолтный фон состава",
        "description": "Фон состава по умолчанию. Персональный купленный фон игрока имеет приоритет.",
    },
    {
        "key": "render_lineup_accent",
        "value": "#4CB8FF",
        "title": "Рендер: цвет состава",
        "description": "HEX accent HUD, слотов и линий состава.",
    },
    {
        "key": "render_lineup_chemistry_enabled",
        "value": "1",
        "title": "Рендер: линии химии",
        "description": "1 — показывать визуальные связи химии между картами состава.",
    },
]


DEFAULT_CREATOR_LEVEL_SETTINGS = [
    {
        "level": 1,
        "required_subscribers": 30,
        "required_distributed_value": 0,
        "welcome_coins": 250000,
        "weekly_coins": 100000,
        "weekly_elite_packs": 1,
        "weekly_legendary_packs": 0,
        "weekly_elite_pack_id": None,
        "weekly_legendary_pack_id": None,
        "promo_codes_weekly": 0,
        "author_code_percent_bp": 0,
        "exclusive_card_rating": 0,
        "perks_text": "Закрытый чат креаторов.",
        "personal_rewards_text": "Приоритет в списке официальных креаторов; отдельная отметка в розыгрышах.",
    },
    {
        "level": 2,
        "required_subscribers": 100,
        "required_distributed_value": 500000,
        "welcome_coins": 500000,
        "weekly_coins": 250000,
        "weekly_elite_packs": 1,
        "weekly_legendary_packs": 0,
        "weekly_elite_pack_id": None,
        "weekly_legendary_pack_id": None,
        "promo_codes_weekly": 3,
        "author_code_percent_bp": 0,
        "exclusive_card_rating": 0,
        "perks_text": "Тег CREATOR в общем чате; возможность создать 3 промокода в неделю.",
        "personal_rewards_text": "Ранний доступ к новым ивентам; отдельный бейдж в списке креаторов.",
    },
    {
        "level": 3,
        "required_subscribers": 200,
        "required_distributed_value": 2000000,
        "welcome_coins": 750000,
        "weekly_coins": 350000,
        "weekly_elite_packs": 0,
        "weekly_legendary_packs": 1,
        "weekly_elite_pack_id": None,
        "weekly_legendary_pack_id": None,
        "promo_codes_weekly": 5,
        "author_code_percent_bp": 0,
        "exclusive_card_rating": 0,
        "perks_text": "5 промокодов в неделю; пометка креатора в профиле игры.",
        "personal_rewards_text": "Личная витрина розыгрышей; приоритет на тест новых механик.",
    },
    {
        "level": 4,
        "required_subscribers": 300,
        "required_distributed_value": 4000000,
        "welcome_coins": 1000000,
        "weekly_coins": 400000,
        "weekly_elite_packs": 0,
        "weekly_legendary_packs": 3,
        "weekly_elite_pack_id": None,
        "weekly_legendary_pack_id": None,
        "promo_codes_weekly": 5,
        "author_code_percent_bp": 150,
        "exclusive_card_rating": 0,
        "perks_text": "Личный код автора: 1.5% с покупок пользователей, у которых введён код автора.",
        "personal_rewards_text": "Возможность запускать брендированный мини-ивент; отдельный приоритет в промо.",
    },
    {
        "level": 5,
        "required_subscribers": 400,
        "required_distributed_value": 10000000,
        "welcome_coins": 2000000,
        "weekly_coins": 500000,
        "weekly_elite_packs": 0,
        "weekly_legendary_packs": 5,
        "weekly_elite_pack_id": None,
        "weekly_legendary_pack_id": None,
        "promo_codes_weekly": 5,
        "author_code_percent_bp": 150,
        "exclusive_card_rating": 99,
        "perks_text": "Возможность заказать эксклюзивную карту 99 OVR на любого незанятого игрока.",
        "personal_rewards_text": "Именной сезонный квест; персональный дизайн эксклюзивной карты; отдельная роль топ-креатора.",
    },
]


CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    nickname TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'player',
    league TEXT NOT NULL DEFAULT 'NCAA',
    rating_points INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    matches_played INTEGER NOT NULL DEFAULT 0,
    goals_scored INTEGER NOT NULL DEFAULT 0,
    goals_allowed INTEGER NOT NULL DEFAULT 0,
    bp_points INTEGER NOT NULL DEFAULT 0,
    hockey_pass_level INTEGER NOT NULL DEFAULT 1,
    premium_pass INTEGER NOT NULL DEFAULT 0,
    team_name TEXT,
    team_country TEXT,
    team_logo_path TEXT,
    is_banned INTEGER NOT NULL DEFAULT 0,
    trade_blocked INTEGER NOT NULL DEFAULT 0,
    privacy_public_cards INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


CREATE_BOT_ADMINS_TABLE = """
CREATE TABLE IF NOT EXISTS bot_admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    added_by_telegram_id INTEGER,
    role TEXT NOT NULL DEFAULT 'senior_admin',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_CURRENCIES_TABLE = """
CREATE TABLE IF NOT EXISTS currencies (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_CURRENCY_BALANCES_TABLE = """
CREATE TABLE IF NOT EXISTS currency_balances (
    user_id INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, currency_code),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE CASCADE
);
"""

CREATE_COLLECTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    player_key TEXT NOT NULL,
    position TEXT NOT NULL CHECK(position IN ('G', 'D', 'F')),
    overall INTEGER NOT NULL CHECK(overall BETWEEN 1 AND 110),
    team TEXT NOT NULL,
    country TEXT NOT NULL,
    collection_id INTEGER NOT NULL,
    rarity TEXT NOT NULL CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')),
    image_path TEXT NOT NULL,
    salary INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE RESTRICT
);
"""

CREATE_USER_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS user_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    is_in_lineup INTEGER NOT NULL DEFAULT 0,
    lineup_slot TEXT,
    trade_locked INTEGER NOT NULL DEFAULT 0,
    lock_reason TEXT,
    lock_until TEXT,
    obtained_from TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE RESTRICT
);
"""

CREATE_INVENTORY_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    stackable INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_USER_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS user_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, item_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES inventory_items(id) ON DELETE RESTRICT
);
"""

CREATE_USER_ITEMS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_items_user ON user_items(user_id, item_id);
"""

CREATE_DNA_WELCOME_GRANTS_TABLE = """
CREATE TABLE IF NOT EXISTS dna_welcome_grants (
    user_id INTEGER PRIMARY KEY,
    collectible_amount INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_DNA_EXTRACTION_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS dna_extraction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    recipe_code TEXT NOT NULL,
    collectible_amount INTEGER NOT NULL,
    consumed_user_card_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_DNA_EXTRACTION_LOGS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_dna_extraction_logs_user ON dna_extraction_logs(user_id, created_at);
"""

CREATE_DNA_CHOICE_CLAIMS_TABLE = """
CREATE TABLE IF NOT EXISTS dna_choice_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    card_id INTEGER NOT NULL,
    user_card_id INTEGER,
    collectible_cost INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE SET NULL
);
"""

CREATE_DNA_CRAFT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS dna_craft_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    target_card_id INTEGER NOT NULL,
    target_user_card_id INTEGER,
    target_overall INTEGER NOT NULL CHECK(target_overall IN (93, 95, 98, 100)),
    target_surname TEXT NOT NULL,
    consumed_user_card_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (target_card_id) REFERENCES cards(id) ON DELETE RESTRICT,
    FOREIGN KEY (target_user_card_id) REFERENCES user_cards(id) ON DELETE SET NULL
);
"""

CREATE_DNA_CRAFT_LOGS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_dna_craft_logs_user ON dna_craft_logs(user_id, created_at);
"""

CREATE_PACKS_TABLE = """
CREATE TABLE IF NOT EXISTS packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    animation_video_path TEXT,
    price_currency_code TEXT,
    price_amount INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    is_shop_available INTEGER NOT NULL DEFAULT 0,
    is_starter INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (price_currency_code) REFERENCES currencies(code) ON DELETE SET NULL
);
"""

CREATE_PACK_SLOTS_TABLE = """
CREATE TABLE IF NOT EXISTS pack_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    slot_number INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    collection_id INTEGER,
    position TEXT CHECK(position IN ('G', 'D', 'F') OR position IS NULL),
    rarity TEXT CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon') OR rarity IS NULL),
    rarity_chances TEXT,
    min_overall INTEGER,
    max_overall INTEGER,
    special_collection_id INTEGER,
    special_image_hint TEXT,
    special_chance_percent INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL,
    FOREIGN KEY (special_collection_id) REFERENCES collections(id) ON DELETE SET NULL
);
"""
CREATE_PACK_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS pack_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pack_id, card_id),
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);
"""


CREATE_USER_PACKS_TABLE = """
CREATE TABLE IF NOT EXISTS user_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, pack_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE RESTRICT
);
"""

CREATE_PACK_OPENINGS_TABLE = """
CREATE TABLE IF NOT EXISTS pack_openings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'inventory',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE RESTRICT
);
"""

CREATE_PACK_OPENING_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS pack_opening_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opening_id INTEGER NOT NULL,
    user_card_id INTEGER,
    card_id INTEGER,
    reward_type TEXT NOT NULL DEFAULT 'card',
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (opening_id) REFERENCES pack_openings(id) ON DELETE CASCADE,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE SET NULL,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE SET NULL
);
"""

CREATE_PACK_PENDING_REVEALS_TABLE = """
CREATE TABLE IF NOT EXISTS pack_pending_reveals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opening_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    reward_snapshot TEXT NOT NULL,
    chat_id INTEGER,
    message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reveal_at TEXT,
    completed_at TEXT,
    error TEXT,
    FOREIGN KEY (opening_id) REFERENCES pack_openings(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE CASCADE
);
"""
CREATE_PACK_PENDING_REVEALS_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_pending_reveals_status ON pack_pending_reveals(status);
"""

CREATE_SHOP_PURCHASES_TABLE = """
CREATE TABLE IF NOT EXISTS shop_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL,
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE RESTRICT,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL
);
"""

CREATE_MATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    opponent_user_id INTEGER,
    opponent_name TEXT NOT NULL,
    opponent_type TEXT NOT NULL DEFAULT 'bot',
    user_lineup_ovr INTEGER NOT NULL DEFAULT 0,
    opponent_lineup_ovr INTEGER NOT NULL DEFAULT 0,
    user_score INTEGER NOT NULL DEFAULT 0,
    opponent_score INTEGER NOT NULL DEFAULT 0,
    result TEXT NOT NULL CHECK(result IN ('win', 'loss')),
    rating_delta INTEGER NOT NULL DEFAULT 0,
    coins_reward INTEGER NOT NULL DEFAULT 0,
    rank_points_reward INTEGER NOT NULL DEFAULT 0,
    league_before TEXT NOT NULL DEFAULT 'NCAA',
    league_after TEXT NOT NULL DEFAULT 'NCAA',
    is_overtime INTEGER NOT NULL DEFAULT 0,
    is_shootout INTEGER NOT NULL DEFAULT 0,
    mvp_title TEXT NOT NULL DEFAULT '',
    periods_summary TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (opponent_user_id) REFERENCES users(id) ON DELETE SET NULL
);
"""

CREATE_MATCH_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS match_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    period_title TEXT NOT NULL,
    time_text TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);
"""

CREATE_MATCH_QUEUE_TABLE = """
CREATE TABLE IF NOT EXISTS match_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    telegram_id INTEGER NOT NULL UNIQUE,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    nickname TEXT NOT NULL,
    league TEXT NOT NULL DEFAULT 'NCAA',
    rating_points INTEGER NOT NULL DEFAULT 0,
    lineup_ovr INTEGER NOT NULL DEFAULT 0,
    bot_fallback_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_QUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    period_type TEXT NOT NULL CHECK(period_type IN ('daily', 'seasonal')),
    target_type TEXT NOT NULL CHECK(target_type IN ('matches_played', 'matches_won', 'goals_scored', 'shutout_wins')),
    target_value INTEGER NOT NULL DEFAULT 1,
    bp_reward INTEGER NOT NULL DEFAULT 0,
    coins_reward INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_USER_QUEST_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS user_quest_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    quest_id INTEGER NOT NULL,
    period_key TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    reward_claimed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, quest_id, period_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (quest_id) REFERENCES quests(id) ON DELETE CASCADE
);
"""




CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    target_type TEXT NOT NULL CHECK(target_type IN ('matches_played', 'matches_won', 'goals_scored', 'shutout_wins')),
    target_value INTEGER NOT NULL DEFAULT 1,
    reward_type TEXT NOT NULL CHECK(reward_type IN ('currency', 'pack', 'card')),
    reward_currency_code TEXT,
    reward_amount INTEGER NOT NULL DEFAULT 1,
    reward_pack_id INTEGER,
    reward_card_id INTEGER,
    start_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    announcement_sent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reward_currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (reward_pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (reward_card_id) REFERENCES cards(id) ON DELETE SET NULL
);
"""

CREATE_USER_EVENT_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS user_event_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    reward_claimed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
"""

CREATE_USER_EVENT_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS user_event_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    reward_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
"""

CREATE_HOCKEY_PASSES_TABLE = """
CREATE TABLE IF NOT EXISTS hockey_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    premium_currency_code TEXT,
    premium_price_amount INTEGER NOT NULL DEFAULT 0,
    levels_count INTEGER NOT NULL DEFAULT 40,
    points_per_level INTEGER NOT NULL DEFAULT 5,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (premium_currency_code) REFERENCES currencies(code) ON DELETE SET NULL
);
"""

CREATE_HOCKEY_PASS_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS hockey_pass_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pass_id INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 40),
    track TEXT NOT NULL CHECK(track IN ('free', 'premium')),
    reward_type TEXT NOT NULL CHECK(reward_type IN ('currency', 'pack', 'card')),
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    card_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pass_id) REFERENCES hockey_passes(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE SET NULL
);
"""

CREATE_USER_HOCKEY_PASSES_TABLE = """
CREATE TABLE IF NOT EXISTS user_hockey_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pass_id INTEGER NOT NULL,
    premium_unlocked INTEGER NOT NULL DEFAULT 0,
    purchased_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, pass_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pass_id) REFERENCES hockey_passes(id) ON DELETE CASCADE
);
"""

CREATE_USER_HOCKEY_PASS_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS user_hockey_pass_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reward_id INTEGER NOT NULL,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, reward_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (reward_id) REFERENCES hockey_pass_rewards(id) ON DELETE CASCADE
);
"""

CREATE_FREE_CARD_CLAIMS_TABLE = """
CREATE TABLE IF NOT EXISTS free_card_claims (
    user_id INTEGER PRIMARY KEY,
    last_claimed_at TEXT,
    last_notified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


CREATE_STARTER_KIT_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS starter_kit_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_code TEXT NOT NULL UNIQUE CHECK(slot_code IN ('G', 'D1', 'D2', 'F1', 'F2', 'F3')),
    card_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);
"""



CREATE_CLANS_TABLE = """
CREATE TABLE IF NOT EXISTS clans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    emblem_path TEXT,
    rating_points INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);
"""


CREATE_CLAN_MEMBERS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK(role IN ('leader', 'officer', 'member')) DEFAULT 'member',
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_TRADE_OFFERS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_user_id INTEGER NOT NULL,
    target_user_id INTEGER,
    wanted_type TEXT NOT NULL CHECK(wanted_type IN ('cards', 'currency')),
    wanted_currency_code TEXT,
    wanted_currency_amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('open', 'accepted', 'cancelled')) DEFAULT 'open',
    accepted_by_user_id INTEGER,
    accepted_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creator_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (accepted_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (wanted_currency_code) REFERENCES currencies(code) ON DELETE SET NULL
);
"""

CREATE_TRADE_OFFER_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_offer_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER NOT NULL,
    user_card_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(offer_id, user_card_id),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE CASCADE
);
"""

CREATE_TRADE_OFFER_WANTED_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_offer_wanted_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(offer_id, card_id),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);
"""

CREATE_TRADE_OFFER_COSMETICS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_offer_cosmetics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER NOT NULL,
    user_cosmetic_item_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(offer_id, user_cosmetic_item_id),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (user_cosmetic_item_id) REFERENCES user_cosmetic_items(id) ON DELETE CASCADE
);
"""

CREATE_TRADE_OFFER_WANTED_COSMETICS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_offer_wanted_cosmetics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER NOT NULL,
    cosmetic_item_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(offer_id, cosmetic_item_id),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (cosmetic_item_id) REFERENCES war2_cosmetic_items(id) ON DELETE CASCADE
);
"""

CREATE_TRADE_OFFER_COSMETICS_OFFER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offer_cosmetics_offer_id ON trade_offer_cosmetics(offer_id);
"""

CREATE_TRADE_OFFER_COSMETICS_ITEM_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offer_cosmetics_item_id ON trade_offer_cosmetics(user_cosmetic_item_id);
"""

CREATE_TRADE_OFFER_WANTED_COSMETICS_OFFER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offer_wanted_cosmetics_offer_id ON trade_offer_wanted_cosmetics(offer_id);
"""

CREATE_USER_CARD_VIEW_PREFERENCES_TABLE = """
CREATE TABLE IF NOT EXISTS user_card_view_preferences (
    user_id INTEGER PRIMARY KEY,
    sort_order TEXT NOT NULL CHECK(sort_order IN ('ovr_desc', 'ovr_asc')) DEFAULT 'ovr_desc',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_CHEMISTRY_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS chemistry_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL CHECK(rule_type IN ('country', 'team', 'collection')),
    value TEXT NOT NULL,
    required_cards INTEGER NOT NULL DEFAULT 3 CHECK(required_cards BETWEEN 2 AND 6),
    bonus_ovr INTEGER NOT NULL DEFAULT 1 CHECK(bonus_ovr BETWEEN 1 AND 5),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""



CREATE_BOT_ADMINS_TELEGRAM_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bot_admins_telegram_id ON bot_admins(telegram_id);
"""

CREATE_BOT_ADMINS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bot_admins_active ON bot_admins(active);
"""

CREATE_USERS_TELEGRAM_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
"""

CREATE_CURRENCY_BALANCES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_currency_balances_user_id ON currency_balances(user_id);
"""

CREATE_CARDS_NAME_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
"""

CREATE_CARDS_PLAYER_KEY_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cards_player_key ON cards(player_key);
"""

CREATE_CARDS_COLLECTION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cards_collection_id ON cards(collection_id);
"""

CREATE_CARDS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cards_active ON cards(active);
"""

CREATE_USER_CARDS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_cards_user_id ON user_cards(user_id);
"""

CREATE_USER_CARDS_CARD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_cards_card_id ON user_cards(card_id);
"""

CREATE_USER_CARDS_LINEUP_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_cards_lineup ON user_cards(user_id, is_in_lineup);
"""

CREATE_USER_CARDS_TRADE_LOCK_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_cards_trade_locked ON user_cards(trade_locked);
"""

CREATE_PACKS_CODE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_packs_code ON packs(code);
"""

CREATE_PACKS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_packs_active ON packs(active);
"""

CREATE_PACK_SLOTS_PACK_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_slots_pack_id ON pack_slots(pack_id);
"""

CREATE_PACK_SLOTS_RARITY_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_slots_rarity ON pack_slots(rarity);
"""

CREATE_PACK_CARDS_PACK_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_cards_pack_id ON pack_cards(pack_id);
"""

CREATE_PACK_CARDS_CARD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_cards_card_id ON pack_cards(card_id);
"""

CREATE_USER_PACKS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_packs_user_id ON user_packs(user_id);
"""

CREATE_PACK_OPENINGS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_openings_user_id ON pack_openings(user_id);
"""

CREATE_PACK_REWARDS_OPENING_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pack_opening_rewards_opening_id ON pack_opening_rewards(opening_id);
"""

CREATE_SHOP_PURCHASES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_shop_purchases_user_id ON shop_purchases(user_id);
"""

CREATE_SHOP_PURCHASES_PACK_INDEX = """
CREATE INDEX IF NOT EXISTS idx_shop_purchases_pack_id ON shop_purchases(pack_id);
"""

CREATE_MATCHES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_matches_user_id ON matches(user_id);
"""

CREATE_MATCHES_CREATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_matches_created_at ON matches(created_at);
"""

CREATE_MATCH_EVENTS_MATCH_INDEX = """
CREATE INDEX IF NOT EXISTS idx_match_events_match_id ON match_events(match_id);
"""

CREATE_MATCH_QUEUE_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_match_queue_user_id ON match_queue(user_id);
"""

CREATE_MATCH_QUEUE_SEARCH_INDEX = """
CREATE INDEX IF NOT EXISTS idx_match_queue_search ON match_queue(league, lineup_ovr, rating_points);
"""



CREATE_EVENTS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_events_active ON events(active, start_at, end_at);
"""

CREATE_EVENTS_TARGET_INDEX = """
CREATE INDEX IF NOT EXISTS idx_events_target ON events(target_type, active);
"""

CREATE_USER_EVENT_PROGRESS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_event_progress_user_id ON user_event_progress(user_id);
"""

CREATE_USER_EVENT_PROGRESS_EVENT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_event_progress_event_id ON user_event_progress(event_id);
"""

CREATE_USER_EVENT_REWARDS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_event_rewards_user_id ON user_event_rewards(user_id);
"""

CREATE_HOCKEY_PASSES_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_hockey_passes_active ON hockey_passes(active, end_at);
"""

CREATE_HOCKEY_PASS_REWARDS_PASS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_hockey_pass_rewards_pass_id ON hockey_pass_rewards(pass_id, level, track);
"""

CREATE_USER_HOCKEY_PASSES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_hockey_passes_user_id ON user_hockey_passes(user_id, pass_id);
"""

CREATE_USER_HOCKEY_PASS_REWARDS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_hockey_pass_rewards_user_id ON user_hockey_pass_rewards(user_id);
"""

CREATE_FREE_CARD_CLAIMS_NOTIFY_INDEX = """
CREATE INDEX IF NOT EXISTS idx_free_card_claims_notify ON free_card_claims(last_claimed_at, last_notified_at);
"""


CREATE_STARTER_KIT_CARDS_CARD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_starter_kit_cards_card_id ON starter_kit_cards(card_id);
"""



CREATE_CLANS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_clans_active ON clans(active, rating_points);
"""

CREATE_CLAN_MEMBERS_CLAN_INDEX = """
CREATE INDEX IF NOT EXISTS idx_clan_members_clan_id ON clan_members(clan_id);
"""

CREATE_TRADE_OFFERS_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offers_status ON trade_offers(status, created_at);
"""

CREATE_TRADE_OFFERS_CREATOR_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offers_creator ON trade_offers(creator_user_id, status);
"""

CREATE_TRADE_OFFERS_TARGET_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offers_target ON trade_offers(target_user_id, status);
"""

CREATE_TRADE_OFFER_CARDS_OFFER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offer_cards_offer_id ON trade_offer_cards(offer_id);
"""

CREATE_TRADE_OFFER_CARDS_CARD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offer_cards_user_card_id ON trade_offer_cards(user_card_id);
"""

CREATE_TRADE_WANTED_CARDS_OFFER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trade_offer_wanted_cards_offer_id ON trade_offer_wanted_cards(offer_id);
"""

CREATE_CHEMISTRY_RULES_TYPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chemistry_rules_type ON chemistry_rules(rule_type, active);
"""

CREATE_CHEMISTRY_RULES_VALUE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chemistry_rules_value ON chemistry_rules(value);
"""


CREATE_QUESTS_PERIOD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_quests_period ON quests(period_type, active);
"""

CREATE_QUESTS_TARGET_INDEX = """
CREATE INDEX IF NOT EXISTS idx_quests_target ON quests(target_type, active);
"""

CREATE_USER_QUEST_PROGRESS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_quest_progress_user_id ON user_quest_progress(user_id);
"""

CREATE_USER_QUEST_PROGRESS_PERIOD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_quest_progress_period ON user_quest_progress(user_id, period_key);
"""

DEFAULT_QUESTS = [
    {
        "code": "daily_play_15_matches",
        "title": "Сыграть 15 матчей",
        "description": "Выйди на лёд и проведи 15 матчей за день.",
        "period_type": "daily",
        "target_type": "matches_played",
        "target_value": 15,
        "bp_reward": 2,
        "coins_reward": 0,
        "sort_order": 10,
    },
    {
        "code": "daily_win_9_matches",
        "title": "Выиграть 9 матчей",
        "description": "Забери 9 побед за день.",
        "period_type": "daily",
        "target_type": "matches_won",
        "target_value": 9,
        "bp_reward": 2,
        "coins_reward": 0,
        "sort_order": 20,
    },
    {
        "code": "daily_score_30_goals",
        "title": "Забить 30 голов",
        "description": "Забей 30 шайб в любых матчах за день.",
        "period_type": "daily",
        "target_type": "goals_scored",
        "target_value": 30,
        "bp_reward": 2,
        "coins_reward": 0,
        "sort_order": 30,
    },
    {
        "code": "seasonal_play_1500_matches",
        "title": "Сыграть 1500 матчей",
        "description": "Большая сезонная цель для самых активных игроков.",
        "period_type": "seasonal",
        "target_type": "matches_played",
        "target_value": 1500,
        "bp_reward": 10,
        "coins_reward": 100000,
        "sort_order": 10,
    },
    {
        "code": "seasonal_win_100_shutouts",
        "title": "Выиграть 100 сухих матчей",
        "description": "Побеждай без пропущенных шайб и докажи силу защиты.",
        "period_type": "seasonal",
        "target_type": "shutout_wins",
        "target_value": 100,
        "bp_reward": 10,
        "coins_reward": 100000,
        "sort_order": 20,
    },
]

DEFAULT_CURRENCIES = [
    {
        "code": "coins",
        "name": "Coins",
        "icon": "🪙",
        "description": "Основная валюта для паков и наград.",
    },
    {
        "code": "energy",
        "name": "Рубли",
        "icon": "💵",
        "description": "Премиальная валюта. За покупкой обращаться к @E4RFQ.",
    },
    {
        "code": "rank_point",
        "name": "Rank-point",
        "icon": "🏅",
        "description": "Валюта для рейтинговых паков.",
    },
    {
        "code": "fortress_token",
        "name": "Fortress Token",
        "icon": "🛡",
        "description": "Событийная валюта THE STRONGHOLD для прокачки Miro Heiskanen.",
    },
]

DEFAULT_COLLECTIONS = [
    {
        "code": "free-cards",
        "name": "Бесплатные карточки",
        "description": "Коллекция для бесплатной карточки раз в 6 часов.",
    },
]

LEGACY_DEMO_COLLECTION_CODES = [
    "default",
    "pros-26",
    "ranked",
    "superstars",
    "TOTS",
    "winners",
    "wch-26",
    "died-legends-1",
    "died-legends-2",
]

LEGACY_DEMO_PACK_CODES = [
    "common-pack",
    "elite-pack",
    "prospects-2026-pack",
    "starter-pack",
    "superstar-pack",
    "TOTS-pack",
    "winners-pack",
    "world-championship-2026-pack",
    "ranked-pack",
]

DEFAULT_PACKS = []

DEFAULT_PACK_SLOTS = []











CREATE_DAILY_LOGIN_CLAIMS_TABLE = """
CREATE TABLE IF NOT EXISTS daily_login_claims (
    user_id INTEGER PRIMARY KEY,
    last_claim_date TEXT,
    streak INTEGER NOT NULL DEFAULT 0,
    total_claims INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_DAILY_LOGIN_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS daily_login_rewards (
    day INTEGER PRIMARY KEY,
    coins INTEGER NOT NULL DEFAULT 0,
    rubles INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL
);
"""

DEFAULT_SEASON_REWARD_TIERS = [
    ("T1", 500000, 100, None),
    ("T2", 300000, 0, None),
    ("T3", 200000, 0, None),
    ("T4_10", 100000, 0, None),
    ("T11_25", 50000, 0, None),
]


DEFAULT_DAILY_LOGIN_LADDER = [
    (1, 500, 0, None),
    (2, 1000, 0, None),
    (3, 2000, 0, None),
    (4, 3500, 0, None),
    (5, 5000, 1, None),
    (6, 7500, 1, None),
    (7, 15000, 3, None),
]




CREATE_PROMO_CODES_TABLE = """
CREATE TABLE IF NOT EXISTS promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    coins INTEGER NOT NULL DEFAULT 0,
    rubles INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    bp_points INTEGER NOT NULL DEFAULT 0,
    max_activations INTEGER NOT NULL DEFAULT 0,
    per_user_limit INTEGER NOT NULL DEFAULT 1,
    activations_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL
);
"""

CREATE_PROMO_ACTIVATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS promo_code_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_code_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_PROMO_ACTIVATIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_promo_activations ON promo_code_activations(promo_code_id, user_id);
"""




CREATE_ACTIVE_MATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS active_matches (
    user_id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# ЕДИНЫЙ ГЛОБАЛЬНЫЙ MATCH LOCK (см. app/services/match_guard.py) — заменяет
# active_matches как источник правды для "у пользователя уже есть незавершённый
# матч" во ВСЕХ режимах (Ranked/Stronghold/Clan War 2/обычные матчи/турниры).
# active_matches НЕ удаляется (раздел ТЗ "без удаления пользовательских данных"),
# но новый код больше не читает/пишет её — миграция (db.py run_migrations)
# переносит любые ещё существующие строки active_matches в player_match_locks.
CREATE_PLAYER_MATCH_LOCKS_TABLE = """
CREATE TABLE IF NOT EXISTS player_match_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_id INTEGER,
    match_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'ACQUIRING', 'ACTIVE', 'RESOLVING', 'COMPLETED', 'CANCELLED', 'EXPIRED', 'FAILED'
    )),
    request_id TEXT,
    acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    release_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# Физическое ограничение БД: максимум одна АКТИВНАЯ блокировка на user_id — partial
# unique index (SQLite поддерживает WHERE в CREATE UNIQUE INDEX). Это работает
# независимо от Python-уровня и независимо от того, сколько процессов/воркеров бота
# запущено одновременно: второй INSERT с тем же user_id и активным статусом получает
# sqlite3.IntegrityError на уровне файла БД, а не только "гонку в приложении".
CREATE_PLAYER_MATCH_LOCKS_ACTIVE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_player_match_locks_active_user
ON player_match_locks(user_id)
WHERE status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING');
"""

CREATE_PLAYER_MATCH_LOCKS_MATCH_INDEX = """
CREATE INDEX IF NOT EXISTS idx_player_match_locks_match_id ON player_match_locks(match_id);
"""

CREATE_PLAYER_MATCH_LOCKS_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_player_match_locks_status ON player_match_locks(status);
"""

CREATE_PLAYER_MATCH_LOCKS_REQUEST_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_player_match_locks_request_id ON player_match_locks(request_id);
"""

CREATE_PLAYER_MATCH_LOCKS_EXPIRES_AT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_player_match_locks_expires_at ON player_match_locks(expires_at);
"""

CREATE_CLAN_JOIN_REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')) DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_CLAN_JOIN_REQUESTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_clan_join_requests ON clan_join_requests(clan_id, status);
"""




CREATE_SEASONS_TABLE = """
CREATE TABLE IF NOT EXISTS seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER NOT NULL,
    ended_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    top_json TEXT NOT NULL DEFAULT '[]',
    rewards_summary TEXT NOT NULL DEFAULT '',
    players_count INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_SEASON_REWARD_TIERS_TABLE = """
CREATE TABLE IF NOT EXISTS season_reward_tiers (
    tier_key TEXT PRIMARY KEY,
    coins INTEGER NOT NULL DEFAULT 0,
    rubles INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL
);
"""





CREATE_CLAN_WAR_PLAYER_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_war_player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    wins_contributed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(clan_id, user_id),
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_CLAN_ARENAS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_arenas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    capture_wins_required INTEGER NOT NULL DEFAULT 10,
    income_currency_code TEXT,
    income_amount INTEGER NOT NULL DEFAULT 0,
    capture_currency_code TEXT,
    capture_amount INTEGER NOT NULL DEFAULT 0,
    holder_clan_id INTEGER,
    captured_at TEXT,
    last_income_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (holder_clan_id) REFERENCES clans(id) ON DELETE SET NULL,
    FOREIGN KEY (income_currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (capture_currency_code) REFERENCES currencies(code) ON DELETE SET NULL
);
"""

CREATE_CLAN_ARENA_ATTACKS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_arena_attacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arena_id INTEGER NOT NULL,
    clan_id INTEGER NOT NULL,
    started_by_user_id INTEGER,
    points INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('active', 'won', 'failed')) DEFAULT 'active',
    notified INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (arena_id) REFERENCES clan_arenas(id) ON DELETE CASCADE,
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
    FOREIGN KEY (started_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);
"""

CREATE_CLAN_ARENAS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_clan_arenas_active ON clan_arenas(active, holder_clan_id);
"""

CREATE_CLAN_ARENA_ATTACKS_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_clan_arena_attacks_status ON clan_arena_attacks(status, expires_at);
"""

CREATE_CLAN_ARENA_ATTACKS_CLAN_INDEX = """
CREATE INDEX IF NOT EXISTS idx_clan_arena_attacks_clan ON clan_arena_attacks(clan_id, status);
"""

CREATE_CLAN_SEASONS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER NOT NULL,
    ended_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    top_json TEXT NOT NULL DEFAULT '[]',
    rewards_summary TEXT NOT NULL DEFAULT '',
    clans_count INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_CLAN_SEASON_REWARD_TIERS_TABLE = """
CREATE TABLE IF NOT EXISTS clan_season_reward_tiers (
    place INTEGER PRIMARY KEY CHECK(place BETWEEN 1 AND 5),
    coins INTEGER NOT NULL DEFAULT 0,
    rubles INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL
);
"""

DEFAULT_CLAN_SEASON_REWARD_TIERS = [
    (1, 1000000, 0, None),
    (2, 750000, 0, None),
    (3, 500000, 0, None),
    (4, 300000, 0, None),
    (5, 200000, 0, None),
]


CREATE_CREATOR_LEVEL_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS creator_level_settings (
    level INTEGER PRIMARY KEY CHECK(level BETWEEN 1 AND 5),
    required_subscribers INTEGER NOT NULL DEFAULT 0,
    required_distributed_value INTEGER NOT NULL DEFAULT 0,
    welcome_coins INTEGER NOT NULL DEFAULT 0,
    weekly_coins INTEGER NOT NULL DEFAULT 0,
    weekly_elite_packs INTEGER NOT NULL DEFAULT 0,
    weekly_legendary_packs INTEGER NOT NULL DEFAULT 0,
    weekly_elite_pack_id INTEGER,
    weekly_legendary_pack_id INTEGER,
    promo_codes_weekly INTEGER NOT NULL DEFAULT 0,
    author_code_percent_bp INTEGER NOT NULL DEFAULT 0,
    exclusive_card_rating INTEGER NOT NULL DEFAULT 0,
    perks_text TEXT NOT NULL DEFAULT '',
    personal_rewards_text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (weekly_elite_pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (weekly_legendary_pack_id) REFERENCES packs(id) ON DELETE SET NULL
);
"""

CREATE_CREATOR_BANK_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS creator_bank_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('currency','pack','card')),
    currency_code TEXT,
    pack_id INTEGER,
    user_card_id INTEGER,
    quantity INTEGER NOT NULL DEFAULT 1,
    value_per_unit INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('available','distributed','cancelled')) DEFAULT 'available',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE SET NULL
);
"""

CREATE_CREATOR_BONUS_CLAIMS_TABLE = """
CREATE TABLE IF NOT EXISTS creator_bonus_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    bonus_type TEXT NOT NULL CHECK(bonus_type IN ('welcome','weekly')),
    level INTEGER NOT NULL DEFAULT 0,
    period_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_CREATOR_BANK_ITEMS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_creator_bank_items_user ON creator_bank_items(user_id, status, item_type);
"""

CREATE_CREATOR_BANK_ITEMS_CARD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_creator_bank_items_card ON creator_bank_items(user_card_id, status);
"""

CREATE_CREATOR_DISTRIBUTIONS_CREATOR_INDEX = """
CREATE INDEX IF NOT EXISTS idx_creator_distributions_creator ON creator_distributions(creator_user_id, created_at);
"""

CREATE_CREATOR_BONUS_CLAIMS_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_bonus_claims_unique
ON creator_bonus_claims(user_id, bonus_type, level)
WHERE bonus_type = 'welcome';
"""

CREATE_CREATOR_WEEKLY_CLAIMS_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_bonus_claims_weekly_unique
ON creator_bonus_claims(user_id, bonus_type, period_key)
WHERE bonus_type = 'weekly';
"""

CREATE_CREATOR_APPLICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS creator_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    subscribers INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')) DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_CREATOR_INVENTORY_TABLE = """
CREATE TABLE IF NOT EXISTS creator_inventory (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_CREATOR_PACK_INVENTORY_TABLE = """
CREATE TABLE IF NOT EXISTS creator_pack_inventory (
    user_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, pack_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE CASCADE
);
"""

CREATE_CREATOR_DISTRIBUTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS creator_distributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_user_id INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    reward_desc TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creator_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


CREATE_TEAM_DIVISIONS_TABLE = """
CREATE TABLE IF NOT EXISTS team_divisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    image_path TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_TEAM_DIVISION_TEAMS_TABLE = """
CREATE TABLE IF NOT EXISTS team_division_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    division_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team_name),
    FOREIGN KEY (division_id) REFERENCES team_divisions(id) ON DELETE CASCADE
);
"""

CREATE_ANIMATION_ASSETS_TABLE = """
CREATE TABLE IF NOT EXISTS animation_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('division','team','country','stage')),
    asset_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_type, asset_key)
);
"""

CREATE_REWARD_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS reward_settings (
    key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    reward_type TEXT NOT NULL DEFAULT 'currency',
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    card_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE SET NULL
);
"""

CREATE_TEAM_DIVISION_TEAMS_DIVISION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_team_division_teams_division ON team_division_teams(division_id);
"""

CREATE_TEAM_DIVISION_TEAMS_TEAM_INDEX = """
CREATE INDEX IF NOT EXISTS idx_team_division_teams_team ON team_division_teams(team_name);
"""

CREATE_ANIMATION_ASSETS_TYPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_animation_assets_type ON animation_assets(asset_type, asset_key);
"""


# ============================================================================
# THE STRONGHOLD (сезонное событие) — см. docs/THE_STRONGHOLD_SPEC.md
# ============================================================================

CREATE_STRONGHOLD_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    status TEXT NOT NULL CHECK(status IN ('DRAFT', 'SCHEDULED', 'ACTIVE', 'GRACE_PERIOD', 'ARCHIVED')) DEFAULT 'DRAFT',
    starts_at TEXT,
    ends_at TEXT,
    grace_ends_at TEXT,
    store_available_in_grace INTEGER NOT NULL DEFAULT 0,
    ft_conversion_rate INTEGER NOT NULL DEFAULT 5000,
    config_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_STRONGHOLD_UPGRADE_STEPS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_upgrade_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    from_card_id INTEGER NOT NULL,
    to_card_id INTEGER NOT NULL,
    ft_cost INTEGER NOT NULL DEFAULT 0,
    coins_cost INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, step_order),
    UNIQUE(event_id, from_card_id),
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (from_card_id) REFERENCES cards(id) ON DELETE RESTRICT,
    FOREIGN KEY (to_card_id) REFERENCES cards(id) ON DELETE RESTRICT
);
"""

CREATE_STRONGHOLD_UPGRADE_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_upgrade_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    user_card_id INTEGER NOT NULL,
    step_id INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'success', 'failed')) DEFAULT 'pending',
    from_card_id INTEGER NOT NULL,
    to_card_id INTEGER NOT NULL,
    ft_spent INTEGER NOT NULL DEFAULT 0,
    coins_spent INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, request_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES stronghold_upgrade_steps(id) ON DELETE RESTRICT
);
"""

CREATE_STRONGHOLD_CURRENCY_LEDGER_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_currency_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_FORTRESSES_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_fortresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    is_boss INTEGER NOT NULL DEFAULT 0,
    first_completion_ft INTEGER NOT NULL DEFAULT 0,
    repeat_coins_reward INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, order_index),
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_FORTRESS_MATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_fortress_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fortress_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    opponent_name TEXT NOT NULL,
    opponent_ovr INTEGER NOT NULL,
    star_rules TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fortress_id, order_index),
    FOREIGN KEY (fortress_id) REFERENCES stronghold_fortresses(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_USER_FORTRESS_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_user_fortress_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    fortress_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('LOCKED', 'AVAILABLE', 'IN_PROGRESS', 'COMPLETED')) DEFAULT 'LOCKED',
    stars_total INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    first_completion_reward_claimed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, fortress_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (fortress_id) REFERENCES stronghold_fortresses(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_USER_FORTRESS_MATCH_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_user_fortress_match_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    fortress_match_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('LOCKED', 'AVAILABLE', 'STARTED', 'WON', 'LOST', 'COMPLETED')) DEFAULT 'LOCKED',
    stars INTEGER NOT NULL DEFAULT 0,
    match_id INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, fortress_match_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (fortress_match_id) REFERENCES stronghold_fortress_matches(id) ON DELETE CASCADE,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE SET NULL
);
"""

CREATE_STRONGHOLD_ENDLESS_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_endless_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE,
    base_opponent_ovr INTEGER NOT NULL DEFAULT 75,
    ovr_growth_per_wave INTEGER NOT NULL DEFAULT 1,
    max_opponent_ovr INTEGER NOT NULL DEFAULT 99,
    weekly_ft_cap INTEGER NOT NULL DEFAULT 20,
    ft_per_wave INTEGER NOT NULL DEFAULT 2,
    modifier_every_n_waves INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_ENDLESS_WAVES_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_endless_waves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    wave_number INTEGER NOT NULL,
    opponent_ovr INTEGER NOT NULL,
    modifiers TEXT NOT NULL DEFAULT '[]',
    result TEXT NOT NULL CHECK(result IN ('win', 'loss')),
    match_id INTEGER,
    ft_awarded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE SET NULL
);
"""

CREATE_STRONGHOLD_USER_ENDLESS_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_user_endless_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    current_wave INTEGER NOT NULL DEFAULT 1,
    best_wave INTEGER NOT NULL DEFAULT 0,
    best_wave_achieved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_ENDLESS_WEEKLY_FT_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_endless_weekly_ft (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    week_key TEXT NOT NULL,
    ft_earned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id, week_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_LEADERBOARD_ENTRIES_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_leaderboard_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    best_wave INTEGER NOT NULL DEFAULT 0,
    achieved_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_MISSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('DAILY', 'WEEKLY', 'SEASONAL')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    condition_type TEXT NOT NULL CHECK(condition_type IN (
        'play_matches', 'win_matches', 'fortress_match_complete', 'fortress_complete',
        'earn_stars', 'use_collection_card', 'upgrade_heiskanen', 'endless_wave_complete',
        'spend_coins', 'spend_ft', 'goals_scored', 'clean_sheet', 'season_level_reached'
    )),
    target_value INTEGER NOT NULL DEFAULT 1,
    reward_ft INTEGER NOT NULL DEFAULT 0,
    reward_coins INTEGER NOT NULL DEFAULT 0,
    reward_xp INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, code),
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_USER_MISSION_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_user_mission_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    mission_id INTEGER NOT NULL,
    period_key TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    reward_claimed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, mission_id, period_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mission_id) REFERENCES stronghold_missions(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_SEASON_TRACK_LEVELS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_season_track_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    xp_threshold INTEGER NOT NULL,
    reward_ft INTEGER NOT NULL DEFAULT 0,
    reward_coins INTEGER NOT NULL DEFAULT 0,
    reward_pack_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, level),
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (reward_pack_id) REFERENCES packs(id) ON DELETE SET NULL
);
"""

CREATE_STRONGHOLD_USER_SEASON_PROGRESS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_user_season_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_USER_SEASON_CLAIMS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_user_season_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    season_level_id INTEGER NOT NULL,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, season_level_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (season_level_id) REFERENCES stronghold_season_track_levels(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_STORE_PRODUCTS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_store_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('Featured', 'Packs', 'Cards', 'Resources', 'Bundles')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    price_currency_code TEXT NOT NULL,
    price_amount INTEGER NOT NULL DEFAULT 0,
    purchase_limit INTEGER NOT NULL DEFAULT 0,
    starts_at TEXT,
    ends_at TEXT,
    contents TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, code),
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (price_currency_code) REFERENCES currencies(code) ON DELETE RESTRICT
);
"""

CREATE_STRONGHOLD_STORE_PURCHASES_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_store_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    price_currency_code TEXT NOT NULL,
    price_amount INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed')) DEFAULT 'success',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, request_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES stronghold_store_products(id) ON DELETE RESTRICT
);
"""

CREATE_STRONGHOLD_AUDIT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    admin_id INTEGER,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    before TEXT,
    after TEXT,
    reason TEXT,
    request_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_STRONGHOLD_ANALYTICS_EVENT_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_analytics_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    user_id INTEGER,
    event_code TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_STRONGHOLD_COMPENSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_compensations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    compensation_type TEXT NOT NULL CHECK(compensation_type IN ('coins', 'fortress_token', 'card', 'pack', 'season_xp')),
    amount INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    card_id INTEGER,
    reason TEXT NOT NULL,
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(admin_id, request_id),
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_FT_CONVERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS stronghold_ft_conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    ft_converted INTEGER NOT NULL,
    coins_granted INTEGER NOT NULL,
    converted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES stronghold_events(id) ON DELETE CASCADE
);
"""

CREATE_STRONGHOLD_UPGRADE_TRANSACTIONS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_upgrade_tx_user ON stronghold_upgrade_transactions(user_id, status, created_at);
"""

CREATE_STRONGHOLD_CURRENCY_LEDGER_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_ledger_user ON stronghold_currency_ledger(user_id, event_id, created_at);
"""

CREATE_STRONGHOLD_USER_FORTRESS_PROGRESS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_fortress_progress_user ON stronghold_user_fortress_progress(user_id, event_id, status);
"""

CREATE_STRONGHOLD_USER_FORTRESS_MATCH_PROGRESS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_fortress_match_progress_user ON stronghold_user_fortress_match_progress(user_id, status);
"""

CREATE_STRONGHOLD_ENDLESS_WAVES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_endless_waves_user ON stronghold_endless_waves(user_id, event_id, created_at);
"""

CREATE_STRONGHOLD_ENDLESS_WEEKLY_FT_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_endless_weekly_ft_user ON stronghold_endless_weekly_ft(user_id, event_id, week_key);
"""

CREATE_STRONGHOLD_LEADERBOARD_RANK_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_leaderboard_rank ON stronghold_leaderboard_entries(event_id, best_wave DESC, achieved_at);
"""

CREATE_STRONGHOLD_USER_MISSION_PROGRESS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_mission_progress_user ON stronghold_user_mission_progress(user_id, completed, reward_claimed);
"""

CREATE_STRONGHOLD_STORE_PURCHASES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_store_purchases_user ON stronghold_store_purchases(user_id, product_id, created_at);
"""

CREATE_STRONGHOLD_AUDIT_LOG_CREATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_audit_log_created ON stronghold_audit_log(event_id, created_at);
"""

CREATE_STRONGHOLD_ANALYTICS_EVENT_CREATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_stronghold_analytics_event_created ON stronghold_analytics_event(event_id, event_code, created_at);
"""


# ============================================================================
# CLAN WAR 2.0 — единственная система клановых войн в проекте.
# Все данные режима хранятся в таблицах с префиксом "war2_".
# См. docs/CLAN_WAR_2_SPEC.md.
# ============================================================================

CREATE_WAR2_SEASONS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_number INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('scheduled', 'active', 'ended')) DEFAULT 'scheduled',
    starts_at TEXT,
    ends_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_WAR2_DAILY_TICKETS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_daily_tickets (
    user_id INTEGER NOT NULL,
    day_key TEXT NOT NULL,
    tickets_used INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, day_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_WAR2_MODES_TABLE = """
CREATE TABLE IF NOT EXISTS war2_modes (
    code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    uses_draft INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_WAR2_MATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS war2_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER,
    status TEXT NOT NULL CHECK(status IN ('drafting', 'completed', 'abandoned')) DEFAULT 'drafting',
    user_id INTEGER NOT NULL,
    user_clan_id INTEGER,
    opponent_user_id INTEGER,
    opponent_clan_id INTEGER,
    opponent_name TEXT NOT NULL DEFAULT '',
    opponent_type TEXT NOT NULL CHECK(opponent_type IN ('player', 'bot')) DEFAULT 'bot',
    mode_code TEXT NOT NULL,
    pool_id INTEGER,
    used_wild_card INTEGER NOT NULL DEFAULT 0,
    wild_card_replaced_card_id INTEGER,
    wild_card_user_card_id INTEGER,
    user_lineup_json TEXT NOT NULL DEFAULT '[]',
    opponent_lineup_json TEXT NOT NULL DEFAULT '[]',
    user_ovr INTEGER NOT NULL DEFAULT 0,
    opponent_ovr INTEGER NOT NULL DEFAULT 0,
    user_score INTEGER NOT NULL DEFAULT 0,
    opponent_score INTEGER NOT NULL DEFAULT 0,
    result TEXT CHECK(result IN ('win', 'loss') OR result IS NULL),
    rating_delta INTEGER NOT NULL DEFAULT 0,
    is_overtime INTEGER NOT NULL DEFAULT 0,
    is_shootout INTEGER NOT NULL DEFAULT 0,
    mvp_title TEXT NOT NULL DEFAULT '',
    periods_summary TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (season_id) REFERENCES war2_seasons(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_clan_id) REFERENCES clans(id) ON DELETE SET NULL,
    FOREIGN KEY (opponent_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (opponent_clan_id) REFERENCES clans(id) ON DELETE SET NULL,
    FOREIGN KEY (mode_code) REFERENCES war2_modes(code) ON DELETE RESTRICT,
    FOREIGN KEY (wild_card_replaced_card_id) REFERENCES cards(id) ON DELETE SET NULL,
    FOREIGN KEY (wild_card_user_card_id) REFERENCES user_cards(id) ON DELETE SET NULL
);
"""

CREATE_WAR2_MATCHES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_war2_matches_user ON war2_matches(user_id, created_at);
"""

CREATE_WAR2_MATCH_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_match_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    period_title TEXT NOT NULL,
    time_text TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES war2_matches(id) ON DELETE CASCADE
);
"""

CREATE_WAR2_MATCH_EVENTS_MATCH_INDEX = """
CREATE INDEX IF NOT EXISTS idx_war2_match_events_match ON war2_match_events(match_id);
"""

CREATE_WAR2_DRAFT_POOLS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_draft_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL UNIQUE,
    card_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES war2_matches(id) ON DELETE CASCADE
);
"""

CREATE_WAR2_DRAFT_PICKS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_draft_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 5),
    pick_order INTEGER NOT NULL,
    picker TEXT NOT NULL CHECK(picker IN ('user', 'opponent')),
    card_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, card_id),
    UNIQUE(match_id, picker, round_number),
    FOREIGN KEY (match_id) REFERENCES war2_matches(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE RESTRICT
);
"""

CREATE_WAR2_PLAYER_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rating_points INTEGER NOT NULL DEFAULT 1000,
    matches_played INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season_id, user_id),
    FOREIGN KEY (season_id) REFERENCES war2_seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_WAR2_CLAN_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_clan_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    clan_id INTEGER NOT NULL,
    rating_points INTEGER NOT NULL DEFAULT 0,
    wins_contributed INTEGER NOT NULL DEFAULT 0,
    matches_played INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season_id, clan_id),
    FOREIGN KEY (season_id) REFERENCES war2_seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE
);
"""

CREATE_WAR2_COSMETIC_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS war2_cosmetic_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('FRAME', 'BACKGROUND', 'NICK_BADGE', 'CARD_FRAME', 'PROFILE_BACKGROUND', 'TITLE')),
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    rarity TEXT NOT NULL CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')) DEFAULT 'Common',
    image_path TEXT,
    badge_text TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_USER_COSMETIC_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS user_cosmetic_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    cosmetic_item_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    rarity TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'admin_grant',
    equipped INTEGER NOT NULL DEFAULT 0,
    trade_locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (cosmetic_item_id) REFERENCES war2_cosmetic_items(id) ON DELETE RESTRICT
);
"""

CREATE_USER_COSMETIC_ITEMS_OWNER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_cosmetic_items_owner ON user_cosmetic_items(owner_id, type, equipped);
"""

CREATE_WAR2_CLAN_ROSTER_TABLE = """
CREATE TABLE IF NOT EXISTS war2_clan_roster (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    added_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(clan_id, user_id),
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (added_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);
"""

CREATE_WAR2_CLAN_ROSTER_CLAN_INDEX = """
CREATE INDEX IF NOT EXISTS idx_war2_clan_roster_clan ON war2_clan_roster(clan_id);
"""

# ============================================================================
# RANKED MODE (v1) — новая, отдельная от старой ладдер-системы (users.league/
# rating_points) система. Косметика (NICK_BADGE/CARD_FRAME/PROFILE_BACKGROUND/TITLE)
# переиспользует уже существующий каталог war2_cosmetic_items/user_cosmetic_items
# (расширенный раздел выше, CHECK по типу теперь включает все 6 значений).
# См. docs/RANKED_MODE_SPEC.md.
# ============================================================================

CREATE_RANKED_SEASONS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_number INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('scheduled', 'active', 'ended')) DEFAULT 'scheduled',
    starts_at TEXT,
    ends_at TEXT,
    top_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_RANKED_LEAGUES_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_leagues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    division_code TEXT NOT NULL CHECK(division_code IN ('bronze', 'silver', 'gold', 'platinum', 'diamond', 'master', 'legend')),
    tier_number INTEGER NOT NULL CHECK(tier_number BETWEEN 1 AND 3),
    title TEXT NOT NULL,
    min_points INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    icon TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(division_code, tier_number)
);
"""

CREATE_RANKED_LEAGUES_SORT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_ranked_leagues_sort ON ranked_leagues(sort_order);
"""

CREATE_RANKED_PLAYER_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rank_points INTEGER NOT NULL DEFAULT 0,
    ranked_league_id INTEGER,
    ranked_xp INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    matches_played INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season_id, user_id),
    FOREIGN KEY (season_id) REFERENCES ranked_seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (ranked_league_id) REFERENCES ranked_leagues(id) ON DELETE SET NULL
);
"""

CREATE_RANKED_MATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER,
    user_id INTEGER NOT NULL,
    opponent_user_id INTEGER,
    opponent_name TEXT NOT NULL DEFAULT '',
    opponent_type TEXT NOT NULL CHECK(opponent_type IN ('player', 'bot')) DEFAULT 'bot',
    user_score INTEGER NOT NULL DEFAULT 0,
    opponent_score INTEGER NOT NULL DEFAULT 0,
    result TEXT NOT NULL CHECK(result IN ('win', 'loss')),
    rank_delta INTEGER NOT NULL DEFAULT 0,
    division_before TEXT NOT NULL DEFAULT '',
    division_after TEXT NOT NULL DEFAULT '',
    is_shootout INTEGER NOT NULL DEFAULT 0,
    regulation_user_score INTEGER NOT NULL DEFAULT 0,
    regulation_opponent_score INTEGER NOT NULL DEFAULT 0,
    shootout_user_goals INTEGER NOT NULL DEFAULT 0,
    shootout_opponent_goals INTEGER NOT NULL DEFAULT 0,
    shootout_log_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (season_id) REFERENCES ranked_seasons(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (opponent_user_id) REFERENCES users(id) ON DELETE SET NULL
);
"""

CREATE_RANKED_MATCHES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_ranked_matches_user ON ranked_matches(user_id, created_at);
"""

CREATE_RANKED_LEAGUE_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_league_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranked_league_id INTEGER NOT NULL,
    reward_type TEXT NOT NULL CHECK(reward_type IN ('cosmetic', 'currency', 'pack')),
    cosmetic_item_id INTEGER,
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ranked_league_id) REFERENCES ranked_leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (cosmetic_item_id) REFERENCES war2_cosmetic_items(id) ON DELETE SET NULL,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (pack_id) REFERENCES ranked_packs(id) ON DELETE SET NULL
);
"""

CREATE_RANKED_LEAGUE_REWARD_CLAIMS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_league_reward_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    ranked_league_id INTEGER NOT NULL,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, season_id, ranked_league_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES ranked_seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (ranked_league_id) REFERENCES ranked_leagues(id) ON DELETE CASCADE
);
"""

CREATE_USER_CARD_FRAMES_TABLE = """
CREATE TABLE IF NOT EXISTS user_card_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_cosmetic_item_id INTEGER NOT NULL UNIQUE,
    user_card_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_cosmetic_item_id) REFERENCES user_cosmetic_items(id) ON DELETE CASCADE,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE CASCADE
);
"""

CREATE_RANKED_CAPTAINS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_captains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    user_card_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_card_id) REFERENCES user_cards(id) ON DELETE CASCADE
);
"""

CREATE_RANKED_PACKS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    division_code TEXT NOT NULL CHECK(division_code IN ('bronze', 'silver', 'gold', 'platinum', 'diamond', 'master', 'legend')),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_RANKED_PACK_SLOTS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_pack_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    slot_number INTEGER NOT NULL,
    reward_type TEXT NOT NULL CHECK(reward_type IN ('card', 'currency', 'xp', 'cosmetic')),
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    cosmetic_item_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pack_id) REFERENCES ranked_packs(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (cosmetic_item_id) REFERENCES war2_cosmetic_items(id) ON DELETE SET NULL
);
"""

CREATE_RANKED_PACK_CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_pack_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pack_id, card_id),
    FOREIGN KEY (pack_id) REFERENCES ranked_packs(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);
"""

CREATE_USER_RANKED_PACKS_TABLE = """
CREATE TABLE IF NOT EXISTS user_ranked_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, pack_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pack_id) REFERENCES ranked_packs(id) ON DELETE CASCADE
);
"""

CREATE_RANKED_PASSES_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    levels_count INTEGER NOT NULL DEFAULT 60,
    points_per_level INTEGER NOT NULL DEFAULT 100,
    gold_currency_code TEXT,
    gold_price_amount INTEGER NOT NULL DEFAULT 0,
    platinum_currency_code TEXT,
    platinum_price_amount INTEGER NOT NULL DEFAULT 0,
    upgrade_currency_code TEXT,
    upgrade_price_amount INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (season_id) REFERENCES ranked_seasons(id) ON DELETE SET NULL,
    FOREIGN KEY (gold_currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (platinum_currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (upgrade_currency_code) REFERENCES currencies(code) ON DELETE SET NULL
);
"""

CREATE_RANKED_PASS_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS ranked_pass_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pass_id INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 60),
    track TEXT NOT NULL CHECK(track IN ('free', 'gold', 'platinum')),
    reward_type TEXT NOT NULL CHECK(reward_type IN ('currency', 'pack', 'card', 'cosmetic')),
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    pack_id INTEGER,
    card_id INTEGER,
    cosmetic_item_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pass_id) REFERENCES ranked_passes(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE SET NULL,
    FOREIGN KEY (cosmetic_item_id) REFERENCES war2_cosmetic_items(id) ON DELETE SET NULL
);
"""

CREATE_RANKED_PASS_REWARDS_PASS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_ranked_pass_rewards_pass ON ranked_pass_rewards(pass_id, level, track);
"""

CREATE_USER_RANKED_PASSES_TABLE = """
CREATE TABLE IF NOT EXISTS user_ranked_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pass_id INTEGER NOT NULL,
    gold_unlocked INTEGER NOT NULL DEFAULT 0,
    platinum_unlocked INTEGER NOT NULL DEFAULT 0,
    purchased_at TEXT,
    platinum_purchased_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, pass_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (pass_id) REFERENCES ranked_passes(id) ON DELETE CASCADE
);
"""

CREATE_USER_RANKED_PASS_REWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS user_ranked_pass_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reward_id INTEGER NOT NULL,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, reward_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (reward_id) REFERENCES ranked_pass_rewards(id) ON DELETE CASCADE
);
"""


# ---------------------------------------------------------------------------
# BLACK MARKET — персональная ежедневная ротация витрины на пользователя.
#
# MASTER POOL (black_market_settings/black_market_rarity_weights/black_market_pool_items)
# общий для всех. STOREFRONT (black_market_user_rotations/black_market_user_rotation_items)
# генерируется лениво (при открытии магазина) и независимо для каждого пользователя —
# см. app/services/black_market_generation.py.
# ---------------------------------------------------------------------------

CREATE_BLACK_MARKET_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    shop_enabled INTEGER NOT NULL DEFAULT 1,
    slots_count INTEGER NOT NULL DEFAULT 6,
    stock_mode TEXT NOT NULL CHECK(stock_mode IN ('PERSONAL', 'GLOBAL')) DEFAULT 'PERSONAL',
    allow_duplicate_slots INTEGER NOT NULL DEFAULT 0,
    global_rotation_version INTEGER NOT NULL DEFAULT 1,
    notification_target TEXT NOT NULL CHECK(notification_target IN ('ALL', 'ACTIVE_N_DAYS', 'NONE', 'IN_BOT_ONLY')) DEFAULT 'ALL',
    notification_active_days INTEGER NOT NULL DEFAULT 7,
    last_notified_business_date TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_BLACK_MARKET_RARITY_WEIGHTS_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_rarity_weights (
    rarity TEXT PRIMARY KEY CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')),
    weight INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_BLACK_MARKET_POOL_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_pool_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL CHECK(item_type IN ('currency', 'pack', 'card', 'cosmetic')),
    currency_code TEXT,
    amount INTEGER NOT NULL DEFAULT 1,
    pack_id INTEGER,
    card_id INTEGER,
    cosmetic_item_id INTEGER,
    rarity TEXT NOT NULL CHECK(rarity IN ('Common', 'Rare', 'Epic', 'Legendary', 'Event', 'Icon')),
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    price_currency_code TEXT NOT NULL,
    price_mode TEXT NOT NULL CHECK(price_mode IN ('FIXED', 'RANDOM_RANGE')) DEFAULT 'FIXED',
    price_amount INTEGER NOT NULL DEFAULT 0,
    price_min_amount INTEGER,
    price_max_amount INTEGER,
    max_stock_per_rotation INTEGER NOT NULL DEFAULT 1,
    stock_min INTEGER,
    stock_max INTEGER,
    personal_purchase_limit INTEGER NOT NULL DEFAULT 0,
    available_from TEXT,
    available_until TEXT,
    allow_repeat_in_rotation INTEGER NOT NULL DEFAULT 0,
    selection_weight INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (currency_code) REFERENCES currencies(code) ON DELETE SET NULL,
    FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE SET NULL,
    FOREIGN KEY (cosmetic_item_id) REFERENCES war2_cosmetic_items(id) ON DELETE SET NULL,
    FOREIGN KEY (price_currency_code) REFERENCES currencies(code) ON DELETE RESTRICT
);
"""

CREATE_BLACK_MARKET_POOL_ITEMS_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bm_pool_items_active ON black_market_pool_items(active, rarity);
"""

CREATE_BLACK_MARKET_USER_ROTATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_user_rotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    business_date TEXT NOT NULL,
    rotation_version INTEGER NOT NULL,
    seed_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'EXPIRED')) DEFAULT 'ACTIVE',
    generation_reason TEXT NOT NULL DEFAULT 'lazy_open',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ends_at TEXT,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invalidated_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# Партиальный уникальный индекс (не table-level UNIQUE): гонка при одновременном первом
# открытии витрины должна оставить только одну ACTIVE-ротацию на (user_id, business_date,
# rotation_version). Но нужно ещё, чтобы админ мог "обновить рынок игрока" — прошлая
# ротация переводится в EXPIRED, а не удаляется (история), и ей допустимо оставаться
# с тем же ключом, пока новая ACTIVE-строка генерируется под тем же rotation_version.
CREATE_BLACK_MARKET_USER_ROTATIONS_ACTIVE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_bm_user_rotations_active_unique
ON black_market_user_rotations(user_id, business_date, rotation_version)
WHERE status = 'ACTIVE';
"""

CREATE_BLACK_MARKET_USER_ROTATIONS_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bm_user_rotations_user_date ON black_market_user_rotations(user_id, business_date);
"""

CREATE_BLACK_MARKET_USER_ROTATIONS_VERSION_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bm_user_rotations_version_status ON black_market_user_rotations(rotation_version, status);
"""

CREATE_BLACK_MARKET_USER_ROTATION_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_user_rotation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_rotation_id INTEGER NOT NULL,
    slot_number INTEGER NOT NULL,
    pool_item_id INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    item_reference_id INTEGER,
    rarity TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price_currency_code TEXT NOT NULL,
    price_amount INTEGER NOT NULL,
    initial_personal_stock INTEGER NOT NULL,
    remaining_personal_stock INTEGER NOT NULL,
    personal_purchase_limit INTEGER NOT NULL DEFAULT 0,
    purchased_quantity INTEGER NOT NULL DEFAULT 0,
    item_status TEXT NOT NULL CHECK(item_status IN ('AVAILABLE', 'SOLD_OUT', 'REMOVED')) DEFAULT 'AVAILABLE',
    preview TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_rotation_id, slot_number),
    FOREIGN KEY (user_rotation_id) REFERENCES black_market_user_rotations(id) ON DELETE CASCADE,
    FOREIGN KEY (pool_item_id) REFERENCES black_market_pool_items(id) ON DELETE RESTRICT
);
"""

CREATE_BLACK_MARKET_USER_ROTATION_ITEMS_ROTATION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bm_rotation_items_rotation ON black_market_user_rotation_items(user_rotation_id);
"""

CREATE_BLACK_MARKET_PURCHASES_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_rotation_id INTEGER NOT NULL,
    rotation_item_id INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    price_currency_code TEXT NOT NULL,
    price_amount INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed')) DEFAULT 'success',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, request_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_rotation_id) REFERENCES black_market_user_rotations(id) ON DELETE CASCADE,
    FOREIGN KEY (rotation_item_id) REFERENCES black_market_user_rotation_items(id) ON DELETE RESTRICT
);
"""

CREATE_BLACK_MARKET_PURCHASES_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bm_purchases_user ON black_market_purchases(user_id, created_at);
"""

CREATE_BLACK_MARKET_ADMIN_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS black_market_admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    target_user_id INTEGER,
    before TEXT,
    after TEXT,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_BLACK_MARKET_ADMIN_AUDIT_CREATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bm_admin_audit_created ON black_market_admin_audit(created_at);
"""


SCHEMA_QUERIES = [
    CREATE_GAME_SETTINGS_TABLE,
    CREATE_SECURITY_LOGS_TABLE,
    CREATE_USERS_TABLE,
    CREATE_BOT_ADMINS_TABLE,
    CREATE_CURRENCIES_TABLE,
    CREATE_CURRENCY_BALANCES_TABLE,
    CREATE_COLLECTIONS_TABLE,
    CREATE_CARDS_TABLE,
    CREATE_USER_CARDS_TABLE,
    CREATE_INVENTORY_ITEMS_TABLE,
    CREATE_USER_ITEMS_TABLE,
    CREATE_USER_ITEMS_USER_INDEX,
    CREATE_DNA_WELCOME_GRANTS_TABLE,
    CREATE_DNA_EXTRACTION_LOGS_TABLE,
    CREATE_DNA_EXTRACTION_LOGS_USER_INDEX,
    CREATE_DNA_CHOICE_CLAIMS_TABLE,
    CREATE_DNA_CRAFT_LOGS_TABLE,
    CREATE_DNA_CRAFT_LOGS_USER_INDEX,
    CREATE_PACKS_TABLE,
    CREATE_PACK_SLOTS_TABLE,
    CREATE_PACK_CARDS_TABLE,
    CREATE_USER_PACKS_TABLE,
    CREATE_PACK_OPENINGS_TABLE,
    CREATE_PACK_OPENING_REWARDS_TABLE,
    CREATE_PACK_PENDING_REVEALS_TABLE,
    CREATE_PACK_PENDING_REVEALS_STATUS_INDEX,
    CREATE_SHOP_PURCHASES_TABLE,
    CREATE_MATCHES_TABLE,
    CREATE_MATCH_EVENTS_TABLE,
    CREATE_MATCH_QUEUE_TABLE,
    CREATE_QUESTS_TABLE,
    CREATE_USER_QUEST_PROGRESS_TABLE,
    CREATE_EVENTS_TABLE,
    CREATE_USER_EVENT_PROGRESS_TABLE,
    CREATE_USER_EVENT_REWARDS_TABLE,
    CREATE_HOCKEY_PASSES_TABLE,
    CREATE_HOCKEY_PASS_REWARDS_TABLE,
    CREATE_USER_HOCKEY_PASSES_TABLE,
    CREATE_USER_HOCKEY_PASS_REWARDS_TABLE,
    CREATE_FREE_CARD_CLAIMS_TABLE,
    CREATE_STARTER_KIT_CARDS_TABLE,
    CREATE_CLANS_TABLE,
    CREATE_CLAN_MEMBERS_TABLE,
    CREATE_CLAN_WAR_PLAYER_STATS_TABLE,
    CREATE_CLAN_ARENAS_TABLE,
    CREATE_CLAN_ARENA_ATTACKS_TABLE,
    CREATE_CLAN_ARENAS_ACTIVE_INDEX,
    CREATE_CLAN_ARENA_ATTACKS_STATUS_INDEX,
    CREATE_CLAN_ARENA_ATTACKS_CLAN_INDEX,
    CREATE_DAILY_LOGIN_CLAIMS_TABLE,
    CREATE_DAILY_LOGIN_REWARDS_TABLE,
    CREATE_PROMO_CODES_TABLE,
    CREATE_PROMO_ACTIVATIONS_TABLE,
    CREATE_PROMO_ACTIVATIONS_INDEX,
    CREATE_ACTIVE_MATCHES_TABLE,
    CREATE_PLAYER_MATCH_LOCKS_TABLE,
    CREATE_PLAYER_MATCH_LOCKS_ACTIVE_UNIQUE_INDEX,
    CREATE_PLAYER_MATCH_LOCKS_MATCH_INDEX,
    CREATE_PLAYER_MATCH_LOCKS_STATUS_INDEX,
    CREATE_PLAYER_MATCH_LOCKS_REQUEST_ID_INDEX,
    CREATE_PLAYER_MATCH_LOCKS_EXPIRES_AT_INDEX,
    CREATE_CLAN_JOIN_REQUESTS_TABLE,
    CREATE_CLAN_JOIN_REQUESTS_INDEX,
    CREATE_SEASONS_TABLE,
    CREATE_SEASON_REWARD_TIERS_TABLE,
    CREATE_CLAN_SEASONS_TABLE,
    CREATE_CLAN_SEASON_REWARD_TIERS_TABLE,
    CREATE_CREATOR_LEVEL_SETTINGS_TABLE,
    CREATE_CREATOR_BANK_ITEMS_TABLE,
    CREATE_CREATOR_BONUS_CLAIMS_TABLE,
    CREATE_CREATOR_BANK_ITEMS_USER_INDEX,
    CREATE_CREATOR_BANK_ITEMS_CARD_INDEX,
    CREATE_CREATOR_BONUS_CLAIMS_UNIQUE_INDEX,
    CREATE_CREATOR_APPLICATIONS_TABLE,
    CREATE_CREATOR_INVENTORY_TABLE,
    CREATE_CREATOR_PACK_INVENTORY_TABLE,
    CREATE_CREATOR_DISTRIBUTIONS_TABLE,
    CREATE_CREATOR_DISTRIBUTIONS_CREATOR_INDEX,
    CREATE_TEAM_DIVISIONS_TABLE,
    CREATE_TEAM_DIVISION_TEAMS_TABLE,
    CREATE_ANIMATION_ASSETS_TABLE,
    CREATE_REWARD_SETTINGS_TABLE,
    CREATE_TEAM_DIVISION_TEAMS_DIVISION_INDEX,
    CREATE_TEAM_DIVISION_TEAMS_TEAM_INDEX,
    CREATE_ANIMATION_ASSETS_TYPE_INDEX,
    CREATE_TRADE_OFFERS_TABLE,
    CREATE_TRADE_OFFER_CARDS_TABLE,
    CREATE_TRADE_OFFER_WANTED_CARDS_TABLE,
    CREATE_TRADE_OFFER_COSMETICS_TABLE,
    CREATE_TRADE_OFFER_WANTED_COSMETICS_TABLE,
    CREATE_USER_CARD_VIEW_PREFERENCES_TABLE,
    CREATE_CHEMISTRY_RULES_TABLE,
    CREATE_GAME_SETTINGS_UPDATED_INDEX,
    CREATE_SECURITY_LOGS_USER_INDEX,
    CREATE_SECURITY_LOGS_CREATED_INDEX,
    CREATE_BOT_ADMINS_TELEGRAM_ID_INDEX,
    CREATE_BOT_ADMINS_ACTIVE_INDEX,
    CREATE_USERS_TELEGRAM_ID_INDEX,
    CREATE_CURRENCY_BALANCES_USER_INDEX,
    CREATE_CARDS_NAME_INDEX,
    CREATE_CARDS_PLAYER_KEY_INDEX,
    CREATE_CARDS_COLLECTION_INDEX,
    CREATE_CARDS_ACTIVE_INDEX,
    CREATE_USER_CARDS_USER_INDEX,
    CREATE_USER_CARDS_CARD_INDEX,
    CREATE_USER_CARDS_LINEUP_INDEX,
    CREATE_USER_CARDS_TRADE_LOCK_INDEX,
    CREATE_PACKS_CODE_INDEX,
    CREATE_PACKS_ACTIVE_INDEX,
    CREATE_PACK_SLOTS_PACK_INDEX,
    CREATE_PACK_SLOTS_RARITY_INDEX,
    CREATE_PACK_CARDS_PACK_INDEX,
    CREATE_PACK_CARDS_CARD_INDEX,
    CREATE_USER_PACKS_USER_INDEX,
    CREATE_PACK_OPENINGS_USER_INDEX,
    CREATE_PACK_REWARDS_OPENING_INDEX,
    CREATE_SHOP_PURCHASES_USER_INDEX,
    CREATE_SHOP_PURCHASES_PACK_INDEX,
    CREATE_MATCHES_USER_INDEX,
    CREATE_MATCHES_CREATED_INDEX,
    CREATE_MATCH_EVENTS_MATCH_INDEX,
    CREATE_MATCH_QUEUE_USER_INDEX,
    CREATE_MATCH_QUEUE_SEARCH_INDEX,
    CREATE_HOCKEY_PASSES_ACTIVE_INDEX,
    CREATE_HOCKEY_PASS_REWARDS_PASS_INDEX,
    CREATE_USER_HOCKEY_PASSES_USER_INDEX,
    CREATE_USER_HOCKEY_PASS_REWARDS_USER_INDEX,
    CREATE_FREE_CARD_CLAIMS_NOTIFY_INDEX,
    CREATE_STARTER_KIT_CARDS_CARD_INDEX,
    CREATE_CLANS_ACTIVE_INDEX,
    CREATE_CLAN_MEMBERS_CLAN_INDEX,
    CREATE_TRADE_OFFERS_STATUS_INDEX,
    CREATE_TRADE_OFFERS_CREATOR_INDEX,
    CREATE_TRADE_OFFERS_TARGET_INDEX,
    CREATE_TRADE_OFFER_CARDS_OFFER_INDEX,
    CREATE_TRADE_OFFER_CARDS_CARD_INDEX,
    CREATE_TRADE_WANTED_CARDS_OFFER_INDEX,
    CREATE_TRADE_OFFER_COSMETICS_OFFER_INDEX,
    CREATE_TRADE_OFFER_COSMETICS_ITEM_INDEX,
    CREATE_TRADE_OFFER_WANTED_COSMETICS_OFFER_INDEX,
    CREATE_CHEMISTRY_RULES_TYPE_INDEX,
    CREATE_CHEMISTRY_RULES_VALUE_INDEX,
    CREATE_QUESTS_PERIOD_INDEX,
    CREATE_QUESTS_TARGET_INDEX,
    CREATE_USER_QUEST_PROGRESS_USER_INDEX,
    CREATE_USER_QUEST_PROGRESS_PERIOD_INDEX,
    CREATE_EVENTS_ACTIVE_INDEX,
    CREATE_EVENTS_TARGET_INDEX,
    CREATE_USER_EVENT_PROGRESS_USER_INDEX,
    CREATE_USER_EVENT_PROGRESS_EVENT_INDEX,
    CREATE_USER_EVENT_REWARDS_USER_INDEX,
    CREATE_STRONGHOLD_EVENTS_TABLE,
    CREATE_STRONGHOLD_UPGRADE_STEPS_TABLE,
    CREATE_STRONGHOLD_UPGRADE_TRANSACTIONS_TABLE,
    CREATE_STRONGHOLD_CURRENCY_LEDGER_TABLE,
    CREATE_STRONGHOLD_FORTRESSES_TABLE,
    CREATE_STRONGHOLD_FORTRESS_MATCHES_TABLE,
    CREATE_STRONGHOLD_USER_FORTRESS_PROGRESS_TABLE,
    CREATE_STRONGHOLD_USER_FORTRESS_MATCH_PROGRESS_TABLE,
    CREATE_STRONGHOLD_ENDLESS_CONFIG_TABLE,
    CREATE_STRONGHOLD_ENDLESS_WAVES_TABLE,
    CREATE_STRONGHOLD_USER_ENDLESS_PROGRESS_TABLE,
    CREATE_STRONGHOLD_ENDLESS_WEEKLY_FT_TABLE,
    CREATE_STRONGHOLD_LEADERBOARD_ENTRIES_TABLE,
    CREATE_STRONGHOLD_MISSIONS_TABLE,
    CREATE_STRONGHOLD_USER_MISSION_PROGRESS_TABLE,
    CREATE_STRONGHOLD_SEASON_TRACK_LEVELS_TABLE,
    CREATE_STRONGHOLD_USER_SEASON_PROGRESS_TABLE,
    CREATE_STRONGHOLD_USER_SEASON_CLAIMS_TABLE,
    CREATE_STRONGHOLD_STORE_PRODUCTS_TABLE,
    CREATE_STRONGHOLD_STORE_PURCHASES_TABLE,
    CREATE_STRONGHOLD_AUDIT_LOG_TABLE,
    CREATE_STRONGHOLD_ANALYTICS_EVENT_TABLE,
    CREATE_STRONGHOLD_COMPENSATIONS_TABLE,
    CREATE_STRONGHOLD_FT_CONVERSIONS_TABLE,
    CREATE_STRONGHOLD_UPGRADE_TRANSACTIONS_USER_INDEX,
    CREATE_STRONGHOLD_CURRENCY_LEDGER_USER_INDEX,
    CREATE_STRONGHOLD_USER_FORTRESS_PROGRESS_USER_INDEX,
    CREATE_STRONGHOLD_USER_FORTRESS_MATCH_PROGRESS_USER_INDEX,
    CREATE_STRONGHOLD_ENDLESS_WAVES_USER_INDEX,
    CREATE_STRONGHOLD_ENDLESS_WEEKLY_FT_USER_INDEX,
    CREATE_STRONGHOLD_LEADERBOARD_RANK_INDEX,
    CREATE_STRONGHOLD_USER_MISSION_PROGRESS_USER_INDEX,
    CREATE_STRONGHOLD_STORE_PURCHASES_USER_INDEX,
    CREATE_STRONGHOLD_AUDIT_LOG_CREATED_INDEX,
    CREATE_STRONGHOLD_ANALYTICS_EVENT_CREATED_INDEX,
    CREATE_WAR2_SEASONS_TABLE,
    CREATE_WAR2_DAILY_TICKETS_TABLE,
    CREATE_WAR2_MODES_TABLE,
    CREATE_WAR2_MATCHES_TABLE,
    CREATE_WAR2_MATCHES_USER_INDEX,
    CREATE_WAR2_MATCH_EVENTS_TABLE,
    CREATE_WAR2_MATCH_EVENTS_MATCH_INDEX,
    CREATE_WAR2_DRAFT_POOLS_TABLE,
    CREATE_WAR2_DRAFT_PICKS_TABLE,
    CREATE_WAR2_PLAYER_STATS_TABLE,
    CREATE_WAR2_CLAN_STATS_TABLE,
    CREATE_WAR2_COSMETIC_ITEMS_TABLE,
    CREATE_USER_COSMETIC_ITEMS_TABLE,
    CREATE_USER_COSMETIC_ITEMS_OWNER_INDEX,
    CREATE_WAR2_CLAN_ROSTER_TABLE,
    CREATE_WAR2_CLAN_ROSTER_CLAN_INDEX,
    CREATE_RANKED_SEASONS_TABLE,
    CREATE_RANKED_LEAGUES_TABLE,
    CREATE_RANKED_LEAGUES_SORT_INDEX,
    CREATE_RANKED_PLAYER_STATS_TABLE,
    CREATE_RANKED_MATCHES_TABLE,
    CREATE_RANKED_MATCHES_USER_INDEX,
    CREATE_RANKED_LEAGUE_REWARDS_TABLE,
    CREATE_RANKED_LEAGUE_REWARD_CLAIMS_TABLE,
    CREATE_USER_CARD_FRAMES_TABLE,
    CREATE_RANKED_CAPTAINS_TABLE,
    CREATE_RANKED_PACKS_TABLE,
    CREATE_RANKED_PACK_SLOTS_TABLE,
    CREATE_RANKED_PACK_CARDS_TABLE,
    CREATE_USER_RANKED_PACKS_TABLE,
    CREATE_RANKED_PASSES_TABLE,
    CREATE_RANKED_PASS_REWARDS_TABLE,
    CREATE_RANKED_PASS_REWARDS_PASS_INDEX,
    CREATE_USER_RANKED_PASSES_TABLE,
    CREATE_USER_RANKED_PASS_REWARDS_TABLE,
    CREATE_BLACK_MARKET_SETTINGS_TABLE,
    CREATE_BLACK_MARKET_RARITY_WEIGHTS_TABLE,
    CREATE_BLACK_MARKET_POOL_ITEMS_TABLE,
    CREATE_BLACK_MARKET_POOL_ITEMS_ACTIVE_INDEX,
    CREATE_BLACK_MARKET_USER_ROTATIONS_TABLE,
    CREATE_BLACK_MARKET_USER_ROTATIONS_ACTIVE_UNIQUE_INDEX,
    CREATE_BLACK_MARKET_USER_ROTATIONS_USER_INDEX,
    CREATE_BLACK_MARKET_USER_ROTATIONS_VERSION_STATUS_INDEX,
    CREATE_BLACK_MARKET_USER_ROTATION_ITEMS_TABLE,
    CREATE_BLACK_MARKET_USER_ROTATION_ITEMS_ROTATION_INDEX,
    CREATE_BLACK_MARKET_PURCHASES_TABLE,
    CREATE_BLACK_MARKET_PURCHASES_USER_INDEX,
    CREATE_BLACK_MARKET_ADMIN_AUDIT_TABLE,
    CREATE_BLACK_MARKET_ADMIN_AUDIT_CREATED_INDEX,
]
