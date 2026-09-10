from __future__ import annotations

from dataclasses import dataclass

from app.database.db import get_connection
from app.services.mastery_identity import resolve_mastery_player_key
from app.services.xfactors import grant_xfactor

MASTERY_MAX_POINTS = 1_000_000
MASTERY_WIN_POINTS = 50
MASTERY_LOSS_POINTS = 10


@dataclass(frozen=True)
class MasteryPlayer:
    player_key: str
    name: str
    first_xfactor: str
    second_xfactor: str
    unique_xfactor: str


MASTERY_PLAYERS: tuple[MasteryPlayer, ...] = (
    MasteryPlayer("martin_brodeur", "Martin Brodeur", "sponge", "recharge", "third_defenseman"),
    MasteryPlayer("nicklas_lidstrom", "Nicklas Lidström", "quick_pick", "stick_em_up", "perfect_position"),
    MasteryPlayer("pavel_datsyuk", "Pavel Datsyuk", "elite_edges", "unstoppable", "the_magic_man"),
    MasteryPlayer("jaromir_jagr", "Jaromír Jágr", "big_rig", "unstoppable", "unbreakable_mastery"),
    MasteryPlayer("carey_price", "Carey Price", "show_stopper", "post_to_post", "calm_under_fire"),
    MasteryPlayer("zdeno_chara", "Zdeno Chára", "truculence", "quick_pick", "the_giant"),
    MasteryPlayer("sidney_crosby", "Sidney Crosby", "quick_draw", "tape_to_tape", "complete_player"),
    MasteryPlayer("alexander_ovechkin", "Alexander Ovechkin", "rocket", "one_t", "the_office"),
    MasteryPlayer("joe_sakic", "Joe Sakic", "quick_release", "tape_to_tape", "wrist_shot_legend"),
    MasteryPlayer("henrik_lundqvist", "Henrik Lundqvist", "post_to_post", "dialed_in", "the_king"),
)
MASTER_BY_KEY = {player.player_key: player for player in MASTERY_PLAYERS}


@dataclass(frozen=True)
class MasteryTier:
    points: int
    reward_type: str
    amount: int = 0
    xfactor_slot: int = 0


MASTERY_TIERS: tuple[MasteryTier, ...] = (
    MasteryTier(100, "coins", 25_000),
    MasteryTier(250, "coins", 50_000),
    MasteryTier(500, "coins", 75_000),
    MasteryTier(1_000, "rank_point", 2),
    MasteryTier(2_000, "coins", 100_000),
    MasteryTier(3_500, "coins", 150_000),
    MasteryTier(5_500, "rank_point", 4),
    MasteryTier(8_000, "coins", 200_000),
    MasteryTier(12_000, "coins", 300_000),
    MasteryTier(18_000, "rank_point", 8),
    MasteryTier(27_000, "coins", 400_000),
    MasteryTier(40_000, "coins", 500_000),
    MasteryTier(60_000, "xfactor", xfactor_slot=1),
    MasteryTier(90_000, "rank_point", 15),
    MasteryTier(130_000, "coins", 750_000),
    MasteryTier(180_000, "future"),
    MasteryTier(250_000, "coins", 1_000_000),
    MasteryTier(340_000, "xfactor", xfactor_slot=2),
    MasteryTier(450_000, "rank_point", 30),
    MasteryTier(560_000, "coins", 2_000_000),
    MasteryTier(700_000, "future"),
    MasteryTier(850_000, "combo", 3_000_000),
    MasteryTier(1_000_000, "unique_xfactor"),
)


@dataclass(frozen=True)
class MasteryProgress:
    player: MasteryPlayer
    points: int
    claimed_points: frozenset[int]


@dataclass(frozen=True)
class MasteryClaimResult:
    success: bool
    message: str


def get_mastery_player(player_key: str | None) -> MasteryPlayer | None:
    return MASTER_BY_KEY.get(resolve_mastery_player_key(player_key))


