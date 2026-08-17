from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable

from app.database.db import get_connection
from app.services.card_distribution_policy import is_admin_only_card


DNA_COLLECTION_CODE = "dna"
DNA_COLLECTION_NAME = "DNA"
DNA_COLLECTIBLE_CODE = "dna_collectible"
DNA_COLLECTIBLE_TITLE = "DNA Collectible"
DNA_WELCOME_AMOUNT = 1
DNA_STARTER_CHOICE_COST = 3

# Each OVR is a separate catalog card. Existing cards are never upgraded in-place.
DNA_TARGETS: dict[int, tuple[str, ...]] = {
    93: ("YUROV", "MICHKOV"),
    95: ("CAUFIELD", "EICHEL"),
    98: ("SCHEIFELE", "NECAS"),
    100: ("STONE", "HUTSON", "COOLEY", "SCHAEFER"),
}

DNA_COLLECTIBLE_COSTS: dict[int, int] = {93: 5, 95: 10, 98: 20, 100: 50}

# Bundled DNA catalog. These are complete catalog cards, not placeholders: the
# provided 914x1280 visuals ship with the project and are bound to the card rows
# on every startup. OVR never mutates on an owned card; crafting still consumes
# instances and creates a new user_cards row for the target catalog card.
# (player_key, display_name, position, overall, team, country, salary, image_path)
DNA_CARDS: tuple[tuple[str, str, str, int, str, str, int, str], ...] = (
    ("danila-yurov", "Danila Yurov", "F", 93, "Minnesota Wild", "Russia", 6300, "assets/uploads/dna/danila-yurov_93.png"),
    ("matvei-michkov", "Matvei Michkov", "F", 93, "Philadelphia Flyers", "Russia", 6300, "assets/uploads/dna/matvei-michkov_93.png"),
    ("cole-caufield", "Cole Caufield", "F", 95, "Montreal Canadiens", "USA", 7000, "assets/uploads/dna/cole-caufield_95.png"),
    ("jack-eichel", "Jack Eichel", "F", 95, "Vegas Golden Knights", "USA", 7000, "assets/uploads/dna/jack-eichel_95.png"),
    ("mark-scheifele", "Mark Scheifele", "F", 98, "Winnipeg Jets", "Canada", 8200, "assets/uploads/dna/mark-scheifele_98.png"),
    ("martin-necas", "Martin Necas", "F", 98, "Colorado Avalanche", "Czechia", 8200, "assets/uploads/dna/martin-necas_98.png"),
    ("mark-stone", "Mark Stone", "F", 100, "Vegas Golden Knights", "Canada", 9000, "assets/uploads/dna/mark-stone_100.png"),
    ("lane-hutson", "Lane Hutson", "D", 100, "Montreal Canadiens", "USA", 9000, "assets/uploads/dna/lane-hutson_100.png"),
    ("logan-cooley", "Logan Cooley", "F", 100, "Utah Mammoth", "USA", 9000, "assets/uploads/dna/logan-cooley_100.png"),
    ("matthew-schaefer", "Matthew Schaefer", "D", 100, "New York Islanders", "Canada", 9000, "assets/uploads/dna/matthew-schaefer_100.png"),
)

# code -> (min OVR, max OVR, cards consumed, collectibles gained)
DNA_EXTRACTION_RECIPES: dict[str, tuple[int, int, int, int]] = {
    "90_92": (90, 92, 3, 1),
    "93_94": (93, 94, 2, 1),
    "95_96": (95, 96, 1, 2),
    "97": (97, 97, 1, 3),
    "98": (98, 98, 1, 5),
    "99": (99, 99, 1, 10),
}


class DnaCraftError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DnaTargetCard:
    surname: str
    overall: int
    card_id: int | None
    name: str
    position: str
    team: str
    country: str
    image_path: str
    available: bool


@dataclass(frozen=True)
class DnaInventoryProgress:
    next_gen: int
    dna_93: int
    dna_95: int
    dna_98: int
    ovr_92: int
    ovr_94: int
    ovr_97: int
    ovr_99: int
    collectibles: int
    starter_choice_claimed: bool


@dataclass(frozen=True)
class DnaCraftPreview:
    target: DnaTargetCard
    ingredient_text: tuple[str, ...]
    enough: bool
    progress: DnaInventoryProgress


