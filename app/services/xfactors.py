from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from app.database.db import get_connection
from app.services.mastery_identity import resolve_mastery_player_key

MAX_XFACTORS_PER_CARD = 3
XFACTOR_QUICKSELL_COINS = 20_000


REGULAR_XFACTORS: tuple[dict[str, object], ...] = (
    {"code":"elite_edges","name":"Elite Edges","role":"F","description":"Shake off opponents with explosive edge work with increased Acceleration and Agility while performing tight turns and sharp direction changes.","icon":"assets/xfactors/regular/elite_edges.jpg"},
    {"code":"quick_draw","name":"Quick Draw","role":"F","description":"Create more opportunities for teammates off the draw with faster faceoff draw wins and allows skill based one-timers right off the faceoff. Unlocks stronger tieup wins which box out opposing players. In this game its battle effect activates only while the card is in the center slot F2.","icon":"assets/xfactors/regular/quick_draw.jpg"},
    {"code":"send_it","name":"Send It","role":"F","description":"Spring your teammates by enhancing that pass receiver with a temporary boost of acceleration. Unlocks the ability for these players to perform automatic saucer passes.","icon":"assets/xfactors/regular/send_it.jpg"},
    {"code":"tape_to_tape","name":"Tape to Tape","role":"F","description":"Feather saucer passes and make snappy passes in and out of vision with increased Pass Power and Accuracy. Unlocks the ability for these players to perform automatic saucer passes.","icon":"assets/xfactors/regular/tape_to_tape.jpg"},
    {"code":"unstoppable","name":"Unstoppable","role":"F","description":"Reverse the fortune on opposing players with stronger reverse hits. Fight through push checks with increased strength and balance.","icon":"assets/xfactors/regular/unstoppable.jpg"},
    {"code":"wheels","name":"Wheels","role":"F","description":"Turn on the jets and blow past opponents after hitting top speed with increased Speed and Acceleration.","icon":"assets/xfactors/regular/wheels.jpg"},
    {"code":"backhand_beauty","name":"Backhand Beauty","role":"F","description":"Catch opposing players and goalies off guard with increased Backhand shot Power and Accuracy. Additionally Backhand Passes are as accurate and powerful as forehand passes.","icon":"assets/xfactors/regular/backhand_beauty.jpg"},
    {"code":"big_rig","name":"Big Rig","role":"F","description":"Protect the puck and drive the net with authority with increased strength, agility and balance. Surprise goalies with enhanced accuracy and power with One Handed Shots. Unlocks enhanced protect puck animations with the ability to fight through stick contact even at extreme angles.","icon":"assets/xfactors/regular/big_rig.jpg"},
    {"code":"big_tipper","name":"Big Tipper","role":"F","description":"Create chaos in front of the net by taking away the goalie's eyes influencing their readiness. Find and redirect the puck easier with increased accuracy on deflections and additional longer ranged animations. Unlocks deflections with increased range.","icon":"assets/xfactors/regular/big_tipper.jpg"},
    {"code":"one_t","name":"One T","role":"F","description":"Become the ultimate threat with increased One T Shot Power and Accuracy. Allowed to be an additional Skill Based One Timer target when open.","icon":"assets/xfactors/regular/one_t.jpg"},
    {"code":"pressure_plus","name":"Pressure+","role":"F","description":"Build up momentum with shots that generate bonus pressure on every save.","icon":"assets/xfactors/regular/pressure_plus.jpg"},
    {"code":"quick_release","name":"Quick Release","role":"F","description":"Get shots off lightning quick with an extra fast shot release. Decrease goalies readiness on both snap shots and wrist shots.","icon":"assets/xfactors/regular/quick_release.jpg"},
    {"code":"rocket","name":"Rocket","role":"F","description":"Slap shots create large rebounds and can cause the goalie to react when hit up high with increases to Slap Shot Accuracy and Power.","icon":"assets/xfactors/regular/rocket.jpg"},
    {"code":"born_leader","name":"Born Leader","role":"D","description":"Rally the team with every action by increasing team energy after every Shot Block, Body Check, or Shot on Net.","icon":"assets/xfactors/regular/born_leader.jpg"},
    {"code":"hipster","name":"Hipster","role":"D","description":"Lay devastating hip checks on players with improved hit power that punish opposing players with increased stamina loss and a slowing lingering effect after a big hit. Perfectly lined up hip checks will cause the opposing player to lose their stick.","icon":"assets/xfactors/regular/hipster.jpg"},
    {"code":"no_contest","name":"No Contest","role":"D","description":"Overpower opposing players with additional stick and arm strength and come out with the puck with increased speed and acceleration.","icon":"assets/xfactors/regular/no_contest.jpg"},
    {"code":"quick_pick","name":"Quick Pick","role":"D","description":"Effortlessly block passing lanes using stick or body to get a piece or intercept the puck clean with additional range and increased puck handling. Unlocks enhanced pickup and interception range with additional skate and stick defensive deflections and interceptions.","icon":"assets/xfactors/regular/quick_pick.jpg"},
    {"code":"second_wind","name":"Second Wind","role":"D","description":"Outlast the opposing team by instantly recovering energy when you become exhausted. Must be recovered back to full to trigger again.","icon":"assets/xfactors/regular/second_wind.jpg"},
    {"code":"spark_plug","name":"Spark Plug","role":"D","description":"Get your team going with body checks that generate additional pressure while also giving a temporary speed and acceleration boost after delivering a hit.","icon":"assets/xfactors/regular/spark_plug.jpg"},
    {"code":"stick_em_up","name":"Stick Em Up","role":"D","description":"Disrupt and separate players from the puck with improved poke check accuracy, recovery and defensive skill stick speed.","icon":"assets/xfactors/regular/stick_em_up.jpg"},
    {"code":"truculence","name":"Truculence","role":"D","description":"Distribute punishing shoulder checks on players with improved hit power that leave opposing players with increased stamina loss and a slowing effect after a big hit. Perfectly lined up shoulder checks will cause the opposing player to lose their stick.","icon":"assets/xfactors/regular/truculence.jpg"},
    {"code":"warrior","name":"Warrior","role":"D","description":"Fight through the pain with reduced stamina penalties when body checked or while blocking shots and shrug off lingering slow effects from big hitters. Unlocks enhanced shot blocking animations, resistant to dropping their stick and makes the player immune to minor injuries.","icon":"assets/xfactors/regular/warrior.jpg"},
    {"code":"dialed_in","name":"Dialed In","role":"G","description":"Keep on a roll with increased save accuracy and reaction time for each save made in a row. Bonus resets after letting in a goal.","icon":"assets/xfactors/regular/dialed_in.jpg"},
    {"code":"post_to_post","name":"Post to Post","role":"G","description":"Stretch post to post to make miraculous cross crease saves with increased speed and improved save accuracy while sliding. Unlocks additional windmill reactions on one-timer saves and eliminates reaction penalties on Perfect One Timers.","icon":"assets/xfactors/regular/post_to_post.jpg"},
    {"code":"recharge","name":"Recharge","role":"G","description":"Fight through pressure by reducing pressure meter gain and fatigue lost on opposing shots and by increasing energy recovery when the puck leaves the offensive zone.","icon":"assets/xfactors/regular/recharge.jpg"},
    {"code":"show_stopper","name":"Show Stopper","role":"G","description":"Utilize catlike reflexes with increase Save Accuracy and Readiness when performing reflex saves and consecutive saves. Increased ability to see through screens and react to deflections.","icon":"assets/xfactors/regular/show_stopper.jpg"},
    {"code":"sponge","name":"Sponge","role":"G","description":"Absorb shots and limit rebound opportunities with an increase ability to acquire the puck on saves and jump on pucks quicker with faster cover speeds. Unlocks additional windmill reactions and eliminates goalie reactions when hit from shots up high.","icon":"assets/xfactors/regular/sponge.jpg"},
)