def migrate_mastery_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_player_mastery (
            user_id INTEGER NOT NULL,
            player_key TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0 CHECK(points >= 0 AND points <= 1000000),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, player_key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_mastery_claims (
            user_id INTEGER NOT NULL,
            player_key TEXT NOT NULL,
            tier_points INTEGER NOT NULL,
            claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, player_key, tier_points),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS mastery_match_awards (
            user_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            player_key TEXT NOT NULL,
            points_awarded INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, match_id, player_key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_mastery_progress_user ON user_player_mastery(user_id, points DESC);
        """
    )


def award_mastery_for_match(connection, *, user_id: int, match_id: int, lineup_cards, is_win: bool) -> dict[str, int]:
    """Awards mastery to every eligible unique hockey player in the NORMAL lineup.

    `mastery_match_awards` makes this idempotent per saved match. The game already
    forbids duplicate player_key values in a lineup, but this function also dedupes.
    """
    delta = MASTERY_WIN_POINTS if is_win else MASTERY_LOSS_POINTS
    eligible: dict[str, MasteryPlayer] = {}
    for card in lineup_cards:
        player = get_mastery_player(getattr(card, "player_key", None))
        if player is not None:
            eligible[player.player_key] = player

    awarded: dict[str, int] = {}
    for key in eligible:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO mastery_match_awards(user_id, match_id, player_key, points_awarded)
               VALUES (?, ?, ?, ?)""",
            (user_id, match_id, key, delta),
        )
        if cursor.rowcount == 0:
            continue
        connection.execute(
            """
            INSERT INTO user_player_mastery(user_id, player_key, points)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, player_key) DO UPDATE SET
                points=MIN(1000000, points+excluded.points),
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, key, delta),
        )
        row = connection.execute(
            "SELECT points FROM user_player_mastery WHERE user_id=? AND player_key=?", (user_id, key)
        ).fetchone()
        awarded[key] = int(row["points"])
    return awarded


def get_mastery_progress(user_id: int, player_key: str) -> MasteryProgress | None:
    player = get_mastery_player(player_key)
    if player is None:
        return None
    with get_connection() as connection:
        row = connection.execute(
            "SELECT points FROM user_player_mastery WHERE user_id=? AND player_key=?", (user_id, player.player_key)
        ).fetchone()
        claims = connection.execute(
            "SELECT tier_points FROM user_mastery_claims WHERE user_id=? AND player_key=?",
            (user_id, player.player_key),
        ).fetchall()
    return MasteryProgress(
        player=player,
        points=int(row["points"] if row else 0),
        claimed_points=frozenset(int(item["tier_points"]) for item in claims),
    )


def get_mastery_progress_for_user_card(user_id: int, user_card_id: int) -> MasteryProgress | None:
    with get_connection() as connection:
        row = connection.execute(
            """SELECT cards.player_key FROM user_cards JOIN cards ON cards.id=user_cards.card_id
               WHERE user_cards.id=? AND user_cards.user_id=?""", (user_card_id, user_id)
        ).fetchone()
    return get_mastery_progress(user_id, row["player_key"]) if row else None


def get_user_mastery_overview(user_id: int) -> list[MasteryProgress]:
    return [get_mastery_progress(user_id, player.player_key) for player in MASTERY_PLAYERS]  # type: ignore[list-item]


def xfactor_code_for_tier(player: MasteryPlayer, tier: MasteryTier) -> str | None:
    if tier.reward_type == "xfactor":
        return player.first_xfactor if tier.xfactor_slot == 1 else player.second_xfactor
    if tier.reward_type == "unique_xfactor":
        return player.unique_xfactor
    return None


def reward_label(player: MasteryPlayer, tier: MasteryTier, *, connection=None) -> str:
    if tier.reward_type == "coins":
        return f"{tier.amount:,} Coins".replace(",", " ")
    if tier.reward_type == "rank_point":
        return f"{tier.amount} Rank Coins"
    if tier.reward_type == "combo":
        return f"3 000 000 Coins + 50 Rank Coins"
    if tier.reward_type == "future":
        return "Будущая награда"
    code = xfactor_code_for_tier(player, tier)
    if code:
        owns = connection is None
        conn = connection or get_connection()
        try:
            row = conn.execute("SELECT name FROM xfactors WHERE code=?", (code,)).fetchone()
            name = str(row["name"]) if row else code
        finally:
            if owns:
                conn.close()
        prefix = "👑 " if tier.reward_type == "unique_xfactor" else "⚡ "
        return prefix + name
    return "—"


def claim_mastery_reward(user_id: int, player_key: str, tier_points: int) -> MasteryClaimResult:
    player = get_mastery_player(player_key)
    tier = next((item for item in MASTERY_TIERS if item.points == tier_points), None)
    if player is None or tier is None:
        return MasteryClaimResult(False, "Награда не найдена.")
    if tier.reward_type == "future":
        return MasteryClaimResult(False, "Этот слот зарезервирован под будущую награду.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        progress = connection.execute(
            "SELECT points FROM user_player_mastery WHERE user_id=? AND player_key=?", (user_id, player.player_key)
        ).fetchone()
        points = int(progress["points"] if progress else 0)
        if points < tier.points:
            connection.rollback(); return MasteryClaimResult(False, "Недостаточно очков мастерства.")
        claimed = connection.execute(
            "SELECT 1 FROM user_mastery_claims WHERE user_id=? AND player_key=? AND tier_points=?",
            (user_id, player.player_key, tier.points),
        ).fetchone()
        if claimed:
            connection.rollback(); return MasteryClaimResult(False, "Эта награда уже получена.")

        if tier.reward_type == "coins":
            connection.execute(
                """INSERT INTO currency_balances(user_id,currency_code,amount) VALUES (?, 'coins', ?)
                   ON CONFLICT(user_id,currency_code) DO UPDATE SET amount=amount+excluded.amount, updated_at=CURRENT_TIMESTAMP""",
                (user_id, tier.amount),
            )
        elif tier.reward_type == "rank_point":
            connection.execute(
                """INSERT INTO currency_balances(user_id,currency_code,amount) VALUES (?, 'rank_point', ?)
                   ON CONFLICT(user_id,currency_code) DO UPDATE SET amount=amount+excluded.amount, updated_at=CURRENT_TIMESTAMP""",
                (user_id, tier.amount),
            )
        elif tier.reward_type == "combo":
            connection.execute(
                """INSERT INTO currency_balances(user_id,currency_code,amount) VALUES (?, 'coins', 3000000)
                   ON CONFLICT(user_id,currency_code) DO UPDATE SET amount=amount+3000000, updated_at=CURRENT_TIMESTAMP""",
                (user_id,),
            )
            connection.execute(
                """INSERT INTO currency_balances(user_id,currency_code,amount) VALUES (?, 'rank_point', 50)
                   ON CONFLICT(user_id,currency_code) DO UPDATE SET amount=amount+50, updated_at=CURRENT_TIMESTAMP""",
                (user_id,),
            )
        elif tier.reward_type in ("xfactor", "unique_xfactor"):
            code = xfactor_code_for_tier(player, tier)
            assert code is not None
            grant_xfactor(user_id, code, 1, connection=connection)
        else:
            connection.rollback(); return MasteryClaimResult(False, "Тип награды пока не поддерживается.")

        connection.execute(
            "INSERT INTO user_mastery_claims(user_id, player_key, tier_points) VALUES (?, ?, ?)",
            (user_id, player.player_key, tier.points),
        )
        label = reward_label(player, tier, connection=connection)
        connection.commit()
    return MasteryClaimResult(True, f"Получено: {label}")
