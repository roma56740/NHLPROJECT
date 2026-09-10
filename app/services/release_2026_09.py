from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database.db import get_connection

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
HEROES_PART1_AT = datetime(2026, 9, 10, 12, 0, tzinfo=MOSCOW_TZ)
HEROES_PART2_AT = datetime(2026, 9, 17, 12, 0, tzinfo=MOSCOW_TZ)
PIRATES_START_AT = datetime(2026, 9, 23, 0, 0, tzinfo=MOSCOW_TZ)
PIRATES_END_AT = datetime(2026, 9, 30, 23, 59, 59, tzinfo=MOSCOW_TZ)
PASS_LEVELS = 30
PASS_POINTS_PER_LEVEL = 5
PASS_PREMIUM_PRICE_ENERGY = 400

ENERGY_TIERS: tuple[tuple[int, int], ...] = (
    (50, 0), (100, 5), (250, 10), (500, 15), (1000, 20),
    (2500, 30), (5000, 40), (7500, 45), (10000, 50),
)

FIRESIDE_PLAYERS: tuple[dict[str, object], ...] = (
    {"name":"Cole Caufield","player_key":"cole caufield","position":"F","ovr":100,"team":"Montreal Canadiens","country":"USA","image":"assets/release/fireside/cole_caufield_100.png","weight":0},
    {"name":"Wyatt Johnston","player_key":"wyatt johnston","position":"F","ovr":99,"team":"Dallas Stars","country":"Canada","image":"assets/release/fireside/wyatt_johnston_99.png","weight":5},
    {"name":"Dylan Guenther","player_key":"dylan guenther","position":"F","ovr":99,"team":"Utah Mammoth","country":"Canada","image":"assets/release/fireside/dylan_guenther_99.png","weight":5},
    {"name":"Evan Bouchard","player_key":"evan bouchard","position":"D","ovr":98,"team":"Edmonton Oilers","country":"Canada","image":"assets/release/fireside/evan_bouchard_98.png","weight":8},
    {"name":"Zach Werenski","player_key":"zach werenski","position":"D","ovr":98,"team":"Columbus Blue Jackets","country":"USA","image":"assets/release/fireside/zach_werenski_98.png","weight":8},
    {"name":"Joel Eriksson Ek","player_key":"joel eriksson ek","position":"F","ovr":97,"team":"Minnesota Wild","country":"Sweden","image":"assets/release/fireside/joel_eriksson_ek_97.png","weight":11},
    {"name":"Thomas Harley","player_key":"thomas harley","position":"D","ovr":96,"team":"Dallas Stars","country":"Canada","image":"assets/release/fireside/thomas_harley_96.png","weight":11},
    {"name":"Josh Doan","player_key":"josh doan","position":"F","ovr":96,"team":"Buffalo Sabres","country":"USA","image":"assets/release/fireside/josh_doan_96.png","weight":14},
    {"name":"Gabriel Vilardi","player_key":"gabriel vilardi","position":"F","ovr":96,"team":"Winnipeg Jets","country":"Canada","image":"assets/release/fireside/gabriel_vilardi_96.png","weight":14},
    {"name":"Gustav Forsling","player_key":"gustav forsling","position":"D","ovr":95,"team":"Florida Panthers","country":"Sweden","image":"assets/release/fireside/gustav_forsling_95.png","weight":24},
)

HEROES: tuple[dict[str, object], ...] = (
    {"key":"ovechkin","name":"Alexander Ovechkin","player_key":"alexander ovechkin","position":"F","team":"Washington Capitals","country":"Russia","part":1},
    {"key":"crosby","name":"Sidney Crosby","player_key":"sidney crosby","position":"F","team":"Pittsburgh Penguins","country":"Canada","part":1},
    {"key":"chara","name":"Zdeno Chara","player_key":"zdeno chara","position":"D","team":"Boston Bruins","country":"Slovakia","part":1},
    {"key":"price","name":"Carey Price","player_key":"carey price","position":"G","team":"Montreal Canadiens","country":"Canada","part":1},
    {"key":"datsyuk","name":"Pavel Datsyuk","player_key":"pavel datsyuk","position":"F","team":"Detroit Red Wings","country":"Russia","part":2},
    {"key":"brodeur","name":"Martin Brodeur","player_key":"martin brodeur","position":"G","team":"New Jersey Devils","country":"Canada","part":2},
    {"key":"lidstrom","name":"Nicklas Lidstrom","player_key":"nicklas lidstrom","position":"D","team":"Detroit Red Wings","country":"Sweden","part":2},
    {"key":"jagr","name":"Jaromir Jagr","player_key":"jaromir jagr","position":"F","team":"Pittsburgh Penguins","country":"Czechia","part":2},
)

PIRATE_PLAYERS: tuple[dict[str, object], ...] = (
    {"name":"Joe Sakic","key":"joe sakic","position":"F","ovr":101,"team":"Colorado Avalanche","country":"Canada","image":"assets/release/pirates/joe_sakic_101.png"},
    {"name":"Mathew Barzal","key":"mathew barzal","position":"F","ovr":97,"team":"New York Islanders","country":"Canada","image":"assets/release/pirates/mathew_barzal_97.png"},
    {"name":"Anthony Mantha","key":"anthony mantha","position":"F","ovr":95,"team":"Calgary Flames","country":"Canada","image":"assets/release/pirates/anthony_mantha_95.png"},
    {"name":"Shayne Gostisbehere","key":"shayne gostisbehere","position":"D","ovr":97,"team":"Carolina Hurricanes","country":"USA","image":"assets/release/pirates/shayne_gostisbehere_97.png"},
    {"name":"Scott Niedermayer","key":"scott niedermayer","position":"D","ovr":99,"team":"New Jersey Devils","country":"Canada","image":"assets/release/pirates/scott_niedermayer_99.png"},
    {"name":"Mackenzie Blackwood","key":"mackenzie blackwood","position":"G","ovr":98,"team":"Colorado Avalanche","country":"Canada","image":"assets/release/pirates/mackenzie_blackwood_98.png"},
    {"name":"Nico Hischier","key":"nico hischier","position":"F","ovr":98,"team":"New Jersey Devils","country":"Switzerland","image":"assets/release/pirates/nico_hischier_98.png"},
    {"name":"Jake DeBrusk","key":"jake debrusk","position":"F","ovr":97,"team":"Vancouver Canucks","country":"Canada","image":"assets/release/pirates/jake_debrusk_97.png"},
    {"name":"Daniel Sprong","key":"daniel sprong","position":"F","ovr":96,"team":"Seattle Kraken","country":"Netherlands","image":"assets/release/pirates/daniel_sprong_96.png"},
    {"name":"Chris Pronger","key":"chris pronger","position":"D","ovr":98,"team":"Philadelphia Flyers","country":"Canada","image":"assets/release/pirates/chris_pronger_98.png"},
    {"name":"Shea Weber","key":"shea weber","position":"D","ovr":99,"team":"Montreal Canadiens","country":"Canada","image":"assets/release/pirates/shea_weber_99.png"},
    {"name":"Henrik Lundqvist","key":"henrik lundqvist","position":"G","ovr":101,"team":"New York Rangers","country":"Sweden","image":"assets/release/pirates/henrik_lundqvist_101.png"},
)

# level, free kind, free code/value, free amount, premium kind, premium code/value, premium amount
FIRESIDE_PASS_REWARDS: tuple[tuple, ...] = (
    (1,"currency","coins",25000,"xfactor","firescore",1),
    (2,"currency","rank_point",1,"currency","coins",75000),
    (3,"item","fireside_collectible",1,"box","ahl_box",1),
    (4,"currency","coins",40000,"currency","rank_point",3),
    (5,"currency","rank_point",2,"currency","coins",100000),
    (6,"currency","coins",50000,"xfactor","ordinary_random",1),
    (7,"item","fireside_collectible",1,"box","common_box",1),
    (8,"currency","coins",75000,"currency","rank_point",5),
    (9,"currency","rank_point",3,"currency","coins",125000),
    (10,"currency","coins",100000,"item","fireside_collectible",2),
    (11,"item","fireside_collectible",1,"box","ahl_box",1),
    (12,"currency","rank_point",4,"currency","coins",150000),
    (13,"currency","coins",125000,"currency","rank_point",6),
    (14,"item","fireside_collectible",2,"xfactor","ordinary_random",1),
    (15,"currency","coins",150000,"box","common_box",1),
    (16,"currency","rank_point",5,"currency","coins",250000),
    (17,"currency","coins",175000,"currency","rank_point",8),
    (18,"xfactor","heatwave",1,"box","elite_box",1),
    (19,"currency","coins",200000,"item","fireside_collectible",3),
    (20,"currency","rank_point",6,"currency","coins",300000),
    (21,"currency","coins",225000,"box","common_box",1),
    (22,"xfactor","ordinary_random",1,"currency","rank_point",10),
    (23,"item","fireside_collectible",3,"currency","coins",350000),
    (24,"currency","coins",250000,"xfactor","ordinary_random",1),
    (25,"currency","rank_point",8,"box","elite_box",1),
    (26,"currency","coins",300000,"currency","rank_point",12),
    (27,"item","fireside_collectible",4,"currency","coins",500000),
    (28,"xfactor","ordinary_random",1,"currency","rank_point",15),
    (29,"currency","coins",400000,"currency","coins",750000),
    (30,"box","elite_box",1,"bundle","cole_and_fireside_box",1),
)