MASTERY_XFACTORS: tuple[dict[str, object], ...] = (
    {"code":"third_defenseman","name":"Third Defenseman","role":"G","player_key":"martin_brodeur","description":"Take control beyond the crease with elite puck handling and anticipation. Dramatically improves puck recovery, breakout passes and readiness after playing the puck. Reduces dangerous second-chance opportunities after successful saves.","icon":"assets/xfactors/mastery/third_defenseman.jpg"},
    {"code":"perfect_position","name":"Perfect Position","role":"D","player_key":"nicklas_lidstrom","description":"Always be one step ahead with elite defensive positioning and anticipation. Greatly increases interception, shot blocking and puck recovery ability while reducing the effectiveness of opposing cross-ice passes and high-danger chances.","icon":"assets/xfactors/mastery/perfect_position.jpg"},
    {"code":"the_magic_man","name":"The Magic Man","role":"F","player_key":"pavel_datsyuk","description":"Make the impossible look effortless with elite puck control, deception and defensive awareness. Dramatically increases successful dekes, puck protection and takeaways while creating higher-quality chances immediately after stealing the puck.","icon":"assets/xfactors/mastery/the_magic_man.jpg"},
    {"code":"unbreakable_mastery","name":"Unbreakable","role":"F","player_key":"jaromir_jagr","description":"Become nearly impossible to separate from the puck. Gain massive strength, balance and puck protection while under pressure, with increased scoring ability after fighting through physical contact.","icon":"assets/xfactors/mastery/unbreakable.jpg"},
    {"code":"calm_under_fire","name":"Calm Under Fire","role":"G","player_key":"carey_price","description":"Stay composed no matter how intense the pressure becomes. Greatly reduces the effects of screens, rebounds and sustained offensive pressure while increasing save accuracy and readiness on consecutive high-danger chances.","icon":"assets/xfactors/mastery/calm_under_fire.jpg"},
    {"code":"the_giant","name":"The Giant","role":"D","player_key":"zdeno_chara","description":"Control the ice with overwhelming reach and physical strength. Dramatically increases defensive range, shot blocking and body check effectiveness while making opposing players significantly easier to separate from the puck.","icon":"assets/xfactors/mastery/the_giant.jpg"},
    {"code":"complete_player","name":"Complete Player","role":"F","player_key":"sidney_crosby","description":"Elevate every player around you with elite vision and all-around skill. Greatly improves faceoffs, passing and puck protection while temporarily boosting teammates after creating or finishing a high-danger scoring chance.","icon":"assets/xfactors/mastery/complete_player.jpg"},
    {"code":"the_office","name":"The Office","role":"F","player_key":"alexander_ovechkin","description":"Own your scoring territory and punish defenders who leave you open. Dramatically increases shot power and accuracy from prime shooting areas, with an extreme bonus to one-timers from Ovechkin's preferred scoring position.","icon":"assets/xfactors/mastery/the_office.jpg"},
    {"code":"wrist_shot_legend","name":"Wrist Shot Legend","role":"F","player_key":"joe_sakic","description":"Release one of hockey's most dangerous wrist shots with exceptional speed, power and precision. Dramatically increases wrist and snap shot effectiveness and reduces goalie readiness when shooting immediately after receiving a pass.","icon":"assets/xfactors/mastery/wrist_shot_legend.jpg"},
    {"code":"the_king","name":"The King","role":"G","player_key":"henrik_lundqvist","description":"Rule the crease with elite positioning and composure. Gain greatly increased save accuracy and readiness on high-danger shots, with an additional boost when protecting a lead late in the game.","icon":"assets/xfactors/mastery/the_king.jpg"},
)


