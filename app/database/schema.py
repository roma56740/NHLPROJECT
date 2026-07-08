

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
    overall INTEGER NOT NULL CHECK(overall BETWEEN 1 AND 99),
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

CREATE_PACKS_TABLE = """
CREATE TABLE IF NOT EXISTS packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path TEXT,
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
    ("T11_50", 50000, 0, None),
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
    CREATE_PACKS_TABLE,
    CREATE_PACK_SLOTS_TABLE,
    CREATE_PACK_CARDS_TABLE,
    CREATE_USER_PACKS_TABLE,
    CREATE_PACK_OPENINGS_TABLE,
    CREATE_PACK_OPENING_REWARDS_TABLE,
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
    CREATE_CLAN_JOIN_REQUESTS_TABLE,
    CREATE_CLAN_JOIN_REQUESTS_INDEX,
    CREATE_SEASONS_TABLE,
    CREATE_SEASON_REWARD_TIERS_TABLE,
    CREATE_CREATOR_APPLICATIONS_TABLE,
    CREATE_CREATOR_INVENTORY_TABLE,
    CREATE_CREATOR_PACK_INVENTORY_TABLE,
    CREATE_CREATOR_DISTRIBUTIONS_TABLE,
    CREATE_TRADE_OFFERS_TABLE,
    CREATE_TRADE_OFFER_CARDS_TABLE,
    CREATE_TRADE_OFFER_WANTED_CARDS_TABLE,
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
]