@dataclass(frozen=True)
class DnaCraftResult:
    target: DnaTargetCard
    user_card_id: int
    consumed_user_card_ids: tuple[int, ...]
    consumed_labels: tuple[str, ...]
    collectibles_spent: int


@dataclass(frozen=True)
class DnaExtractionPreview:
    code: str
    min_overall: int
    max_overall: int
    cards_required: int
    collectibles_reward: int
    available_cards: int

    @property
    def can_extract(self) -> bool:
        return self.available_cards >= self.cards_required

    @property
    def ovr_label(self) -> str:
        return str(self.min_overall) if self.min_overall == self.max_overall else f"{self.min_overall}–{self.max_overall}"


@dataclass(frozen=True)
class DnaExtractionResult:
    recipe: DnaExtractionPreview
    consumed_labels: tuple[str, ...]
    collectible_balance: int


@dataclass(frozen=True)
class DnaExtractionCandidate:
    user_card_id: int
    card_id: int
    name: str
    overall: int
    position: str
    team: str
    collection_name: str


@dataclass(frozen=True)
class DnaExtractionCandidatePage:
    recipe: DnaExtractionPreview
    items: tuple[DnaExtractionCandidate, ...]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class DnaChoiceCard:
    card_id: int
    name: str
    overall: int
    position: str
    team: str
    collection_name: str


@dataclass(frozen=True)
class DnaChoicePage:
    items: tuple[DnaChoiceCard, ...]
    page: int
    pages_count: int
    total_count: int
    claimed: bool
    collectibles: int


@dataclass(frozen=True)
class DnaChoiceResult:
    card: DnaChoiceCard
    user_card_id: int
    collectible_balance: int


def _collection_is_dna_sql(alias: str = "collections") -> str:
    return (
        f"(LOWER({alias}.code) = 'dna' OR "
        f"LOWER(REPLACE(REPLACE({alias}.name, ' ', ''), '-', '')) = 'dna')"
    )


def _collection_is_next_gen_sql(alias: str = "collections") -> str:
    return (
        f"(LOWER(REPLACE(REPLACE({alias}.code, '_', '-'), ' ', '-')) IN "
        f"('next-gen', 'nextgen') OR "
        f"LOWER(REPLACE(REPLACE({alias}.name, ' ', ''), '-', '')) = 'nextgen')"
    )


def _target_name_match_sql(alias: str = "cards") -> str:
    return f"(UPPER({alias}.name) = ? OR UPPER({alias}.name) LIKE ?)"


def _resolve_user_id(connection, telegram_id: int) -> int:
    row = connection.execute("SELECT id FROM users WHERE telegram_id = ? LIMIT 1", (telegram_id,)).fetchone()
    if row is None:
        raise DnaCraftError("USER_NOT_FOUND", "Открой игру через /start.")
    return int(row["id"])


def _ensure_dna_collection(connection) -> int:
    connection.execute(
        """
        INSERT INTO collections (code, name, description, active, is_exclusive)
        VALUES (?, ?, 'DNA crafting collection: Next Gen → DNA → 100 OVR.', 1, 1)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            active = 1,
            is_exclusive = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (DNA_COLLECTION_CODE, DNA_COLLECTION_NAME),
    )
    row = connection.execute("SELECT id FROM collections WHERE code = ?", (DNA_COLLECTION_CODE,)).fetchone()
    return int(row["id"])


def _seed_dna_cards(connection, collection_id: int) -> None:
    for player_key, name, position, overall, team, country, salary, image_path in DNA_CARDS:
        surname = name.rsplit(" ", 1)[-1]
        row = connection.execute(
            """
            SELECT id
            FROM cards
            WHERE collection_id = ? AND overall = ?
              AND (
                    lower(trim(name)) = lower(trim(?))
                    OR upper(trim(name)) = upper(?)
                    OR upper(trim(name)) LIKE upper(?)
                    OR player_key = ?
                  )
            ORDER BY
                CASE WHEN lower(trim(name)) = lower(trim(?)) THEN 0
                     WHEN player_key = ? THEN 1
                     ELSE 2 END,
                id DESC
            LIMIT 1
            """,
            (collection_id, overall, name, surname, f"% {surname}", player_key, name, player_key),
        ).fetchone()

        if row is not None:
            connection.execute(
                """
                UPDATE cards
                SET player_key = ?, name = ?, position = ?, team = ?, country = ?,
                    rarity = 'Event', image_path = ?, salary = ?, active = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (player_key, name, position, team, country, image_path, salary, int(row["id"])),
            )
            continue

        connection.execute(
            """
            INSERT INTO cards
                (name, player_key, position, overall, team, country, collection_id,
                 rarity, image_path, salary, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Event', ?, ?, 1)
            """,
            (name, player_key, position, overall, team, country, collection_id, image_path, salary),
        )