HERO_CHAPTERS: dict[str, tuple[dict[str, object], ...]] = {
    "ovechkin": (
        {"title":"THE ARRIVAL","metric":"shots","target":60,"reward":25000},
        {"title":"THE SCORER","metric":"goals","target":15,"reward":40000},
        {"title":"THE SCORING MACHINE","metric":"multi_goal_games","target":5,"reward":60000},
        {"title":"WHEN IT MATTERS","metric":"game_winning_goals","target":4,"reward":80000},
        {"title":"THE GREAT EIGHT","metric":"hat_tricks","target":2,"reward":100000},
        {"title":"IMMORTAL","metric":"goals","target":40,"reward":0},
    ),
    "crosby": (
        {"title":"THE PLAYMAKER","metric":"assists","target":12,"reward":25000},
        {"title":"POINT PER NIGHT","metric":"points","target":25,"reward":40000},
        {"title":"LEAD THE WAY","metric":"multi_point_games","target":6,"reward":60000},
        {"title":"THE CAPTAIN","metric":"wins_with_point","target":8,"reward":80000},
        {"title":"CONSISTENCY","metric":"point_streak","target":7,"reward":100000},
        {"title":"LEGACY","metric":"points","target":60,"reward":0},
    ),
    "chara": (
        {"title":"THE PRESENCE","metric":"hits","target":40,"reward":25000},
        {"title":"NO EASY ICE","metric":"blocks","target":30,"reward":40000},
        {"title":"CAPTAIN'S STANDARD","metric":"wins","target":10,"reward":60000},
        {"title":"SHUT IT DOWN","metric":"low_ga_games","target":6,"reward":80000},
        {"title":"TWO-WAY GIANT","metric":"points","target":15,"reward":100000},
        {"title":"THE GIANT","metric":"hits","target":120,"reward":0},
    ),
    "price": (
        {"title":"THE WALL","metric":"saves","target":100,"reward":25000},
        {"title":"WINNING HABIT","metric":"wins","target":8,"reward":40000},
        {"title":"CALM UNDER FIRE","metric":"low_ga_games","target":5,"reward":60000},
        {"title":"NOTHING GETS THROUGH","metric":"shutouts","target":3,"reward":80000},
        {"title":"WORKHORSE","metric":"save_30_games","target":5,"reward":100000},
        {"title":"PRICELESS","metric":"saves","target":500,"reward":0},
    ),
    "datsyuk": (
        {"title":"THE MAGIC BEGINS","metric":"assists","target":15,"reward":25000},
        {"title":"MAGIC MAN","metric":"points","target":25,"reward":40000},
        {"title":"TAKE OVER","metric":"multi_point_games","target":6,"reward":60000},
        {"title":"CONSISTENCY","metric":"point_streak","target":6,"reward":80000},
        {"title":"WIN WITH STYLE","metric":"wins_with_point","target":10,"reward":100000},
        {"title":"LEGACY","metric":"points","target":75,"reward":0},
    ),
    "brodeur": (
        {"title":"THE CREASE","metric":"saves","target":120,"reward":25000},
        {"title":"WINNER","metric":"wins","target":10,"reward":40000},
        {"title":"SHUT THE DOOR","metric":"shutouts","target":3,"reward":60000},
        {"title":"STREAK","metric":"win_streak","target":5,"reward":80000},
        {"title":"WORKLOAD","metric":"save_30_games","target":6,"reward":100000},
        {"title":"ALL-TIME","metric":"wins","target":30,"reward":0},
    ),
    "lidstrom": (
        {"title":"FIRST PASS","metric":"assists","target":12,"reward":25000},
        {"title":"POSITION","metric":"blocks","target":30,"reward":40000},
        {"title":"WINNING HOCKEY","metric":"wins","target":10,"reward":60000},
        {"title":"TWO-WAY","metric":"points","target":20,"reward":80000},
        {"title":"CONTROL","metric":"low_ga_games","target":8,"reward":100000},
        {"title":"PERFECT POSITION","metric":"assists","target":50,"reward":0},
    ),
    "jagr": (
        {"title":"POWER FORWARD","metric":"points","target":20,"reward":25000},
        {"title":"FINISH","metric":"goals","target":15,"reward":40000},
        {"title":"CREATE","metric":"assists","target":15,"reward":60000},
        {"title":"DOMINATE","metric":"multi_point_games","target":8,"reward":80000},
        {"title":"STREAK","metric":"point_streak","target":8,"reward":100000},
        {"title":"UNBREAKABLE","metric":"points","target":80,"reward":0},
    ),
}