@dataclass(frozen=True)
class XFactor:
    id: int
    code: str
    name: str
    role: str
    description: str
    icon_path: str
    is_mastery: bool
    mastery_player_key: str | None


@dataclass(frozen=True)
class UserXFactorItem:
    xfactor: XFactor
    quantity: int


@dataclass(frozen=True)
class InstalledXFactor:
    slot_no: int
    xfactor: XFactor


@dataclass(frozen=True)
class XFactorActionResult:
    success: bool
    message: str


def migrate_xfactor_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS xfactors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('F','D','G')),
            description TEXT NOT NULL DEFAULT '',
            icon_path TEXT NOT NULL DEFAULT '',
            is_mastery INTEGER NOT NULL DEFAULT 0,
            mastery_player_key TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_xfactor_items (
            user_id INTEGER NOT NULL,
            xfactor_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, xfactor_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(xfactor_id) REFERENCES xfactors(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_card_xfactors (
            user_card_id INTEGER NOT NULL,
            xfactor_id INTEGER NOT NULL,
            slot_no INTEGER NOT NULL CHECK(slot_no BETWEEN 1 AND 3),
            installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_card_id, slot_no),
            UNIQUE(user_card_id, xfactor_id),
            FOREIGN KEY(user_card_id) REFERENCES user_cards(id) ON DELETE CASCADE,
            FOREIGN KEY(xfactor_id) REFERENCES xfactors(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_user_card_xfactors_card ON user_card_xfactors(user_card_id);
        CREATE INDEX IF NOT EXISTS idx_user_xfactor_items_user ON user_xfactor_items(user_id, quantity);
        """
    )


def seed_xfactors(connection) -> None:
    for item in (*REGULAR_XFACTORS, *MASTERY_XFACTORS):
        is_mastery = "player_key" in item
        connection.execute(
            """
            INSERT INTO xfactors (code, name, role, description, icon_path, is_mastery, mastery_player_key, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                role=excluded.role,
                description=excluded.description,
                icon_path=excluded.icon_path,
                is_mastery=excluded.is_mastery,
                mastery_player_key=excluded.mastery_player_key,
                active=1,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                item["code"], item["name"], item["role"], item["description"], item["icon"],
                1 if is_mastery else 0, item.get("player_key"),
            ),
        )


def _row_to_xfactor(row) -> XFactor:
    return XFactor(
        id=int(row["id"]), code=str(row["code"]), name=str(row["name"]), role=str(row["role"]),
        description=str(row["description"] or ""), icon_path=str(row["icon_path"] or ""),
        is_mastery=bool(row["is_mastery"]), mastery_player_key=row["mastery_player_key"],
    )


def get_xfactor_by_code(code: str) -> XFactor | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM xfactors WHERE code=? AND active=1", (code,)).fetchone()
    return _row_to_xfactor(row) if row else None


def get_installed_xfactors(user_card_id: int) -> list[InstalledXFactor]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT x.*, ucx.slot_no
            FROM user_card_xfactors ucx
            JOIN xfactors x ON x.id=ucx.xfactor_id
            WHERE ucx.user_card_id=?
            ORDER BY ucx.slot_no
            """,
            (user_card_id,),
        ).fetchall()
    return [InstalledXFactor(slot_no=int(row["slot_no"]), xfactor=_row_to_xfactor(row)) for row in rows]


def get_installed_xfactor_codes(user_card_ids: Iterable[int]) -> dict[int, list[str]]:
    ids = sorted({int(v) for v in user_card_ids if int(v) > 0})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT ucx.user_card_id, x.code
            FROM user_card_xfactors ucx JOIN xfactors x ON x.id=ucx.xfactor_id
            WHERE ucx.user_card_id IN ({placeholders})
            ORDER BY ucx.user_card_id, ucx.slot_no
            """, ids,
        ).fetchall()
    result: dict[int, list[str]] = {value: [] for value in ids}
    for row in rows:
        result.setdefault(int(row["user_card_id"]), []).append(str(row["code"]))
    return result


def grant_xfactor(user_id: int, code: str, quantity: int = 1, *, connection=None) -> None:
    if quantity <= 0:
        return
    owns_connection = connection is None
    conn = connection or get_connection()
    try:
        row = conn.execute("SELECT id FROM xfactors WHERE code=? AND active=1", (code,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown X-Factor: {code}")
        conn.execute(
            """
            INSERT INTO user_xfactor_items(user_id, xfactor_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, xfactor_id) DO UPDATE SET
                quantity=quantity+excluded.quantity, updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, int(row["id"]), quantity),
        )
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()


def get_user_xfactor_inventory(user_id: int, page: int = 1, per_page: int = 8) -> tuple[list[UserXFactorItem], int, int, int]:
    with get_connection() as connection:
        total = int(connection.execute(
            "SELECT COUNT(*) AS c FROM user_xfactor_items WHERE user_id=? AND quantity>0", (user_id,)
        ).fetchone()["c"])
        pages = max(1, ceil(total / per_page))
        safe_page = min(max(1, page), pages)
        rows = connection.execute(
            """
            SELECT x.*, u.quantity
            FROM user_xfactor_items u JOIN xfactors x ON x.id=u.xfactor_id
            WHERE u.user_id=? AND u.quantity>0 AND x.active=1
            ORDER BY x.is_mastery DESC, x.name COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, (safe_page-1)*per_page),
        ).fetchall()
    return [UserXFactorItem(_row_to_xfactor(row), int(row["quantity"])) for row in rows], safe_page, pages, total


def get_user_xfactor_quantity(user_id: int, code: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            """SELECT u.quantity FROM user_xfactor_items u JOIN xfactors x ON x.id=u.xfactor_id
               WHERE u.user_id=? AND x.code=?""", (user_id, code)
        ).fetchone()
    return int(row["quantity"]) if row else 0


def _allowed_positions(connection, xfactor_id: int, legacy_role: str) -> tuple[str, ...]:
    table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='xfactor_allowed_positions'").fetchone()
    if table:
        rows = connection.execute("SELECT position FROM xfactor_allowed_positions WHERE xfactor_id=? ORDER BY position", (xfactor_id,)).fetchall()
        if rows:
            return tuple(str(row["position"]) for row in rows)
    return (str(legacy_role),)


def get_eligible_cards_for_xfactor(user_id: int, code: str, limit: int = 30):
    with get_connection() as connection:
        x = connection.execute("SELECT * FROM xfactors WHERE code=? AND active=1", (code,)).fetchone()
        if x is None:
            return []
        positions = _allowed_positions(connection, int(x["id"]), str(x["role"]))
        placeholders = ",".join("?" for _ in positions)
        rows = connection.execute(
            f"""
            SELECT user_cards.id AS user_card_id, cards.name, cards.overall, cards.position, cards.player_key,
                   (SELECT COUNT(*) FROM user_card_xfactors z WHERE z.user_card_id=user_cards.id) AS xfactor_count
            FROM user_cards JOIN cards ON cards.id=user_cards.card_id
            WHERE user_cards.user_id=? AND cards.position IN ({placeholders})
            ORDER BY cards.overall DESC, user_cards.id DESC
            """,
            (user_id, *positions),
        ).fetchall()
    if bool(x["is_mastery"]):
        mastery_key = resolve_mastery_player_key(x["mastery_player_key"])
        rows = [row for row in rows if resolve_mastery_player_key(row["player_key"]) == mastery_key]
    return rows[: max(0, int(limit))]


def install_xfactor(user_id: int, user_card_id: int, code: str, replace_slot: int | None = None) -> XFactorActionResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        x = connection.execute("SELECT * FROM xfactors WHERE code=? AND active=1", (code,)).fetchone()
        card = connection.execute(
            """SELECT user_cards.id, cards.position, cards.player_key FROM user_cards
               JOIN cards ON cards.id=user_cards.card_id WHERE user_cards.id=? AND user_cards.user_id=?""",
            (user_card_id, user_id),
        ).fetchone()
        if x is None or card is None:
            connection.rollback(); return XFactorActionResult(False, "X-Factor или карта не найдены.")
        allowed_positions = _allowed_positions(connection, int(x["id"]), str(x["role"]))
        if str(card["position"]) not in allowed_positions:
            connection.rollback(); return XFactorActionResult(False, "Этот X-Factor не подходит позиции карты.")
        if bool(x["is_mastery"]) and resolve_mastery_player_key(card["player_key"]) != resolve_mastery_player_key(x["mastery_player_key"]):
            connection.rollback(); return XFactorActionResult(False, "Уникальный Mastery X-Factor можно установить только на своего игрока.")
        inv = connection.execute(
            "SELECT quantity FROM user_xfactor_items WHERE user_id=? AND xfactor_id=?", (user_id, int(x["id"]))
        ).fetchone()
        if inv is None or int(inv["quantity"]) <= 0:
            connection.rollback(); return XFactorActionResult(False, "Этого X-Factor нет в инвентаре.")
        duplicate = connection.execute(
            "SELECT 1 FROM user_card_xfactors WHERE user_card_id=? AND xfactor_id=?", (user_card_id, int(x["id"]))
        ).fetchone()
        if duplicate:
            connection.rollback(); return XFactorActionResult(False, "Этот X-Factor уже установлен на карте.")
        installed = connection.execute(
            "SELECT slot_no FROM user_card_xfactors WHERE user_card_id=? ORDER BY slot_no", (user_card_id,)
        ).fetchall()
        occupied = {int(row["slot_no"]) for row in installed}
        if len(occupied) >= MAX_XFACTORS_PER_CARD:
            if replace_slot not in (1,2,3):
                connection.rollback(); return XFactorActionResult(False, "На карте уже 3 X-Factor. Выбери слот для замены.")
            if replace_slot not in occupied:
                connection.rollback(); return XFactorActionResult(False, "Выбранный слот не занят.")
            connection.execute("DELETE FROM user_card_xfactors WHERE user_card_id=? AND slot_no=?", (user_card_id, replace_slot))
            slot = replace_slot
        else:
            # Пока есть свободное место, новый фактор всегда занимает свободный слот.
            # Замена (и уничтожение старого фактора) допустима только при заполненных 3/3.
            slot = next(n for n in (1,2,3) if n not in occupied)
        connection.execute(
            "INSERT INTO user_card_xfactors(user_card_id, xfactor_id, slot_no) VALUES (?, ?, ?)",
            (user_card_id, int(x["id"]), slot),
        )
        connection.execute(
            "UPDATE user_xfactor_items SET quantity=quantity-1, updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND xfactor_id=?",
            (user_id, int(x["id"])),
        )
        connection.commit()
    return XFactorActionResult(True, f"{x['name']} установлен в слот {slot}.")


def remove_installed_xfactor(user_id: int, user_card_id: int, slot_no: int) -> XFactorActionResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT x.name FROM user_card_xfactors ucx JOIN xfactors x ON x.id=ucx.xfactor_id
               JOIN user_cards uc ON uc.id=ucx.user_card_id
               WHERE ucx.user_card_id=? AND ucx.slot_no=? AND uc.user_id=?""",
            (user_card_id, slot_no, user_id),
        ).fetchone()
        if row is None:
            connection.rollback(); return XFactorActionResult(False, "X-Factor не найден на карте.")
        connection.execute("DELETE FROM user_card_xfactors WHERE user_card_id=? AND slot_no=?", (user_card_id, slot_no))
        connection.commit()
    return XFactorActionResult(True, f"{row['name']} снят и уничтожен.")


def quicksell_xfactor(user_id: int, code: str) -> XFactorActionResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT x.id, x.name, x.is_mastery, u.quantity FROM xfactors x
               LEFT JOIN user_xfactor_items u ON u.xfactor_id=x.id AND u.user_id=? WHERE x.code=?""",
            (user_id, code),
        ).fetchone()
        if row is None or int(row["quantity"] or 0) < 1:
            connection.rollback(); return XFactorActionResult(False, "X-Factor отсутствует в инвентаре.")
        if bool(row["is_mastery"]):
            connection.rollback(); return XFactorActionResult(False, "Уникальный Mastery X-Factor нельзя продать.")
        connection.execute("UPDATE user_xfactor_items SET quantity=quantity-1 WHERE user_id=? AND xfactor_id=?", (user_id, int(row["id"])))
        connection.execute(
            """INSERT INTO currency_balances(user_id,currency_code,amount) VALUES (?, 'coins', ?)
               ON CONFLICT(user_id,currency_code) DO UPDATE SET amount=amount+excluded.amount, updated_at=CURRENT_TIMESTAMP""",
            (user_id, XFACTOR_QUICKSELL_COINS),
        )
        connection.commit()
    return XFactorActionResult(True, f"{row['name']} продан за {XFACTOR_QUICKSELL_COINS:,} Coins.".replace(',', ' '))