def _ensure_dna_collectible(connection) -> int:
    connection.execute(
        """
        INSERT INTO inventory_items (code, title, description, image_path, stackable, active)
        VALUES (?, ?, 'Event crafting material for DNA.', '', 1, 1)
        ON CONFLICT(code) DO UPDATE SET title = excluded.title, active = 1, updated_at = CURRENT_TIMESTAMP
        """,
        (DNA_COLLECTIBLE_CODE, DNA_COLLECTIBLE_TITLE),
    )
    row = connection.execute("SELECT id FROM inventory_items WHERE code = ?", (DNA_COLLECTIBLE_CODE,)).fetchone()
    return int(row["id"])


def seed_dna_content(connection) -> None:
    collection_id = _ensure_dna_collection(connection)
    _ensure_dna_collectible(connection)
    _seed_dna_cards(connection, collection_id)


def _item_quantity(connection, user_id: int, item_id: int) -> int:
    row = connection.execute("SELECT quantity FROM user_items WHERE user_id = ? AND item_id = ?", (user_id, item_id)).fetchone()
    return int(row["quantity"] or 0) if row else 0


def _change_item_quantity(connection, user_id: int, item_id: int, delta: int) -> int:
    current = _item_quantity(connection, user_id, item_id)
    new_value = current + int(delta)
    if new_value < 0:
        raise DnaCraftError("NOT_ENOUGH_COLLECTIBLES", "Не хватает DNA Collectibles.")
    connection.execute(
        """
        INSERT INTO user_items (user_id, item_id, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = excluded.quantity, updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, item_id, new_value),
    )
    return new_value


def claim_dna_welcome_collectible(telegram_id: int) -> tuple[bool, int]:
    """Give exactly one starter collectible on the first DNA visit."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user_id = _resolve_user_id(connection, telegram_id)
        item_id = _ensure_dna_collectible(connection)
        existing = connection.execute("SELECT 1 FROM dna_welcome_grants WHERE user_id = ?", (user_id,)).fetchone()
        granted = existing is None
        if granted:
            _change_item_quantity(connection, user_id, item_id, DNA_WELCOME_AMOUNT)
            connection.execute(
                "INSERT INTO dna_welcome_grants (user_id, collectible_amount) VALUES (?, ?)",
                (user_id, DNA_WELCOME_AMOUNT),
            )
        balance = _item_quantity(connection, user_id, item_id)
        connection.commit()
        return granted, balance


def _find_target_card(connection, surname: str, overall: int) -> DnaTargetCard:
    pattern = f"% {surname.upper()}"
    row = connection.execute(
        f"""
        SELECT cards.id, cards.name, cards.position, cards.overall, cards.team, cards.country, cards.image_path
        FROM cards JOIN collections ON collections.id = cards.collection_id
        WHERE cards.active = 1 AND cards.overall = ? AND {_collection_is_dna_sql()} AND {_target_name_match_sql()}
        ORDER BY CASE WHEN UPPER(cards.name) = ? THEN 0 ELSE 1 END, cards.id DESC LIMIT 1
        """,
        (overall, surname.upper(), pattern, surname.upper()),
    ).fetchone()
    if row is None:
        return DnaTargetCard(surname.upper(), overall, None, surname.title(), "F", "DNA", "", "", False)
    return DnaTargetCard(
        surname=surname.upper(), overall=int(row["overall"]), card_id=int(row["id"]), name=str(row["name"]),
        position=str(row["position"]), team=str(row["team"]), country=str(row["country"]),
        image_path=str(row["image_path"] or ""), available=True,
    )


def get_dna_targets(overall: int | None = None) -> list[DnaTargetCard]:
    tiers: Iterable[int] = [overall] if overall in DNA_TARGETS else DNA_TARGETS.keys()
    result: list[DnaTargetCard] = []
    with get_connection() as connection:
        _ensure_dna_collection(connection)
        _ensure_dna_collectible(connection)
        for tier in tiers:
            for surname in DNA_TARGETS[int(tier)]:
                result.append(_find_target_card(connection, surname, int(tier)))
        connection.commit()
    return result


def get_dna_final_targets() -> list[DnaTargetCard]:
    return get_dna_targets(100)


def _eligible_base_where() -> str:
    return """
        user_cards.user_id = ?
        AND user_cards.is_in_lineup = 0
        AND user_cards.trade_locked = 0
        AND NOT EXISTS (SELECT 1 FROM user_card_frames ucf WHERE ucf.user_card_id = user_cards.id)
        AND NOT EXISTS (SELECT 1 FROM ranked_captains rc WHERE rc.user_card_id = user_cards.id)
        AND NOT EXISTS (
            SELECT 1 FROM trade_offer_cards toc JOIN trade_offers t ON t.id = toc.offer_id
            WHERE toc.user_card_id = user_cards.id AND t.status = 'open'
        )
    """


def _count_eligible(connection, user_id: int, extra_where: str, params: tuple = ()) -> int:
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM user_cards JOIN cards ON cards.id = user_cards.card_id
        JOIN collections ON collections.id = cards.collection_id
        WHERE {_eligible_base_where()} AND ({extra_where})
        """,
        (user_id, *params),
    ).fetchone()
    return int(row["n"] or 0)


def _choice_claimed(connection, user_id: int) -> bool:
    return connection.execute("SELECT 1 FROM dna_choice_claims WHERE user_id = ?", (user_id,)).fetchone() is not None


def _inventory_progress(connection, user_id: int) -> DnaInventoryProgress:
    item_id = _ensure_dna_collectible(connection)
    return DnaInventoryProgress(
        next_gen=_count_eligible(connection, user_id, _collection_is_next_gen_sql()),
        dna_93=_count_eligible(connection, user_id, f"{_collection_is_dna_sql()} AND cards.overall = 93"),
        dna_95=_count_eligible(connection, user_id, f"{_collection_is_dna_sql()} AND cards.overall = 95"),
        dna_98=_count_eligible(connection, user_id, f"{_collection_is_dna_sql()} AND cards.overall = 98"),
        ovr_92=_count_eligible(connection, user_id, "cards.overall = 92"),
        ovr_94=_count_eligible(connection, user_id, "cards.overall = 94"),
        ovr_97=_count_eligible(connection, user_id, "cards.overall = 97"),
        ovr_99=_count_eligible(connection, user_id, "cards.overall = 99"),
        collectibles=_item_quantity(connection, user_id, item_id),
        starter_choice_claimed=_choice_claimed(connection, user_id),
    )


def get_dna_inventory_progress(telegram_id: int) -> DnaInventoryProgress:
    with get_connection() as connection:
        user_id = _resolve_user_id(connection, telegram_id)
        progress = _inventory_progress(connection, user_id)
        connection.commit()
        return progress


def _ingredient_lines(overall: int, progress: DnaInventoryProgress) -> tuple[tuple[str, ...], bool]:
    cost = DNA_COLLECTIBLE_COSTS[overall]
    if overall == 93:
        lines = (
            f"3× любые NEXT GEN  •  есть {progress.next_gen}",
            f"2× любые 92 OVR  •  есть {progress.ovr_92}",
            f"{cost}× DNA Collectible  •  есть {progress.collectibles}",
        )
        enough = progress.next_gen >= 3 and progress.ovr_92 >= 2 and progress.collectibles >= cost
    elif overall == 95:
        lines = (
            f"2× DNA 93 OVR  •  есть {progress.dna_93}",
            f"2× любые 94 OVR  •  есть {progress.ovr_94}",
            f"{cost}× DNA Collectible  •  есть {progress.collectibles}",
        )
        enough = progress.dna_93 >= 2 and progress.ovr_94 >= 2 and progress.collectibles >= cost
    elif overall == 98:
        lines = (
            f"2× DNA 95 OVR  •  есть {progress.dna_95}",
            f"2× любые 97 OVR  •  есть {progress.ovr_97}",
            f"{cost}× DNA Collectible  •  есть {progress.collectibles}",
        )
        enough = progress.dna_95 >= 2 and progress.ovr_97 >= 2 and progress.collectibles >= cost
    elif overall == 100:
        lines = (
            f"1× DNA 98 OVR  •  есть {progress.dna_98}",
            f"3× любые 99 OVR  •  есть {progress.ovr_99}",
            f"{cost}× DNA Collectible  •  есть {progress.collectibles}",
        )
        enough = progress.dna_98 >= 1 and progress.ovr_99 >= 3 and progress.collectibles >= cost
    else:
        raise DnaCraftError("BAD_TIER", "Неизвестный уровень DNA крафта.")
    return lines, enough


def get_dna_craft_preview(telegram_id: int, overall: int, surname: str) -> DnaCraftPreview:
    surname = surname.upper().strip()
    if overall not in DNA_TARGETS or surname not in DNA_TARGETS[overall]:
        raise DnaCraftError("BAD_TARGET", "Эта карта не входит в DNA крафт.")
    with get_connection() as connection:
        user_id = _resolve_user_id(connection, telegram_id)
        target = _find_target_card(connection, surname, overall)
        progress = _inventory_progress(connection, user_id)
        lines, enough = _ingredient_lines(overall, progress)
        if enough:
            selected = _select_inputs(connection, user_id, overall)
            expected = {93: 5, 95: 4, 98: 4, 100: 4}[overall]
            enough = len(selected) == expected and len({int(r["user_card_id"]) for r in selected}) == expected
        connection.commit()
    return DnaCraftPreview(target, lines, enough, progress)


def _select_cards(
    connection, user_id: int, extra_where: str, amount: int, params: tuple = (), exclude_ids: tuple[int, ...] = ()
) -> list:
    exclude_sql = ""
    bind = [user_id, *params]
    if exclude_ids:
        placeholders = ",".join("?" for _ in exclude_ids)
        exclude_sql = f" AND user_cards.id NOT IN ({placeholders})"
        bind.extend(exclude_ids)
    bind.append(amount)
    rows = connection.execute(
        f"""
        SELECT user_cards.id AS user_card_id, cards.id AS card_id, cards.name, cards.overall,
               collections.name AS collection_name, COUNT(*) OVER (PARTITION BY cards.id) AS copies
        FROM user_cards JOIN cards ON cards.id = user_cards.card_id
        JOIN collections ON collections.id = cards.collection_id
        WHERE {_eligible_base_where()} AND ({extra_where}) {exclude_sql}
        ORDER BY cards.overall ASC, copies DESC, user_cards.id ASC LIMIT ?
        """,
        tuple(bind),
    ).fetchall()
    return list(rows)


def _select_inputs(connection, user_id: int, overall: int) -> list:
    if overall == 93:
        next_gen = _select_cards(connection, user_id, _collection_is_next_gen_sql(), 3)
        excluded = tuple(int(row["user_card_id"]) for row in next_gen)
        ovr92 = _select_cards(connection, user_id, "cards.overall = 92", 2, exclude_ids=excluded)
        return [*next_gen, *ovr92]
    if overall == 95:
        return [
            *_select_cards(connection, user_id, f"{_collection_is_dna_sql()} AND cards.overall = 93", 2),
            *_select_cards(connection, user_id, "cards.overall = 94", 2),
        ]
    if overall == 98:
        return [
            *_select_cards(connection, user_id, f"{_collection_is_dna_sql()} AND cards.overall = 95", 2),
            *_select_cards(connection, user_id, "cards.overall = 97", 2),
        ]
    if overall == 100:
        return [
            *_select_cards(connection, user_id, f"{_collection_is_dna_sql()} AND cards.overall = 98", 1),
            *_select_cards(connection, user_id, "cards.overall = 99", 3),
        ]
    raise DnaCraftError("BAD_TIER", "Неизвестный уровень DNA крафта.")


def craft_dna_card(telegram_id: int, overall: int, surname: str) -> DnaCraftResult:
    surname = surname.upper().strip()
    if overall not in DNA_TARGETS or surname not in DNA_TARGETS[overall]:
        raise DnaCraftError("BAD_TARGET", "Эта карта не входит в DNA крафт.")

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            user_id = _resolve_user_id(connection, telegram_id)
            item_id = _ensure_dna_collectible(connection)
            target = _find_target_card(connection, surname, overall)
            if not target.available or target.card_id is None:
                raise DnaCraftError("TARGET_NOT_LOADED", f"{surname} {overall} OVR ещё не загружен в коллекцию DNA.")

            progress = _inventory_progress(connection, user_id)
            _, enough = _ingredient_lines(overall, progress)
            if not enough:
                raise DnaCraftError("NOT_ENOUGH", "Не хватает свободных карт или DNA Collectibles.")

            selected = _select_inputs(connection, user_id, overall)
            expected = {93: 5, 95: 4, 98: 4, 100: 4}[overall]
            if len(selected) != expected or len({int(r['user_card_id']) for r in selected}) != expected:
                raise DnaCraftError("NOT_ENOUGH", "Не хватает свободных карт для этого крафта.")

            consumed_ids = tuple(int(row["user_card_id"]) for row in selected)
            labels = tuple(f"{row['name']} {int(row['overall'])}" for row in selected)
            placeholders = ",".join("?" for _ in consumed_ids)
            actual = connection.execute(
                f"SELECT COUNT(*) AS n FROM user_cards WHERE user_id = ? AND id IN ({placeholders})",
                (user_id, *consumed_ids),
            ).fetchone()
            if int(actual["n"] or 0) != len(consumed_ids):
                raise DnaCraftError("INPUT_CHANGED", "Состав карт изменился. Открой рецепт заново.")

            collectible_cost = DNA_COLLECTIBLE_COSTS[overall]
            _change_item_quantity(connection, user_id, item_id, -collectible_cost)
            connection.execute(f"DELETE FROM user_cards WHERE user_id = ? AND id IN ({placeholders})", (user_id, *consumed_ids))
            cursor = connection.execute(
                "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, ?)",
                (user_id, target.card_id, f"dna_craft_{overall}"),
            )
            new_user_card_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO dna_craft_logs
                    (user_id, target_card_id, target_user_card_id, target_overall, target_surname, consumed_user_card_ids_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, target.card_id, new_user_card_id, overall, surname, json.dumps(consumed_ids)),
            )
            connection.commit()
            return DnaCraftResult(target, new_user_card_id, consumed_ids, labels, collectible_cost)
        except Exception:
            connection.rollback()
            raise


def get_dna_extraction_previews(telegram_id: int) -> tuple[DnaExtractionPreview, ...]:
    with get_connection() as connection:
        user_id = _resolve_user_id(connection, telegram_id)
        result = []
        for code, (min_ovr, max_ovr, required, reward) in DNA_EXTRACTION_RECIPES.items():
            available = _count_eligible(
                connection, user_id,
                f"cards.overall BETWEEN ? AND ? AND NOT ({_collection_is_dna_sql()})",
                (min_ovr, max_ovr),
            )
            result.append(DnaExtractionPreview(code, min_ovr, max_ovr, required, reward, available))
        return tuple(result)


def get_dna_extraction_candidates(
    telegram_id: int, recipe_code: str, page: int = 1, page_size: int = 8
) -> DnaExtractionCandidatePage:
    config = DNA_EXTRACTION_RECIPES.get(recipe_code)
    if config is None:
        raise DnaCraftError("BAD_EXTRACTION", "Неизвестный рецепт переработки.")
    min_ovr, max_ovr, required, reward = config
    page = max(1, int(page))
    page_size = max(1, min(20, int(page_size)))

    with get_connection() as connection:
        user_id = _resolve_user_id(connection, telegram_id)
        extra_where = f"cards.overall BETWEEN ? AND ? AND NOT ({_collection_is_dna_sql()})"
        total = _count_eligible(connection, user_id, extra_where, (min_ovr, max_ovr))
        pages = max(1, math.ceil(total / page_size))
        page = min(page, pages)
        rows = connection.execute(
            f"""
            SELECT user_cards.id AS user_card_id, cards.id AS card_id, cards.name, cards.overall,
                   cards.position, cards.team, collections.name AS collection_name
            FROM user_cards
            JOIN cards ON cards.id = user_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE {_eligible_base_where()} AND ({extra_where})
            ORDER BY cards.overall DESC, cards.name ASC, collections.name ASC, user_cards.id ASC
            LIMIT ? OFFSET ?
            """,
            (user_id, min_ovr, max_ovr, page_size, (page - 1) * page_size),
        ).fetchall()
        items = tuple(
            DnaExtractionCandidate(
                user_card_id=int(row["user_card_id"]),
                card_id=int(row["card_id"]),
                name=str(row["name"]),
                overall=int(row["overall"]),
                position=str(row["position"] or ""),
                team=str(row["team"] or ""),
                collection_name=str(row["collection_name"] or ""),
            )
            for row in rows
        )
        recipe = DnaExtractionPreview(recipe_code, min_ovr, max_ovr, required, reward, total)
        return DnaExtractionCandidatePage(recipe, items, page, pages, total)


def extract_dna_collectibles(
    telegram_id: int, recipe_code: str, user_card_ids: Iterable[int] | None = None
) -> DnaExtractionResult:
    config = DNA_EXTRACTION_RECIPES.get(recipe_code)
    if config is None:
        raise DnaCraftError("BAD_EXTRACTION", "Неизвестный рецепт переработки.")
    min_ovr, max_ovr, required, reward = config

    requested_ids: tuple[int, ...] | None = None
    if user_card_ids is not None:
        requested_ids = tuple(int(value) for value in user_card_ids)
        if len(requested_ids) != required or len(set(requested_ids)) != required:
            raise DnaCraftError(
                "BAD_EXTRACTION_SELECTION",
                f"Нужно выбрать ровно {required} {'карту' if required == 1 else 'карты'} для переработки.",
            )

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            user_id = _resolve_user_id(connection, telegram_id)
            item_id = _ensure_dna_collectible(connection)
            extra_where = f"cards.overall BETWEEN ? AND ? AND NOT ({_collection_is_dna_sql()})"

            if requested_ids is None:
                selected = _select_cards(
                    connection, user_id, extra_where, required, (min_ovr, max_ovr),
                )
            else:
                placeholders = ",".join("?" for _ in requested_ids)
                selected = list(connection.execute(
                    f"""
                    SELECT user_cards.id AS user_card_id, cards.id AS card_id, cards.name, cards.overall,
                           cards.position, cards.team, collections.name AS collection_name
                    FROM user_cards
                    JOIN cards ON cards.id = user_cards.card_id
                    JOIN collections ON collections.id = cards.collection_id
                    WHERE {_eligible_base_where()} AND ({extra_where})
                      AND user_cards.id IN ({placeholders})
                    ORDER BY user_cards.id ASC
                    """,
                    (user_id, min_ovr, max_ovr, *requested_ids),
                ).fetchall())

            if len(selected) != required:
                if requested_ids is not None:
                    raise DnaCraftError(
                        "EXTRACTION_SELECTION_CHANGED",
                        "Одна из выбранных карт уже недоступна: она могла попасть в состав, обмен или быть использована. Выбери карты заново.",
                    )
                raise DnaCraftError("NOT_ENOUGH", "Не хватает свободных карт для переработки.")

            selected_by_id = {int(row["user_card_id"]): row for row in selected}
            if requested_ids is not None and set(selected_by_id) != set(requested_ids):
                raise DnaCraftError(
                    "EXTRACTION_SELECTION_CHANGED",
                    "Одна из выбранных карт больше недоступна. Выбери карты заново.",
                )

            ordered = (
                [selected_by_id[value] for value in requested_ids]
                if requested_ids is not None
                else selected
            )
            ids = tuple(int(row["user_card_id"]) for row in ordered)
            labels = tuple(
                f"{row['name']} {int(row['overall'])} · {row['collection_name']} · #{int(row['user_card_id'])}"
                for row in ordered
            )
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"DELETE FROM user_cards WHERE user_id = ? AND id IN ({placeholders})",
                (user_id, *ids),
            )
            balance = _change_item_quantity(connection, user_id, item_id, reward)
            connection.execute(
                "INSERT INTO dna_extraction_logs (user_id, recipe_code, collectible_amount, consumed_user_card_ids_json) VALUES (?, ?, ?, ?)",
                (user_id, recipe_code, reward, json.dumps(ids)),
            )
            connection.commit()
            preview = DnaExtractionPreview(recipe_code, min_ovr, max_ovr, required, reward, required)
            return DnaExtractionResult(preview, labels, balance)
        except Exception:
            connection.rollback()
            raise


def get_dna_choice_page(telegram_id: int, page: int = 1, page_size: int = 8) -> DnaChoicePage:
    page = max(1, int(page))
    page_size = max(1, min(20, int(page_size)))
    with get_connection() as connection:
        user_id = _resolve_user_id(connection, telegram_id)
        item_id = _ensure_dna_collectible(connection)
        where = f"cards.active = 1 AND cards.overall BETWEEN 95 AND 96 AND collections.active = 1 AND COALESCE(collections.is_exclusive, 0) = 0 AND LOWER(TRIM(collections.name)) != 'leaders' AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders' AND NOT ({_collection_is_dna_sql()})"
        total = int(connection.execute(
            f"SELECT COUNT(*) AS n FROM cards JOIN collections ON collections.id = cards.collection_id WHERE {where}"
        ).fetchone()["n"] or 0)
        pages = max(1, math.ceil(total / page_size))
        page = min(page, pages)
        rows = connection.execute(
            f"""
            SELECT cards.id, cards.name, cards.overall, cards.position, cards.team, collections.name AS collection_name
            FROM cards JOIN collections ON collections.id = cards.collection_id
            WHERE {where}
            ORDER BY cards.overall DESC, cards.name ASC, cards.id ASC LIMIT ? OFFSET ?
            """,
            (page_size, (page - 1) * page_size),
        ).fetchall()
        items = tuple(DnaChoiceCard(int(r['id']), str(r['name']), int(r['overall']), str(r['position']), str(r['team']), str(r['collection_name'])) for r in rows)
        return DnaChoicePage(items, page, pages, total, _choice_claimed(connection, user_id), _item_quantity(connection, user_id, item_id))


def craft_dna_choice_card(telegram_id: int, card_id: int) -> DnaChoiceResult:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            user_id = _resolve_user_id(connection, telegram_id)
            item_id = _ensure_dna_collectible(connection)
            if _choice_claimed(connection, user_id):
                raise DnaCraftError("CHOICE_ALREADY_CLAIMED", "95–96 Choice Craft уже использован на этом аккаунте.")
            row = connection.execute(
                f"""
                SELECT cards.id, cards.name, cards.overall, cards.position, cards.team, collections.name AS collection_name
                FROM cards JOIN collections ON collections.id = cards.collection_id
                WHERE cards.id = ? AND cards.active = 1 AND cards.overall BETWEEN 95 AND 96
                  AND collections.active = 1 AND COALESCE(collections.is_exclusive, 0) = 0
                  AND LOWER(TRIM(collections.name)) != 'leaders'
                  AND LOWER(TRIM(COALESCE(collections.code, ''))) != 'leaders'
                  AND NOT ({_collection_is_dna_sql()})
                LIMIT 1
                """,
                (card_id,),
            ).fetchone()
            if row is None or is_admin_only_card(connection, card_id):
                raise DnaCraftError("BAD_CHOICE", "Эта карта не входит в 95–96 Choice Craft.")
            balance = _change_item_quantity(connection, user_id, item_id, -DNA_STARTER_CHOICE_COST)
            cursor = connection.execute(
                "INSERT INTO user_cards (user_id, card_id, obtained_from) VALUES (?, ?, 'dna_choice_95_96')",
                (user_id, int(row['id'])),
            )
            user_card_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO dna_choice_claims (user_id, card_id, user_card_id, collectible_cost) VALUES (?, ?, ?, ?)",
                (user_id, int(row['id']), user_card_id, DNA_STARTER_CHOICE_COST),
            )
            connection.commit()
            card = DnaChoiceCard(int(row['id']), str(row['name']), int(row['overall']), str(row['position']), str(row['team']), str(row['collection_name']))
            return DnaChoiceResult(card, user_card_id, balance)
        except Exception:
            connection.rollback()
            raise