def now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def calculate_pass_level(bp_points: int) -> int:
    return min(PASS_LEVELS, max(1, int(bp_points) // PASS_POINTS_PER_LEVEL + 1))


def energy_discount(quantity: int) -> int:
    if quantity < 50:
        raise ValueError("Минимальная покупка — 50 Energy.")
    if quantity >= 10000:
        return 50
    current = 0
    for threshold, discount in ENERGY_TIERS:
        if quantity >= threshold:
            current = discount
        else:
            break
    return current


def energy_price_rub(quantity: int) -> int:
    discount = energy_discount(quantity)
    return (quantity * (100 - discount) + 99) // 100


def _execute_script_transactionally(connection: sqlite3.Connection, script: str) -> None:
    """Execute a multi-statement SQLite script without sqlite3.executescript().

    executescript() can implicitly commit before running. For release migrations we
    keep every DDL statement inside the caller's transaction/savepoint so a failure
    can be rolled back cleanly. sqlite3.complete_statement() also handles CREATE
    TRIGGER bodies that contain internal semicolons.
    """
    buffer: list[str] = []
    for line in script.splitlines():
        buffer.append(line)
        statement = "\n".join(buffer).strip()
        if statement and sqlite3.complete_statement(statement):
            connection.execute(statement)
            buffer.clear()
    tail = "\n".join(buffer).strip()
    if tail:
        raise sqlite3.OperationalError("Incomplete SQL statement in release migration")


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _seed_collection(connection: sqlite3.Connection, code: str, name: str, description: str, exclusive: int = 1) -> int:
    connection.execute(
        """INSERT INTO collections(code,name,description,active,is_exclusive) VALUES(?,?,?,?,?)
           ON CONFLICT(code) DO UPDATE SET name=excluded.name,description=excluded.description,active=1,is_exclusive=excluded.is_exclusive,updated_at=CURRENT_TIMESTAMP""",
        (code, name, description, 1, exclusive),
    )
    return int(connection.execute("SELECT id FROM collections WHERE code=?", (code,)).fetchone()[0])


def _seed_card(connection: sqlite3.Connection, *, collection_id: int, name: str, player_key: str, position: str, overall: int, team: str, country: str, image_path: str) -> int:
    row = connection.execute(
        "SELECT id FROM cards WHERE collection_id=? AND lower(player_key)=lower(?) AND overall=? ORDER BY id LIMIT 1",
        (collection_id, player_key, overall),
    ).fetchone()
    if row:
        card_id = int(row[0])
        connection.execute(
            "UPDATE cards SET name=?,position=?,team=?,country=?,image_path=?,rarity='Event',active=1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (name, position, team, country, image_path, card_id),
        )
        return card_id
    cursor = connection.execute(
        """INSERT INTO cards(name,player_key,position,overall,team,country,collection_id,rarity,image_path,salary,active)
           VALUES(?,?,?,?,?,?,?,?,?,0,1)""",
        (name, player_key, position, overall, team, country, collection_id, "Event", image_path),
    )
    return int(cursor.lastrowid)


def migrate_release_schema(connection: sqlite3.Connection) -> None:
    connection.execute("SAVEPOINT nexcore_release_2026_09_safe")
    try:
        _execute_script_transactionally(
            connection,
            """
            CREATE TABLE IF NOT EXISTS release_settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS boxes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL DEFAULT '',
                price_currency_code TEXT,
                price_amount INTEGER NOT NULL DEFAULT 0,
                cards_count INTEGER NOT NULL DEFAULT 0,
                resources_count INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                is_shop_available INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(price_currency_code) REFERENCES currencies(code) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS user_boxes(
                user_id INTEGER NOT NULL,
                box_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,box_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(box_id) REFERENCES boxes(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS box_open_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                box_id INTEGER NOT NULL,
                rewards_json TEXT NOT NULL,
                guaranteed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(box_id) REFERENCES boxes(id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_box_open_history_user ON box_open_history(user_id,created_at);
            CREATE TABLE IF NOT EXISTS fireside_box_state(
                user_id INTEGER PRIMARY KEY,
                first_guarantee_used INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS fireside_pass_users(
                user_id INTEGER PRIMARY KEY,
                season_points INTEGER NOT NULL DEFAULT 0,
                season_level INTEGER NOT NULL DEFAULT 1,
                premium_unlocked INTEGER NOT NULL DEFAULT 0,
                purchased_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS fireside_pass_claims(
                user_id INTEGER NOT NULL,
                level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 30),
                track TEXT NOT NULL CHECK(track IN ('free','premium')),
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,level,track),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS xfactor_allowed_positions(
                xfactor_id INTEGER NOT NULL,
                position TEXT NOT NULL CHECK(position IN ('F','D','G')),
                PRIMARY KEY(xfactor_id,position),
                FOREIGN KEY(xfactor_id) REFERENCES xfactors(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS fireside_craft_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target_card_id INTEGER NOT NULL,
                consumed_user_card_id INTEGER NOT NULL,
                collectible_cost INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(target_card_id) REFERENCES cards(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS energy_purchase_orders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                energy_amount INTEGER NOT NULL CHECK(energy_amount>=50),
                discount_percent INTEGER NOT NULL,
                rub_price INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','cancelled')),
                confirmed_by_telegram_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_energy_orders_status ON energy_purchase_orders(status,created_at);
            CREATE TABLE IF NOT EXISTS heroes_user_paths(
                user_id INTEGER NOT NULL,
                hero_key TEXT NOT NULL,
                starter_user_card_id INTEGER NOT NULL,
                card94_id INTEGER NOT NULL,
                card100_id INTEGER NOT NULL,
                current_chapter INTEGER NOT NULL DEFAULT 1,
                claimed_100 INTEGER NOT NULL DEFAULT 0,
                streak_value INTEGER NOT NULL DEFAULT 0,
                unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                PRIMARY KEY(user_id,hero_key),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(starter_user_card_id) REFERENCES user_cards(id) ON DELETE RESTRICT,
                FOREIGN KEY(card94_id) REFERENCES cards(id) ON DELETE RESTRICT,
                FOREIGN KEY(card100_id) REFERENCES cards(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS heroes_chapter_progress(
                user_id INTEGER NOT NULL,
                hero_key TEXT NOT NULL,
                chapter INTEGER NOT NULL CHECK(chapter BETWEEN 1 AND 6),
                progress INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                reward_paid INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,hero_key,chapter),
                FOREIGN KEY(user_id,hero_key) REFERENCES heroes_user_paths(user_id,hero_key) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS heroes_processed_matches(
                user_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,match_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS achievement_card_history(
                user_id INTEGER NOT NULL,
                card_id INTEGER NOT NULL,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,card_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS achievement_claims(
                user_id INTEGER NOT NULL,
                achievement_code TEXT NOT NULL,
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,achievement_code),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cursed_mirror_user_state(
                user_id INTEGER PRIMARY KEY,
                pity_counter INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cursed_mirror_daily(
                user_id INTEGER NOT NULL,
                moscow_date TEXT NOT NULL,
                wins INTEGER NOT NULL DEFAULT 0,
                box_granted INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id,moscow_date),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cursed_mirror_matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                result TEXT NOT NULL CHECK(result IN ('win','loss')),
                user_score INTEGER NOT NULL,
                opponent_score INTEGER NOT NULL,
                opponent_name TEXT NOT NULL,
                opponent_cards_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cursed_mirror_cards(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_card_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                position TEXT NOT NULL,
                original_ovr INTEGER NOT NULL,
                mirrored_ovr INTEGER NOT NULL,
                matches_left INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(source_card_id) REFERENCES cards(id) ON DELETE RESTRICT
            );
            """
        )
        _ensure_column(connection, "cursed_mirror_matches", "mirror_claimed", "mirror_claimed INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "fireside_pass_users", "season_points", "season_points INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "fireside_pass_users", "season_level", "season_level INTEGER NOT NULL DEFAULT 1")
        # SAFE PRODUCTION MIGRATION: legacy systems and player data are intentionally
        # left untouched. Telegram player access is frozen at the middleware/UI layer,
        # not by deleting/resetting old rows. This makes code rollback safe.
        connection.execute("UPDATE currencies SET name='Energy',icon='⚡',description='Премиальная валюта Nexcore. Покупка через @teyld.',active=1,updated_at=CURRENT_TIMESTAMP WHERE code='energy'")
        connection.execute("UPDATE currencies SET name='Rank Coin',icon='🏅',description='Редкая игровая валюта.',active=1,updated_at=CURRENT_TIMESTAMP WHERE code='rank_point'")

        connection.execute(
            """INSERT INTO inventory_items(code,title,description,image_path,stackable,active)
               VALUES('fireside_collectible','Fireside Collectible','Материал для крафта Fireside-карт.','assets/release/fireside/fireside_collectible.png',1,1)
               ON CONFLICT(code) DO UPDATE SET title=excluded.title,description=excluded.description,image_path=excluded.image_path,active=1,updated_at=CURRENT_TIMESTAMP"""
        )
        connection.execute(
            """INSERT INTO inventory_items(code,title,description,image_path,stackable,active)
               VALUES('cursed_collectible','Cursed Collectible','Коллекционный ресурс Cursed Mirror.','assets/release/pirates/dead_mans_chest.png',1,1)
               ON CONFLICT(code) DO UPDATE SET title=excluded.title,description=excluded.description,active=1,updated_at=CURRENT_TIMESTAMP"""
        )
        for code,name,price,cards_count,resources_count,shop,sort,image in (
            ("ahl_box","AHL Box",40000,2,1,1,10,"assets/visual/pack_default.jpg"),
            ("common_box","Common Box",100000,3,2,1,20,"assets/visual/pack_default.jpg"),
            ("elite_box","Elite Box",300000,4,3,1,30,"assets/visual/pack_default.jpg"),
            ("fireside_box","Fireside Box",0,0,1,0,40,"assets/release/fireside/fireside_collectible.png"),
            ("dead_mans_chest","Dead Man's Chest",0,0,1,0,50,"assets/release/pirates/dead_mans_chest.png"),
        ):
            connection.execute(
                """INSERT INTO boxes(code,name,description,image_path,price_currency_code,price_amount,cards_count,resources_count,active,is_shop_available,sort_order)
                   VALUES(?,?,?,?,'coins',?,?,?,1,?,?)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name,image_path=excluded.image_path,price_amount=excluded.price_amount,cards_count=excluded.cards_count,resources_count=excluded.resources_count,active=1,is_shop_available=excluded.is_shop_available,sort_order=excluded.sort_order,updated_at=CURRENT_TIMESTAMP""",
                (code,name,"Nexcore reward box",image,price,cards_count,resources_count,shop,sort),
            )
        fireside_collection = _seed_collection(connection,"fireside-2026","Fireside","Fireside Season 2026 collection",1)
        for item in FIRESIDE_PLAYERS:
            _seed_card(connection,collection_id=fireside_collection,name=str(item["name"]),player_key=str(item["player_key"]),position=str(item["position"]),overall=int(item["ovr"]),team=str(item["team"]),country=str(item["country"]),image_path=str(item["image"]))
        heroes_collection = _seed_collection(connection,"heroes-2026","HEROES","HEROES career event",1)
        for item in HEROES:
            for ovr in (94,100):
                _seed_card(connection,collection_id=heroes_collection,name=str(item["name"]),player_key=str(item["player_key"]),position=str(item["position"]),overall=ovr,team=str(item["team"]),country=str(item["country"]),image_path=f"assets/release/heroes/{item['key']}_{ovr}.png")
        pirate_collection = _seed_collection(connection,"cursed-crew-2026","Cursed Crew","Cursed Mirror pirate Halloween collection",1)
        for item in PIRATE_PLAYERS:
            _seed_card(connection,collection_id=pirate_collection,name=str(item["name"]),player_key=str(item["key"]),position=str(item["position"]),overall=int(item["ovr"]),team=str(item["team"]),country=str(item["country"]),image_path=str(item["image"]))
        # Seed Fireside unique X-Factors. role='F' is the legacy primary role; mapping below allows F + D.
        for code,name,desc,image in (
            ("heatwave","Heatwave","После первого гола этого игрока он получает +3 OVR до конца матча. Срабатывает один раз за матч и не стакается.","assets/release/fireside/heatwave.png"),
            ("last_spark","Last Spark","В последние 5 минут при ничьей или отставании следующий бросок этого игрока имеет 70% шанс стать голом. Один раз за матч.","assets/release/fireside/last_spark.png"),
            ("firescore","Firescore","Первый бросок этого игрока в матче гарантированно становится голом: 100%. Один раз за матч.","assets/release/fireside/firescore.png"),
        ):
            connection.execute(
                """INSERT INTO xfactors(code,name,role,description,icon_path,is_mastery,mastery_player_key,active)
                   VALUES(?,?,'F',?,?,0,NULL,1)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name,description=excluded.description,icon_path=excluded.icon_path,active=1,updated_at=CURRENT_TIMESTAMP""",
                (code,name,desc,image),
            )
            xid = int(connection.execute("SELECT id FROM xfactors WHERE code=?",(code,)).fetchone()[0])
            connection.execute("DELETE FROM xfactor_allowed_positions WHERE xfactor_id=?",(xid,))
            connection.executemany("INSERT INTO xfactor_allowed_positions(xfactor_id,position) VALUES(?,?)",((xid,"F"),(xid,"D")))
        # Backfill lifetime-card history and keep it current for future grants/trades.
        connection.execute("INSERT OR IGNORE INTO achievement_card_history(user_id,card_id) SELECT user_id,card_id FROM user_cards")
        _execute_script_transactionally(
            connection,
            """
            CREATE TRIGGER IF NOT EXISTS trg_achievement_card_history_insert
            AFTER INSERT ON user_cards
            BEGIN
                INSERT OR IGNORE INTO achievement_card_history(user_id,card_id) VALUES(NEW.user_id,NEW.card_id);
            END;
            """
        )
        for key,value in (
            ("release_code","2026-09-fireside-heroes-pirates"),
            ("heroes_part1_at",HEROES_PART1_AT.isoformat()),
            ("heroes_part2_at",HEROES_PART2_AT.isoformat()),
            ("pirates_start_at",PIRATES_START_AT.isoformat()),
            ("pirates_end_at",PIRATES_END_AT.isoformat()),
            ("telegram_player_ui","miniapp_only"),
            ("energy_purchase_mode","manual_contact"),
            ("energy_purchase_contact","@teyld"),
            ("league_reward_ahl","3"),("league_reward_nhl","7"),("league_reward_olympics","15"),
        ):
            connection.execute(
                """INSERT INTO release_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP""",
                (key,value),
            )
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT nexcore_release_2026_09_safe")
        connection.execute("RELEASE SAVEPOINT nexcore_release_2026_09_safe")
        raise
    else:
        connection.execute("RELEASE SAVEPOINT nexcore_release_2026_09_safe")


def enforce_release_retirements(connection: sqlite3.Connection) -> None:
    """Compatibility no-op. Legacy systems are frozen in Telegram UI only.

    Never deactivate/delete legacy packs, Ranked, Stronghold, DNA, frames or
    historical rewards here. Keeping this callable avoids import regressions in
    older code while making rollback to the previous release straightforward.
    """
    return None


def admin_list_boxes() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(connection.execute("SELECT * FROM boxes ORDER BY sort_order,id").fetchall())


def admin_toggle_box(code: str, field: str) -> tuple[bool, str]:
    if field not in {"active", "is_shop_available"}:
        return False, "Недопустимое поле."
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(f"SELECT {field},name FROM boxes WHERE code=?", (code,)).fetchone()
        if row is None:
            connection.rollback(); return False, "Box не найден."
        new_value = 0 if int(row[field]) else 1
        # Event-exclusive boxes must never be made directly purchasable.
        if field == "is_shop_available" and code in {"fireside_box", "dead_mans_chest"} and new_value:
            connection.rollback(); return False, "Этот Box выдаётся только системой события/Pass."
        connection.execute(f"UPDATE boxes SET {field}=?,updated_at=CURRENT_TIMESTAMP WHERE code=?", (new_value, code))
        connection.commit()
        return True, f"{row['name']}: {'включено' if new_value else 'выключено'}."


def get_user_id_by_telegram(connection: sqlite3.Connection, telegram_id: int) -> int | None:
    row = connection.execute("SELECT id FROM users WHERE telegram_id=?",(telegram_id,)).fetchone()
    return int(row[0]) if row else None


def grant_currency(connection: sqlite3.Connection, user_id: int, code: str, amount: int) -> None:
    if amount <= 0:
        return
    connection.execute(
        """INSERT INTO currency_balances(user_id,currency_code,amount) VALUES(?,?,?)
           ON CONFLICT(user_id,currency_code) DO UPDATE SET amount=amount+excluded.amount,updated_at=CURRENT_TIMESTAMP""",
        (user_id,code,amount),
    )


def currency_balance(connection: sqlite3.Connection, user_id: int, code: str) -> int:
    row=connection.execute("SELECT amount FROM currency_balances WHERE user_id=? AND currency_code=?",(user_id,code)).fetchone()
    return int(row[0]) if row else 0


def item_quantity(connection: sqlite3.Connection, user_id: int, code: str) -> int:
    row=connection.execute("""SELECT u.quantity FROM user_items u JOIN inventory_items i ON i.id=u.item_id WHERE u.user_id=? AND i.code=?""",(user_id,code)).fetchone()
    return int(row[0]) if row else 0


def grant_item(connection: sqlite3.Connection, user_id: int, code: str, quantity: int) -> None:
    if quantity <= 0: return
    row=connection.execute("SELECT id FROM inventory_items WHERE code=? AND active=1",(code,)).fetchone()
    if not row: raise ValueError(f"Unknown inventory item: {code}")
    connection.execute(
        """INSERT INTO user_items(user_id,item_id,quantity) VALUES(?,?,?)
           ON CONFLICT(user_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity,updated_at=CURRENT_TIMESTAMP""",
        (user_id,int(row[0]),quantity),
    )


def consume_item(connection: sqlite3.Connection, user_id: int, code: str, quantity: int) -> bool:
    row=connection.execute("""SELECT u.item_id,u.quantity FROM user_items u JOIN inventory_items i ON i.id=u.item_id WHERE u.user_id=? AND i.code=?""",(user_id,code)).fetchone()
    if not row or int(row[1]) < quantity: return False
    connection.execute("UPDATE user_items SET quantity=quantity-?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND item_id=?",(quantity,user_id,int(row[0])))
    return True


def grant_box(connection: sqlite3.Connection, user_id: int, code: str, quantity: int=1) -> None:
    row=connection.execute("SELECT id FROM boxes WHERE code=? AND active=1",(code,)).fetchone()
    if not row: raise ValueError(f"Unknown box: {code}")
    connection.execute(
        """INSERT INTO user_boxes(user_id,box_id,quantity) VALUES(?,?,?)
           ON CONFLICT(user_id,box_id) DO UPDATE SET quantity=quantity+excluded.quantity,updated_at=CURRENT_TIMESTAMP""",
        (user_id,int(row[0]),quantity),
    )


def grant_card(connection: sqlite3.Connection, user_id: int, card_id: int, source: str) -> int:
    cursor=connection.execute("INSERT INTO user_cards(user_id,card_id,obtained_from,is_in_lineup,trade_locked) VALUES(?,?,?,0,0)",(user_id,card_id,source))
    return int(cursor.lastrowid)


def fireside_card_id(connection: sqlite3.Connection, player_key: str, overall: int) -> int | None:
    row=connection.execute("""SELECT c.id FROM cards c JOIN collections col ON col.id=c.collection_id WHERE col.code='fireside-2026' AND lower(c.player_key)=lower(?) AND c.overall=? LIMIT 1""",(player_key,overall)).fetchone()
    return int(row[0]) if row else None


def hero_card_ids(connection: sqlite3.Connection, hero_key: str) -> tuple[int,int] | None:
    hero=next((h for h in HEROES if h["key"]==hero_key),None)
    if not hero:return None
    rows=connection.execute("""SELECT c.id,c.overall FROM cards c JOIN collections col ON col.id=c.collection_id WHERE col.code='heroes-2026' AND lower(c.player_key)=lower(?) AND c.overall IN (94,100)""",(str(hero["player_key"]),)).fetchall()
    by={int(r[1]):int(r[0]) for r in rows}
    return (by[94],by[100]) if 94 in by and 100 in by else None


def get_box_inventory(telegram_id:int) -> list[sqlite3.Row]:
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:return []
        return list(c.execute("""SELECT b.*,COALESCE(ub.quantity,0) quantity FROM boxes b LEFT JOIN user_boxes ub ON ub.box_id=b.id AND ub.user_id=? WHERE b.active=1 ORDER BY b.sort_order,b.id""",(uid,)).fetchall())


def buy_box(telegram_id:int,code:str) -> tuple[bool,str]:
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        uid=get_user_id_by_telegram(c,telegram_id)
        box=c.execute("SELECT * FROM boxes WHERE code=? AND active=1 AND is_shop_available=1",(code,)).fetchone()
        if uid is None or box is None: c.rollback(); return False,"Бокс недоступен."
        price=int(box["price_amount"]); bal=currency_balance(c,uid,str(box["price_currency_code"] or "coins"))
        if bal<price: c.rollback(); return False,"Недостаточно Coins."
        c.execute("UPDATE currency_balances SET amount=amount-?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND currency_code=?",(price,uid,str(box["price_currency_code"])))
        grant_box(c,uid,code,1); c.commit(); return True,f"{box['name']} добавлен в инвентарь."


def _weighted_choice(items:list[tuple[object,float]]) -> object:
    total=sum(float(w) for _,w in items); point=random.random()*total; acc=0.0
    for item,w in items:
        acc+=float(w)
        if point<=acc:return item
    return items[-1][0]


def _random_card(connection: sqlite3.Connection, collection_codes: tuple[str,...]) -> sqlite3.Row | None:
    placeholders=','.join('?' for _ in collection_codes)
    rows=connection.execute(f"""SELECT c.* FROM cards c JOIN collections col ON col.id=c.collection_id WHERE c.active=1 AND col.code IN ({placeholders}) ORDER BY RANDOM() LIMIT 100""",collection_codes).fetchall()
    return random.choice(rows) if rows else None


def _random_regular_xfactor(connection: sqlite3.Connection) -> str | None:
    row=connection.execute("SELECT code FROM xfactors WHERE active=1 AND is_mastery=0 AND code NOT IN ('firescore','heatwave','last_spark') ORDER BY RANDOM() LIMIT 1").fetchone()
    return str(row[0]) if row else None


def _grant_xfactor(connection: sqlite3.Connection,user_id:int,code:str,quantity:int=1)->None:
    row=connection.execute("SELECT id FROM xfactors WHERE code=? AND active=1",(code,)).fetchone()
    if not row: raise ValueError(f"Unknown X-Factor {code}")
    connection.execute("""INSERT INTO user_xfactor_items(user_id,xfactor_id,quantity) VALUES(?,?,?) ON CONFLICT(user_id,xfactor_id) DO UPDATE SET quantity=quantity+excluded.quantity,updated_at=CURRENT_TIMESTAMP""",(user_id,int(row[0]),quantity))


def _fireside_player_reward(connection:sqlite3.Connection,user_id:int)->dict:
    candidates=[p for p in FIRESIDE_PLAYERS if int(p["weight"])>0]
    chosen=_weighted_choice([(p,float(p["weight"])) for p in candidates])
    cid=fireside_card_id(connection,str(chosen["player_key"]),int(chosen["ovr"]))
    if cid is None: raise RuntimeError("Fireside card missing")
    grant_card(connection,user_id,cid,"fireside-box")
    return {"type":"card","label":f"{chosen['name']} · {chosen['ovr']} OVR","card_id":cid}


def open_box(telegram_id:int,code:str)->tuple[bool,str,list[dict]]:
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        uid=get_user_id_by_telegram(c,telegram_id)
        box=c.execute("SELECT b.*,COALESCE(ub.quantity,0) quantity FROM boxes b LEFT JOIN user_boxes ub ON ub.box_id=b.id AND ub.user_id=? WHERE b.code=? AND b.active=1",(uid or -1,code)).fetchone()
        if uid is None or box is None or int(box["quantity"])<=0: c.rollback();return False,"Этого бокса нет в инвентаре.",[]
        c.execute("UPDATE user_boxes SET quantity=quantity-1,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND box_id=?",(uid,int(box["id"])))
        rewards:list[dict]=[]; guaranteed=0
        if code=="fireside_box":
            state=c.execute("SELECT first_guarantee_used FROM fireside_box_state WHERE user_id=?",(uid,)).fetchone()
            first=not state or not int(state[0])
            if first:
                rewards=[_fireside_player_reward(c,uid)]; guaranteed=1
                c.execute("INSERT INTO fireside_box_state(user_id,first_guarantee_used) VALUES(?,1) ON CONFLICT(user_id) DO UPDATE SET first_guarantee_used=1,updated_at=CURRENT_TIMESTAMP",(uid,))
            else:
                kind=_weighted_choice([("player",25),("last_spark",5),("ordinary_xfactor",15),("rank_point",20),("coins",25),("fireside_collectible",10)])
                if kind=="player": rewards=[_fireside_player_reward(c,uid)]
                elif kind=="last_spark": _grant_xfactor(c,uid,"last_spark"); rewards=[{"type":"xfactor","label":"Last Spark"}]
                elif kind=="ordinary_xfactor":
                    xf=_random_regular_xfactor(c)
                    if xf:_grant_xfactor(c,uid,xf); rewards=[{"type":"xfactor","label":xf.replace('_',' ').title()}]
                elif kind=="rank_point": grant_currency(c,uid,"rank_point",5); rewards=[{"type":"currency","label":"5 Rank Coins"}]
                elif kind=="coins": grant_currency(c,uid,"coins",100000); rewards=[{"type":"currency","label":"100,000 Coins"}]
                else: grant_item(c,uid,"fireside_collectible",1); rewards=[{"type":"item","label":"Fireside Collectible ×1"}]
        elif code=="dead_mans_chest":
            state=c.execute("SELECT pity_counter FROM cursed_mirror_user_state WHERE user_id=?",(uid,)).fetchone(); pity=int(state[0]) if state else 0
            if pity>=5:
                reward=_pirate_card_reward(c,uid); rewards=[reward]; pity=0; guaranteed=1
            else:
                kind=_weighted_choice([("event_card",20),("ordinary_xfactor",12),("coins",37.7),("rank_point",20),("cursed_collectible",10),("premium_pass",0.3)])
                if kind=="event_card": rewards=[_pirate_card_reward(c,uid)]; pity=0
                elif kind=="ordinary_xfactor":
                    xf=_random_regular_xfactor(c)
                    if xf:_grant_xfactor(c,uid,xf); rewards=[{"type":"xfactor","label":xf.replace('_',' ').title()}]
                    pity+=1
                elif kind=="coins": grant_currency(c,uid,"coins",100000); rewards=[{"type":"currency","label":"100,000 Coins"}]; pity+=1
                elif kind=="rank_point": grant_currency(c,uid,"rank_point",5); rewards=[{"type":"currency","label":"5 Rank Coins"}]; pity+=1
                elif kind=="cursed_collectible": grant_item(c,uid,"cursed_collectible",1); rewards=[{"type":"item","label":"Cursed Collectible ×1"}]; pity+=1
                else:
                    c.execute("INSERT INTO fireside_pass_users(user_id,season_points,season_level,premium_unlocked,purchased_at) VALUES(?,0,1,1,CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET premium_unlocked=1,purchased_at=COALESCE(purchased_at,CURRENT_TIMESTAMP),updated_at=CURRENT_TIMESTAMP",(uid,)); rewards=[{"type":"pass","label":"Premium Season Pass"}]; pity+=1
            c.execute("INSERT INTO cursed_mirror_user_state(user_id,pity_counter) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET pity_counter=excluded.pity_counter,updated_at=CURRENT_TIMESTAMP",(uid,pity))
        else:
            specs={
                "ahl_box":(2,1,("ahl",),("default","base-collection"),97),
                "common_box":(3,2,("ahl",),("default","base-collection"),65),
                "elite_box":(4,3,("default","base-collection"),("team-of-week","totw"),85),
            }
            cards_count,res_count,primary,secondary,primary_pct=specs.get(code,(0,0,("default",),("default",),100))
            for _ in range(cards_count):
                cols=primary if random.random()*100<primary_pct else secondary
                card=_random_card(c,cols) or _random_card(c,("default","base-collection","ahl"))
                if card:
                    grant_card(c,uid,int(card["id"]),code); rewards.append({"type":"card","label":f"{card['name']} · {card['overall']} OVR","card_id":int(card["id"])})
            resource_weights={"ahl_box":[("coins",55.5),("fireside_collectible",30),("rank_point",10),("xf",4.5)],"common_box":[("coins",46),("fireside_collectible",30),("rank_point",15),("xf",9)],"elite_box":[("coins",37),("fireside_collectible",30),("rank_point",18),("xf",15)]}[code]
            for _ in range(res_count):
                kind=_weighted_choice(resource_weights)
                if kind=="coins":
                    ranges={"ahl_box":(10000,25000),"common_box":(20000,60000),"elite_box":(50000,150000)}; amount=random.randint(*ranges[code]); grant_currency(c,uid,"coins",amount); rewards.append({"type":"currency","label":f"{amount:,} Coins"})
                elif kind=="rank_point":
                    ranges={"ahl_box":(1,2),"common_box":(2,4),"elite_box":(4,8)}; amount=random.randint(*ranges[code]); grant_currency(c,uid,"rank_point",amount); rewards.append({"type":"currency","label":f"{amount} Rank Coins"})
                elif kind=="fireside_collectible":
                    ranges={"ahl_box":(1,1),"common_box":(1,2),"elite_box":(2,4)}; amount=random.randint(*ranges[code]); grant_item(c,uid,"fireside_collectible",amount); rewards.append({"type":"item","label":f"Fireside Collectible ×{amount}"})
                else:
                    xf=_random_regular_xfactor(c)
                    if xf:_grant_xfactor(c,uid,xf); rewards.append({"type":"xfactor","label":xf.replace('_',' ').title()})
        c.execute("INSERT INTO box_open_history(user_id,box_id,rewards_json,guaranteed) VALUES(?,?,?,?)",(uid,int(box["id"]),json.dumps(rewards,ensure_ascii=False),guaranteed))
        c.commit(); return True,"Бокс открыт.",rewards


def _pirate_card_reward(connection:sqlite3.Connection,user_id:int)->dict:
    row=connection.execute("""SELECT c.id,c.name,c.overall FROM cards c JOIN collections col ON col.id=c.collection_id WHERE col.code='cursed-crew-2026' AND c.active=1 ORDER BY RANDOM() LIMIT 1""").fetchone()
    if not row: raise RuntimeError("Cursed Crew card pool missing")
    grant_card(connection,user_id,int(row[0]),"dead-mans-chest")
    return {"type":"card","label":f"{row[1]} · {row[2]} OVR","card_id":int(row[0])}


def grant_fireside_pass_points(connection: sqlite3.Connection, user_id: int, amount: int) -> None:
    """Add points to the new Fireside track without touching legacy Hockey Pass data."""
    if amount <= 0:
        return
    connection.execute(
        "INSERT OR IGNORE INTO fireside_pass_users(user_id,season_points,season_level,premium_unlocked) VALUES(?,0,1,0)",
        (user_id,),
    )
    row = connection.execute(
        "SELECT season_points FROM fireside_pass_users WHERE user_id=?",
        (user_id,),
    ).fetchone()
    current = int(row[0] or 0) if row else 0
    new_points = current + int(amount)
    connection.execute(
        "UPDATE fireside_pass_users SET season_points=?,season_level=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
        (new_points, calculate_pass_level(new_points), user_id),
    )


def _ensure_fireside_pass_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    connection.execute(
        "INSERT OR IGNORE INTO fireside_pass_users(user_id,season_points,season_level,premium_unlocked) VALUES(?,0,1,0)",
        (user_id,),
    )
    return connection.execute(
        "SELECT season_points,season_level,premium_unlocked FROM fireside_pass_users WHERE user_id=?",
        (user_id,),
    ).fetchone()


def pass_status(telegram_id:int)->dict|None:
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:return None
        ps=_ensure_fireside_pass_user(c,uid)
        points=int(ps[0] or 0); level=calculate_pass_level(points)
        if int(ps[1] or 1)!=level:
            c.execute("UPDATE fireside_pass_users SET season_level=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",(level,uid));c.commit()
        premium=bool(int(ps[2] or 0))
        claims={(int(r[0]),str(r[1])) for r in c.execute("SELECT level,track FROM fireside_pass_claims WHERE user_id=?",(uid,))}
        return {"user_id":uid,"bp_points":points,"level":level,"premium":premium,"claims":claims,"energy":currency_balance(c,uid,"energy")}


def purchase_fireside_pass(telegram_id:int)->tuple[bool,str]:
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE"); uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:c.rollback();return False,"Профиль не найден."
        row=_ensure_fireside_pass_user(c,uid)
        if row and int(row[2]):c.rollback();return False,"Premium Pass уже активирован."
        bal=currency_balance(c,uid,"energy")
        if bal<PASS_PREMIUM_PRICE_ENERGY:c.rollback();return False,f"Нужно {PASS_PREMIUM_PRICE_ENERGY} Energy."
        c.execute("UPDATE currency_balances SET amount=amount-?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND currency_code='energy'",(PASS_PREMIUM_PRICE_ENERGY,uid))
        c.execute("UPDATE fireside_pass_users SET premium_unlocked=1,purchased_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",(uid,));c.commit();return True,"Premium Fireside Pass активирован."


def _reward_for(level:int,track:str)->tuple[str,str,int]|None:
    row=next((r for r in FIRESIDE_PASS_REWARDS if r[0]==level),None)
    if not row:return None
    return (str(row[1]),str(row[2]),int(row[3])) if track=='free' else (str(row[4]),str(row[5]),int(row[6]))


def reward_label(level:int,track:str)->str:
    reward=_reward_for(level,track)
    if not reward:return "—"
    kind,code,amount=reward
    if kind=='currency':return f"{amount:,} {'Coins' if code=='coins' else 'Rank Coins'}".replace(',',' ')
    if kind=='item':return f"Fireside Collectible ×{amount}"
    if kind=='box':return {'ahl_box':'AHL Box','common_box':'Common Box','elite_box':'Elite Box','fireside_box':'Fireside Box'}.get(code,code)
    if kind=='xfactor':return 'Ordinary X-Factor' if code=='ordinary_random' else {'firescore':'Firescore','heatwave':'Heatwave'}.get(code,code)
    if kind=='bundle':return 'Cole Caufield 100 + Fireside Box'
    return code


def claim_pass_reward(telegram_id:int,level:int,track:str)->tuple[bool,str]:
    if track not in ('free','premium') or not 1<=level<=30:return False,"Неверная награда."
    reward=_reward_for(level,track)
    if not reward:return False,"Награда не найдена."
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:c.rollback();return False,"Профиль не найден."
        pass_row=_ensure_fireside_pass_user(c,uid); user_level=calculate_pass_level(int(pass_row[0] or 0))
        if user_level<level:c.rollback();return False,"Этот уровень ещё не открыт."
        if track=='premium':
            row=c.execute("SELECT premium_unlocked FROM fireside_pass_users WHERE user_id=?",(uid,)).fetchone()
            if not row or not int(row[0]):c.rollback();return False,"Нужен Premium Pass."
        exists=c.execute("SELECT 1 FROM fireside_pass_claims WHERE user_id=? AND level=? AND track=?",(uid,level,track)).fetchone()
        if exists:c.rollback();return False,"Награда уже получена."
        kind,code,amount=reward
        if kind=='currency':grant_currency(c,uid,code,amount)
        elif kind=='item':grant_item(c,uid,code,amount)
        elif kind=='box':grant_box(c,uid,code,amount)
        elif kind=='xfactor':
            xf=_random_regular_xfactor(c) if code=='ordinary_random' else code
            if xf:_grant_xfactor(c,uid,xf,amount)
        elif kind=='bundle':
            cid=fireside_card_id(c,"cole caufield",100)
            if cid is None:c.rollback();return False,"Cole Caufield 100 не найден в базе."
            grant_card(c,uid,cid,"fireside-pass-30");grant_box(c,uid,"fireside_box",1)
        c.execute("INSERT INTO fireside_pass_claims(user_id,level,track) VALUES(?,?,?)",(uid,level,track));c.commit();return True,f"Получено: {reward_label(level,track)}"


def create_energy_order(telegram_id:int,quantity:int)->tuple[bool,str,int|None]:
    """Manual-contact purchase mode until a payment provider is connected.

    This endpoint intentionally never credits Energy and does not create a fake
    paid order. Administrators credit confirmed payments via Admin Wallets.
    """
    try:
        discount=energy_discount(quantity); price=energy_price_rub(quantity)
    except ValueError as exc:
        return False,str(exc),None
    return False,(f"{quantity:,} Energy · {price:,} ₽ (скидка {discount}%). Для покупки напишите @teyld.".replace(',', ' ')),None


def list_pending_energy_orders(limit:int=20)->list[sqlite3.Row]:
    with get_connection() as c:return list(c.execute("""SELECT o.*,u.telegram_id,u.nickname FROM energy_purchase_orders o JOIN users u ON u.id=o.user_id WHERE o.status='pending' ORDER BY o.id DESC LIMIT ?""",(limit,)).fetchall())


def confirm_energy_order(order_id:int,admin_telegram_id:int,confirm:bool=True)->tuple[bool,str]:
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");row=c.execute("SELECT * FROM energy_purchase_orders WHERE id=?",(order_id,)).fetchone()
        if not row or str(row['status'])!='pending':c.rollback();return False,"Заявка уже обработана или не найдена."
        if confirm:
            grant_currency(c,int(row['user_id']),'energy',int(row['energy_amount']));status='confirmed';msg=f"Начислено {int(row['energy_amount']):,} Energy.".replace(',',' ')
        else:status='cancelled';msg='Заявка отменена.'
        c.execute("UPDATE energy_purchase_orders SET status=?,confirmed_by_telegram_id=?,confirmed_at=CURRENT_TIMESTAMP WHERE id=?",(status,admin_telegram_id,order_id));c.commit();return True,msg


def hero_available(hero_key:str,now:datetime|None=None)->bool:
    hero=next((h for h in HEROES if h['key']==hero_key),None)
    if not hero:return False
    release=HEROES_PART1_AT if int(hero['part'])==1 else HEROES_PART2_AT
    return (now or now_moscow())>=release


def unlock_hero(telegram_id:int,hero_key:str)->tuple[bool,str]:
    if not hero_available(hero_key):return False,"Эта часть HEROES ещё не открылась."
    ids=None
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:c.rollback();return False,"Профиль не найден."
        if c.execute("SELECT 1 FROM heroes_user_paths WHERE user_id=? AND hero_key=?",(uid,hero_key)).fetchone():c.rollback();return False,"Путь этого героя уже открыт."
        if currency_balance(c,uid,'coins')<100000:c.rollback();return False,"Нужно 100 000 Coins."
        ids=hero_card_ids(c,hero_key)
        if not ids:c.rollback();return False,"Карты HEROES не найдены."
        card94,card100=ids;c.execute("UPDATE currency_balances SET amount=amount-100000,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND currency_code='coins'",(uid,));ucid=grant_card(c,uid,card94,f"heroes:{hero_key}:unlock")
        c.execute("INSERT INTO heroes_user_paths(user_id,hero_key,starter_user_card_id,card94_id,card100_id) VALUES(?,?,?,?,?)",(uid,hero_key,ucid,card94,card100))
        c.executemany("INSERT INTO heroes_chapter_progress(user_id,hero_key,chapter) VALUES(?,?,?)",[(uid,hero_key,n) for n in range(1,7)]);c.commit();return True,"HEROES 94 получен. Глава I открыта."


def hero_paths(telegram_id:int)->list[dict]:
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:return []
        rows={str(r['hero_key']):r for r in c.execute("SELECT * FROM heroes_user_paths WHERE user_id=?",(uid,))}
        result=[]
        for h in HEROES:
            p=rows.get(str(h['key']));ch=None
            if p:
                ch=c.execute("SELECT * FROM heroes_chapter_progress WHERE user_id=? AND hero_key=? AND chapter=?",(uid,str(h['key']),int(p['current_chapter']))).fetchone()
            result.append({"hero":h,"available":hero_available(str(h['key'])),"path":p,"chapter":ch})
        return result


def claim_hero_100(telegram_id:int,hero_key:str)->tuple[bool,str]:
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:c.rollback();return False,"Профиль не найден."
        p=c.execute("SELECT * FROM heroes_user_paths WHERE user_id=? AND hero_key=?",(uid,hero_key)).fetchone()
        if not p or int(p['claimed_100']):c.rollback();return False,"Награда недоступна."
        done=int(c.execute("SELECT COUNT(*) FROM heroes_chapter_progress WHERE user_id=? AND hero_key=? AND completed=1",(uid,hero_key)).fetchone()[0])
        if done<6:c.rollback();return False,"Сначала закончи все 6 глав."
        updated=c.execute("UPDATE user_cards SET card_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND card_id=?",(int(p['card100_id']),int(p['starter_user_card_id']),uid,int(p['card94_id'])))
        if updated.rowcount!=1:c.rollback();return False,"Исходная HEROES 94 не найдена."
        c.execute("UPDATE heroes_user_paths SET claimed_100=1,completed_at=CURRENT_TIMESTAMP WHERE user_id=? AND hero_key=?",(uid,hero_key));c.commit();return True,"Та же карта эволюционировала до HEROES 100 OVR."


def _stable_chance(match_id:int,hero_key:str,label:str,percent:int)->bool:
    digest=hashlib.sha256(f"{match_id}:{hero_key}:{label}".encode()).digest();return int.from_bytes(digest[:4],'big')%100<percent


def process_heroes_normal_match(connection:sqlite3.Connection,*,user_id:int,match_id:int,lineup_cards:list,user_score:int,opponent_score:int,is_win:bool,periods:list,events:list)->None:
    if connection.execute("SELECT 1 FROM heroes_processed_matches WHERE user_id=? AND match_id=?",(user_id,match_id)).fetchone():return
    connection.execute("INSERT INTO heroes_processed_matches(user_id,match_id) VALUES(?,?)",(user_id,match_id))
    lineup_by_id={int(getattr(card,'user_card_id',0)):card for card in lineup_cards or []}
    paths=connection.execute("SELECT * FROM heroes_user_paths WHERE user_id=? AND claimed_100=0",(user_id,)).fetchall()
    for p in paths:
        starter=int(p['starter_user_card_id'])
        if starter not in lineup_by_id:continue
        key=str(p['hero_key']); chapter=int(p['current_chapter']); defs=HERO_CHAPTERS.get(key)
        if not defs or chapter>6:continue
        definition=defs[chapter-1];card=lineup_by_id[starter];name=str(getattr(card,'name',''))
        hero_goals=sum(1 for e in events or [] if getattr(e,'event_type','')=='GOAL' and name and name.lower() in str(getattr(e,'description','')).lower())
        team_goals=max(0,int(user_score)); teammate_goals=max(0,team_goals-hero_goals)
        assists=sum(1 for i in range(teammate_goals) if _stable_chance(match_id,key,f"assist:{i}",45))
        points=hero_goals+assists
        shots=max(hero_goals, sum(int(getattr(x,'user_shots',0)) for x in periods or [])//max(1,len([c for c in lineup_cards if getattr(c,'position','')!='G']))) if getattr(card,'position','')!='G' else 0
        opponent_shots=sum(int(getattr(x,'opponent_shots',0)) for x in periods or [])
        hits=sum(1 for e in events or [] if getattr(e,'event_type','')=='BIG HIT' and _stable_chance(match_id,key,str(getattr(e,'time_text','')),50)) if getattr(card,'position','')!='G' else 0
        blocks=(opponent_shots//8)+(1 if _stable_chance(match_id,key,'blocks',50) else 0) if getattr(card,'position','')=='D' else 0
        metric=str(definition['metric']);delta=0;streak=int(p['streak_value'])
        if metric=='shots':delta=shots
        elif metric=='goals':delta=hero_goals
        elif metric=='assists':delta=assists
        elif metric=='points':delta=points
        elif metric=='multi_goal_games':delta=1 if hero_goals>=2 else 0
        elif metric=='hat_tricks':delta=1 if hero_goals>=3 else 0
        elif metric=='game_winning_goals':delta=1 if is_win and hero_goals>0 and user_score>opponent_score else 0
        elif metric=='wins':delta=1 if is_win else 0
        elif metric=='wins_with_point':delta=1 if is_win and points>0 else 0
        elif metric=='low_ga_games':delta=1 if opponent_score<=2 else 0
        elif metric=='shutouts':delta=1 if is_win and opponent_score==0 else 0
        elif metric=='saves':delta=opponent_shots if getattr(card,'position','')=='G' else 0
        elif metric=='save_30_games':delta=1 if getattr(card,'position','')=='G' and opponent_shots>=30 else 0
        elif metric=='hits':delta=hits
        elif metric=='blocks':delta=blocks
        elif metric=='point_streak':
            streak=streak+1 if points>0 else 0;delta=streak;connection.execute("UPDATE heroes_user_paths SET streak_value=? WHERE user_id=? AND hero_key=?",(streak,user_id,key))
        elif metric=='win_streak':
            streak=streak+1 if is_win else 0;delta=streak;connection.execute("UPDATE heroes_user_paths SET streak_value=? WHERE user_id=? AND hero_key=?",(streak,user_id,key))
        row=connection.execute("SELECT progress,completed,reward_paid FROM heroes_chapter_progress WHERE user_id=? AND hero_key=? AND chapter=?",(user_id,key,chapter)).fetchone()
        old=int(row['progress']);target=int(definition['target']);new=max(old,delta) if metric in ('point_streak','win_streak') else old+delta;complete=new>=target
        connection.execute("UPDATE heroes_chapter_progress SET progress=?,completed=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND hero_key=? AND chapter=?",(new,1 if complete else 0,user_id,key,chapter))
        if complete:
            reward=int(definition['reward'])
            if reward>0 and not int(row['reward_paid']):grant_currency(connection,user_id,'coins',reward);connection.execute("UPDATE heroes_chapter_progress SET reward_paid=1 WHERE user_id=? AND hero_key=? AND chapter=?",(user_id,key,chapter))
            if chapter<6:connection.execute("UPDATE heroes_user_paths SET current_chapter=?,streak_value=0 WHERE user_id=? AND hero_key=?",(chapter+1,user_id,key))


def achievement_status(telegram_id:int)->list[dict]:
    defs=(('unique100','Коллекционер','100 уникальных карт',250000,0),('ovr100','100 OVR','Получить карту 100+ OVR',1000000,5),('matches10000','Ветеран','10 000 матчей',5000000,25))
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:return []
        unique=int(c.execute("SELECT COUNT(*) FROM achievement_card_history WHERE user_id=?",(uid,)).fetchone()[0]);ovr=int(c.execute("""SELECT COUNT(*) FROM achievement_card_history h JOIN cards c ON c.id=h.card_id WHERE h.user_id=? AND c.overall>=100""",(uid,)).fetchone()[0]);matches=int(c.execute("SELECT matches_played FROM users WHERE id=?",(uid,)).fetchone()[0]);claimed={str(r[0]) for r in c.execute("SELECT achievement_code FROM achievement_claims WHERE user_id=?",(uid,))}
        values={'unique100':(unique,100),'ovr100':(ovr,1),'matches10000':(matches,10000)}
        return [{'code':code,'title':title,'description':desc,'coins':coins,'rank':rank,'progress':values[code][0],'target':values[code][1],'claimed':code in claimed} for code,title,desc,coins,rank in defs]


def claim_achievement(telegram_id:int,code:str)->tuple[bool,str]:
    statuses={x['code']:x for x in achievement_status(telegram_id)};a=statuses.get(code)
    if not a:return False,"Достижение не найдено."
    if a['claimed']:return False,"Награда уже получена."
    if int(a['progress'])<int(a['target']):return False,"Условие ещё не выполнено."
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:c.rollback();return False,"Профиль не найден."
        try:c.execute("INSERT INTO achievement_claims(user_id,achievement_code) VALUES(?,?)",(uid,code))
        except sqlite3.IntegrityError:c.rollback();return False,"Награда уже получена."
        grant_currency(c,uid,'coins',int(a['coins']));grant_currency(c,uid,'rank_point',int(a['rank']));c.commit()
    return True,"Награда достижения получена."


def fireside_recipes(telegram_id:int)->list[dict]:
    costs={95:3,96:4,97:5,98:6,99:8}
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:return []
        qty=item_quantity(c,uid,'fireside_collectible');out=[]
        for p in FIRESIDE_PLAYERS:
            ovr=int(p['ovr'])
            if ovr>=100:continue
            cid=fireside_card_id(c,str(p['player_key']),ovr);need_ovr=ovr-2;owned=int(c.execute("""SELECT COUNT(*) FROM user_cards uc JOIN cards c ON c.id=uc.card_id WHERE uc.user_id=? AND c.overall=? AND uc.trade_locked=0""",(uid,need_ovr)).fetchone()[0])
            out.append({'name':p['name'],'overall':ovr,'card_id':cid,'required_ovr':need_ovr,'collectibles':costs[ovr],'owned_material_cards':owned,'collectible_balance':qty})
        return out


def craft_fireside(telegram_id:int,target_card_id:int,material_user_card_id:int)->tuple[bool,str]:
    costs={95:3,96:4,97:5,98:6,99:8}
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");uid=get_user_id_by_telegram(c,telegram_id)
        target=c.execute("""SELECT c.id,c.name,c.overall FROM cards c JOIN collections col ON col.id=c.collection_id WHERE c.id=? AND col.code='fireside-2026'""",(target_card_id,)).fetchone()
        if uid is None or not target or int(target['overall'])>=100:c.rollback();return False,"Этот Fireside-крафт недоступен."
        cost=costs.get(int(target['overall']));material=c.execute("""SELECT uc.id,uc.is_in_lineup,uc.trade_locked,c.overall,c.name FROM user_cards uc JOIN cards c ON c.id=uc.card_id WHERE uc.id=? AND uc.user_id=?""",(material_user_card_id,uid)).fetchone()
        if not cost or not material or int(material['trade_locked']) or int(material['overall'])!=int(target['overall'])-2:c.rollback();return False,"Нужна доступная карта ровно на 2 OVR ниже."
        if not consume_item(c,uid,'fireside_collectible',cost):c.rollback();return False,f"Нужно {cost} Fireside Collectibles."
        c.execute("DELETE FROM user_cards WHERE id=? AND user_id=?",(material_user_card_id,uid));grant_card(c,uid,int(target['id']),'fireside-craft');c.execute("INSERT INTO fireside_craft_log(user_id,target_card_id,consumed_user_card_id,collectible_cost) VALUES(?,?,?,?)",(uid,int(target['id']),material_user_card_id,cost));c.commit();return True,f"Создан {target['name']} · {target['overall']} OVR."


def fireside_material_cards(telegram_id:int,target_card_id:int)->list[sqlite3.Row]:
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id);target=c.execute("SELECT overall FROM cards WHERE id=?",(target_card_id,)).fetchone()
        if uid is None or not target:return []
        return list(c.execute("""SELECT uc.id user_card_id,c.name,c.overall,c.collection_id FROM user_cards uc JOIN cards c ON c.id=uc.card_id WHERE uc.user_id=? AND c.overall=? AND uc.trade_locked=0 ORDER BY uc.is_in_lineup ASC,c.name LIMIT 30""",(uid,int(target[0])-2)).fetchall())


def pirates_phase(now:datetime|None=None)->str:
    n=now or now_moscow()
    if n<PIRATES_START_AT:return 'coming'
    if n>PIRATES_END_AT:return 'ended'
    return 'active'


def cursed_state(telegram_id:int)->dict|None:
    today=now_moscow().date().isoformat()
    with get_connection() as c:
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:return None
        daily=c.execute("SELECT wins,box_granted FROM cursed_mirror_daily WHERE user_id=? AND moscow_date=?",(uid,today)).fetchone();wins=int(daily[0]) if daily else 0
        pity=c.execute("SELECT pity_counter FROM cursed_mirror_user_state WHERE user_id=?",(uid,)).fetchone();mirrors=list(c.execute("SELECT * FROM cursed_mirror_cards WHERE user_id=? AND matches_left>0 ORDER BY id DESC",(uid,)).fetchall())
        return {'user_id':uid,'phase':pirates_phase(),'wins':wins,'pity':int(pity[0]) if pity else 0,'mirrors':mirrors,'collectibles':item_quantity(c,uid,'cursed_collectible')}


def _opponent_cards(connection:sqlite3.Connection)->list[dict]:
    result=[]
    for pos,count in (('F',3),('D',2),('G',1)):
        rows=connection.execute("SELECT id,name,position,overall FROM cards WHERE active=1 AND position=? AND overall BETWEEN 92 AND 100 ORDER BY RANDOM() LIMIT ?",(pos,count)).fetchall()
        result.extend({'card_id':int(r[0]),'name':str(r[1]),'position':str(r[2]),'overall':int(r[3])} for r in rows)
    return result



async def play_cursed_match(telegram_id:int)->tuple[bool,str,dict|None]:
    if pirates_phase()!='active':
        return False,"Cursed Mirror сейчас недоступен.",None
    from app.services import match_guard
    from app.services.lineup import get_lineup_overview
    from app.services.matches import build_simulation

    with get_connection() as c:
        profile_uid=get_user_id_by_telegram(c,telegram_id)
    if profile_uid is None:
        return False,"Профиль не найден.",None

    lock=await match_guard.acquire_player_match_lock(profile_uid,"cursed_mirror")
    if not lock.acquired:
        return False,"У вас уже есть активный матч. Дождитесь его завершения.",None

    try:
        overview=await get_lineup_overview(profile_uid)
        if not overview.is_complete:
            await match_guard.cancel_match(profile_uid,reason="CURSED_LINEUP_INCOMPLETE")
            return False,"Для ивент-матча нужен полный состав.",None
        lineup=[card for card in overview.slots.values() if card is not None]
        with get_connection() as c:
            opponents=_opponent_cards(c)
        if len(opponents)<6:
            await match_guard.cancel_match(profile_uid,reason="CURSED_NO_OPPONENT")
            return False,"Не удалось собрать соперника.",None
        opponent_ovr=round(sum(int(x['overall']) for x in opponents)/len(opponents))
        user_ovr=int(overview.final_overall or overview.average_overall or 0)
        score,opp_score,_,_,periods,events=build_simulation(user_ovr,opponent_ovr,lineup,'Cursed Crew',use_xfactors=False)
        is_win=score>opp_score
        today=now_moscow().date().isoformat()
        drop=False
        box_granted=False
        with get_connection() as c:
            c.execute("BEGIN IMMEDIATE")
            # Time is checked again inside the write transaction to prevent a reward after event close.
            if pirates_phase()!='active':
                c.rollback()
                await match_guard.cancel_match(profile_uid,reason="CURSED_EVENT_CLOSED")
                return False,"Cursed Mirror уже завершён.",None
            c.execute("UPDATE cursed_mirror_cards SET matches_left=matches_left-1 WHERE user_id=? AND matches_left>0",(profile_uid,))
            c.execute("DELETE FROM cursed_mirror_cards WHERE user_id=? AND matches_left<=0",(profile_uid,))
            cur=c.execute(
                "INSERT INTO cursed_mirror_matches(user_id,result,user_score,opponent_score,opponent_name,opponent_cards_json,mirror_claimed) VALUES(?,?,?,?,?,?,0)",
                (profile_uid,'win' if is_win else 'loss',score,opp_score,'Cursed Crew',json.dumps(opponents,ensure_ascii=False)),
            )
            match_id=int(cur.lastrowid)
            row=c.execute("SELECT wins,box_granted FROM cursed_mirror_daily WHERE user_id=? AND moscow_date=?",(profile_uid,today)).fetchone()
            wins_before=int(row[0]) if row else 0
            claimed=int(row[1]) if row else 0
            wins_after=min(6,wins_before+(1 if is_win else 0))
            c.execute(
                "INSERT INTO cursed_mirror_daily(user_id,moscow_date,wins,box_granted) VALUES(?,?,?,?) ON CONFLICT(user_id,moscow_date) DO UPDATE SET wins=excluded.wins,box_granted=excluded.box_granted",
                (profile_uid,today,wins_after,claimed),
            )
            if is_win and wins_after>=6 and not claimed:
                grant_box(c,profile_uid,'dead_mans_chest',1)
                c.execute("UPDATE cursed_mirror_daily SET box_granted=1 WHERE user_id=? AND moscow_date=?",(profile_uid,today))
                box_granted=True
            # Post-match collectible rolls only while the 6/6 bar is not full.
            if wins_after<6 and random.random()<0.03:
                grant_item(c,profile_uid,'cursed_collectible',1)
                drop=True
            c.commit()
        await match_guard.finalize_match(profile_uid,match_id=match_id,reason="CURSED_COMPLETED")
        return True,"Победа!" if is_win else "Поражение.",{
            'match_id':match_id,'win':is_win,'score':score,'opponent_score':opp_score,
            'opponent_cards':opponents if is_win else [],'wins':wins_after,
            'collectible_drop':drop,'box_granted':box_granted,
        }
    except Exception:
        await match_guard.cancel_match(profile_uid,reason="CURSED_ERROR")
        raise


def add_mirror_card(telegram_id:int,match_id:int,source_card_id:int,replace_mirror_id:int|None=None)->tuple[bool,str]:
    if pirates_phase()!='active':
        return False,"Cursed Mirror сейчас недоступен."
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None:
            c.rollback();return False,"Профиль не найден."
        match=c.execute(
            "SELECT result,opponent_cards_json,mirror_claimed FROM cursed_mirror_matches WHERE id=? AND user_id=?",
            (match_id,uid),
        ).fetchone()
        if not match or str(match['result'])!='win' or int(match['mirror_claimed']):
            c.rollback();return False,"Mirror-награда этого матча уже недоступна."
        try:
            candidates=json.loads(str(match['opponent_cards_json'] or '[]'))
        except json.JSONDecodeError:
            candidates=[]
        allowed={int(x.get('card_id',0)) for x in candidates if isinstance(x,dict)}
        if source_card_id not in allowed:
            c.rollback();return False,"Этой карты не было в составе соперника."
        card=c.execute("SELECT id,name,position,overall FROM cards WHERE id=? AND active=1",(source_card_id,)).fetchone()
        if not card:
            c.rollback();return False,"Карта не найдена."
        count=int(c.execute("SELECT COUNT(*) FROM cursed_mirror_cards WHERE user_id=? AND matches_left>0",(uid,)).fetchone()[0])
        if count>=3:
            if replace_mirror_id is None:
                c.rollback();return False,"replace_required"
            deleted=c.execute("DELETE FROM cursed_mirror_cards WHERE id=? AND user_id=? AND matches_left>0",(replace_mirror_id,uid))
            if deleted.rowcount!=1:
                c.rollback();return False,"Mirror-карта для замены не найдена."
        c.execute(
            "INSERT INTO cursed_mirror_cards(user_id,source_card_id,name,position,original_ovr,mirrored_ovr,matches_left) VALUES(?,?,?,?,?,?,3)",
            (uid,int(card['id']),str(card['name']),str(card['position']),int(card['overall']),min(110,int(card['overall'])+1)),
        )
        c.execute("UPDATE cursed_mirror_matches SET mirror_claimed=1 WHERE id=? AND user_id=?",(match_id,uid))
        c.commit()
        return True,f"Mirror: {card['name']} · {min(110,int(card['overall'])+1)} OVR · 3 матча."


def exchange_cursed_collectibles(telegram_id:int,player_key:str)->tuple[bool,str]:
    if player_key not in ('joe sakic','henrik lundqvist'):return False,"Можно выбрать только Sakic или Lundqvist."
    with get_connection() as c:
        c.execute("BEGIN IMMEDIATE");uid=get_user_id_by_telegram(c,telegram_id)
        if uid is None or not consume_item(c,uid,'cursed_collectible',4):c.rollback();return False,"Нужно 4 Cursed Collectibles."
        row=c.execute("""SELECT c.id,c.name,c.overall FROM cards c JOIN collections col ON col.id=c.collection_id WHERE col.code='cursed-crew-2026' AND lower(c.player_key)=? AND c.overall=101 LIMIT 1""",(player_key,)).fetchone()
        if not row:c.rollback();return False,"Наградная карта не найдена."
        grant_card(c,uid,int(row[0]),'cursed-collectible-exchange');c.commit();return True,f"Получен {row[1]} · {row[2]} OVR."
