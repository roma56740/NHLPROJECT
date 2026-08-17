from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import ceil
from random import SystemRandom

from app.database.db import get_connection
from app.services.admin_cards import clean_search_query


PACK_RANDOM = SystemRandom()
RARITIES = ["Common", "Rare", "Epic", "Legendary", "Event", "Icon"]
DEFAULT_RARITY_CHANCES = {
    "Common": 70,
    "Rare": 20,
    "Epic": 8,
    "Legendary": 2,
}


@dataclass(frozen=True)
class PackInfo:
    id: int
    code: str
    name: str
    description: str
    image_path: str | None
    animation_video_path: str | None
    price_currency_code: str | None
    price_amount: int
    active: bool
    is_shop_available: bool
    is_starter: bool
    cards_count: int
    selected_cards_count: int


@dataclass(frozen=True)
class PackInventoryItem:
    id: int
    code: str
    name: str
    description: str
    image_path: str | None
    quantity: int
    cards_count: int
    selected_cards_count: int


@dataclass(frozen=True)
class PackInventoryPage:
    packs: list[PackInventoryItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class PackRewardItem:
    user_card_id: int
    card_id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    image_path: str


@dataclass(frozen=True)
class PackOpeningResult:
    opening_id: int
    pack_id: int
    pack_code: str
    pack_name: str
    rewards: list[PackRewardItem]


@dataclass(frozen=True)
class PackHistoryItem:
    id: int
    pack_name: str
    rewards_count: int
    created_at: str


@dataclass(frozen=True)
class PackHistoryPage:
    openings: list[PackHistoryItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class PackChoiceItem:
    id: int
    code: str
    name: str
    description: str
    quantity_hint: int
    active: bool


@dataclass(frozen=True)
class PackChoicePage:
    packs: list[PackChoiceItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None


@dataclass(frozen=True)
class AdminPackListItem:
    id: int
    code: str
    name: str
    cards_count: int
    selected_cards_count: int
    price_amount: int
    price_currency_code: str | None
    active: bool
    is_shop_available: bool


@dataclass(frozen=True)
class AdminPacksPage:
    packs: list[AdminPackListItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None = None


@dataclass(frozen=True)
class AdminPackDetails:
    id: int
    code: str
    name: str
    description: str
    image_path: str | None
    animation_video_path: str | None
    price_currency_code: str | None
    price_amount: int
    active: bool
    is_shop_available: bool
    is_starter: bool
    cards_count: int
    selected_cards_count: int
    rarity_chances: dict[str, int]


@dataclass(frozen=True)
class PackDraft:
    image_path: str
    name: str
    description: str
    price_currency_code: str | None
    price_amount: int
    cards_count: int
    is_shop_available: bool


@dataclass(frozen=True)
class PackCardItem:
    card_id: int
    name: str
    position: str
    overall: int
    team: str
    country: str
    collection_name: str
    rarity: str
    image_path: str


@dataclass(frozen=True)
class PackCardsPage:
    cards: list[PackCardItem]
    page: int
    pages_count: int
    total_count: int
    search: str | None = None


def normalize_pack_code(name: str) -> str:
    raw = name.strip().lower()
    raw = raw.replace("ё", "е")
    raw = re.sub(r"[^a-z0-9а-я]+", "-", raw)
    raw = raw.strip("-")

    if not raw:
        raw = "pack"

    if not raw.endswith("pack") and not raw.endswith("пак"):
        raw = f"{raw}-pack"

    return raw[:80]


def normalize_rarity_title(value: str) -> str | None:
    value = value.strip().lower()
    aliases = {
        "common": "Common",
        "обычная": "Common",
        "обычный": "Common",
        "rare": "Rare",
        "редкая": "Rare",
        "редкий": "Rare",
        "epic": "Epic",
        "эпик": "Epic",
        "эпическая": "Epic",
        "legendary": "Legendary",
        "легендарная": "Legendary",
        "легендарный": "Legendary",
        "event": "Event",
        "ивент": "Event",
        "событийная": "Event",
        "icon": "Icon",
        "икона": "Icon",
    }
    return aliases.get(value)


def encode_rarity_chances(chances: dict[str, int] | None) -> str | None:
    if not chances:
        return None

    clean = {rarity: int(value) for rarity, value in chances.items() if rarity in RARITIES and int(value) > 0}

    if not clean:
        return None

    return json.dumps(clean, ensure_ascii=False)


def decode_rarity_chances(value: str | None) -> dict[str, int]:
    if not value:
        return {}

    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, int] = {}

    for key, chance in raw.items():
        rarity = normalize_rarity_title(str(key)) or str(key)

        if rarity not in RARITIES:
            continue

        try:
            chance_value = int(chance)
        except (TypeError, ValueError):
            continue

        if chance_value > 0:
            result[rarity] = chance_value

    return result


def parse_rarity_chances(text: str) -> tuple[dict[str, int] | None, str | None]:
    result: dict[str, int] = {}
    parts = re.split(r"[\n,;]+", text.strip())

    for part in parts:
        clean_part = part.strip()

        if not clean_part:
            continue

        clean_part = clean_part.replace("=", " ").replace(":", " ").replace("%", " ")
        tokens = [token for token in clean_part.split() if token]

        if len(tokens) < 2:
            return None, "Каждую строку лучше писать так: Common 70"

        rarity = normalize_rarity_title(tokens[0])

        if rarity is None:
            return None, f"Редкость «{tokens[0]}» не найдена."

        try:
            chance = int(tokens[1])
        except ValueError:
            return None, "Проценты должны быть числами."

        if chance < 0:
            return None, "Процент не может быть меньше нуля."

        if chance > 0:
            result[rarity] = chance

    if not result:
        return None, "Укажи хотя бы одну редкость с шансом выше нуля."

    total = sum(result.values())

    if total != 100:
        return None, f"Сумма шансов должна быть 100%. Сейчас: {total}%."

    return result, None


def choose_rarity(chances: dict[str, int]) -> str | None:
    if not chances:
        return None

    total = sum(chances.values())

    if total <= 0:
        return None

    roll = PACK_RANDOM.randint(1, total)
    current = 0

    for rarity, chance in chances.items():
        current += chance

        if roll <= current:
            return rarity

    return next(iter(chances.keys()))


def build_cards_search_sql(search: str | None, params: list[object]) -> str:
    clean_search = clean_search_query(search)

    if not clean_search:
        return ""

    like_value = f"%{clean_search}%"
    clauses = [
        "cards.name LIKE ?",
        "cards.team LIKE ?",
        "cards.country LIKE ?",
        "cards.rarity LIKE ?",
        "cards.position LIKE ?",
        "collections.name LIKE ?",
        "collections.code LIKE ?",
    ]
    params.extend([like_value] * len(clauses))

    if clean_search.isdigit():
        clauses.append("cards.id = ?")
        params.append(int(clean_search))

    return " AND (" + " OR ".join(clauses) + ")"


def row_to_pack_card_item(row) -> PackCardItem:
    return PackCardItem(
        card_id=row["card_id"],
        name=row["name"],
        position=row["position"],
        overall=row["overall"],
        team=row["team"],
        country=row["country"],
        collection_name=row["collection_name"],
        rarity=row["rarity"],
        image_path=row["image_path"],
    )


async def get_pack_info(pack_id: int) -> PackInfo | None:
    details = await get_admin_pack_details(pack_id)

    if details is None:
        return None

    return PackInfo(
        id=details.id,
        code=details.code,
        name=details.name,
        description=details.description,
        image_path=details.image_path,
        animation_video_path=details.animation_video_path,
        price_currency_code=details.price_currency_code,
        price_amount=details.price_amount,
        active=details.active,
        is_shop_available=details.is_shop_available,
        is_starter=details.is_starter,
        cards_count=details.cards_count,
        selected_cards_count=details.selected_cards_count,
    )


async def get_admin_pack_details(pack_id: int) -> AdminPackDetails | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                packs.id,
                packs.code,
                packs.name,
                packs.description,
                packs.image_path,
                packs.animation_video_path,
                packs.price_currency_code,
                packs.price_amount,
                packs.active,
                packs.is_shop_available,
                packs.is_starter,
                COUNT(DISTINCT pack_slots.id) AS cards_count,
                COUNT(DISTINCT pack_cards.card_id) AS selected_cards_count
            FROM packs
            LEFT JOIN pack_slots ON pack_slots.pack_id = packs.id AND pack_slots.active = 1
            LEFT JOIN pack_cards ON pack_cards.pack_id = packs.id
            WHERE packs.id = ?
            GROUP BY packs.id
            """,
            (pack_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        odds_cursor = connection.execute(
            """
            SELECT rarity_chances
            FROM pack_slots
            WHERE pack_id = ? AND active = 1 AND rarity_chances IS NOT NULL AND rarity_chances != ''
            ORDER BY slot_number
            LIMIT 1
            """,
            (pack_id,),
        )
        odds_row = odds_cursor.fetchone()

    return AdminPackDetails(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        description=row["description"],
        image_path=row["image_path"],
        animation_video_path=row["animation_video_path"],
        price_currency_code=row["price_currency_code"],
        price_amount=row["price_amount"],
        active=bool(row["active"]),
        is_shop_available=bool(row["is_shop_available"]),
        is_starter=bool(row["is_starter"]),
        cards_count=row["cards_count"],
        selected_cards_count=row["selected_cards_count"],
        rarity_chances=decode_rarity_chances(odds_row["rarity_chances"] if odds_row else None),
    )


async def get_user_pack_inventory_page(user_id: int, page: int = 1, per_page: int = 5) -> PackInventoryPage:
    with get_connection() as connection:
        count_cursor = connection.execute(
            """
            SELECT COUNT(*) AS total_count
            FROM user_packs
            JOIN packs ON packs.id = user_packs.pack_id
            WHERE user_packs.user_id = ? AND user_packs.quantity > 0 AND packs.active = 1
            """,
            (user_id,),
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                packs.id,
                packs.code,
                packs.name,
                packs.description,
                packs.image_path,
                user_packs.quantity,
                COUNT(DISTINCT pack_slots.id) AS cards_count,
                COUNT(DISTINCT pack_cards.card_id) AS selected_cards_count
            FROM user_packs
            JOIN packs ON packs.id = user_packs.pack_id
            LEFT JOIN pack_slots ON pack_slots.pack_id = packs.id AND pack_slots.active = 1
            LEFT JOIN pack_cards ON pack_cards.pack_id = packs.id
            WHERE user_packs.user_id = ? AND user_packs.quantity > 0 AND packs.active = 1
            GROUP BY user_packs.id
            ORDER BY packs.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, offset),
        )
        rows = cursor.fetchall()

    packs = [
        PackInventoryItem(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            description=row["description"],
            image_path=row["image_path"],
            quantity=row["quantity"],
            cards_count=row["cards_count"],
            selected_cards_count=row["selected_cards_count"],
        )
        for row in rows
    ]

    return PackInventoryPage(packs=packs, page=safe_page, pages_count=pages_count, total_count=total_count)


async def get_user_pack_quantity(user_id: int, pack_id: int) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            "SELECT quantity FROM user_packs WHERE user_id = ? AND pack_id = ?",
            (user_id, pack_id),
        )
        row = cursor.fetchone()

    return int(row["quantity"]) if row else 0


async def give_pack_to_user(user_id: int, pack_id: int, quantity: int = 1) -> bool:
    if quantity <= 0:
        return False

    with get_connection() as connection:
        user_cursor = connection.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        pack_cursor = connection.execute("SELECT id FROM packs WHERE id = ? AND active = 1", (pack_id,))

        if user_cursor.fetchone() is None or pack_cursor.fetchone() is None:
            return False

        connection.execute(
            """
            INSERT INTO user_packs (user_id, pack_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, pack_id) DO UPDATE SET
                quantity = user_packs.quantity + excluded.quantity,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, pack_id, quantity),
        )
        connection.commit()

    return True


async def give_pack_to_user_by_code(user_id: int, pack_code: str, quantity: int = 1) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("SELECT id FROM packs WHERE code = ? AND active = 1", (pack_code,))
        row = cursor.fetchone()

    if row is None:
        return False

    return await give_pack_to_user(user_id=user_id, pack_id=row["id"], quantity=quantity)


async def ensure_starter_pack_for_user(user_id: int) -> None:
    return None


async def get_pack_choice_page(page: int = 1, per_page: int = 5, search: str | None = None) -> PackChoicePage:
    clean_search = clean_search_query(search)
    where_sql = "WHERE packs.active = 1"
    params: list[object] = []

    if clean_search:
        where_sql += " AND (packs.name LIKE ? OR packs.code LIKE ? OR packs.description LIKE ?)"
        params.extend([f"%{clean_search}%"] * 3)

    with get_connection() as connection:
        count_cursor = connection.execute(f"SELECT COUNT(*) AS total_count FROM packs {where_sql}", params)
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                packs.id,
                packs.code,
                packs.name,
                packs.description,
                packs.active,
                COUNT(DISTINCT pack_slots.id) AS quantity_hint
            FROM packs
            LEFT JOIN pack_slots ON pack_slots.pack_id = packs.id AND pack_slots.active = 1
            {where_sql}
            GROUP BY packs.id
            ORDER BY packs.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    packs = [
        PackChoiceItem(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            description=row["description"],
            quantity_hint=row["quantity_hint"],
            active=bool(row["active"]),
        )
        for row in rows
    ]

    return PackChoicePage(packs=packs, page=safe_page, pages_count=pages_count, total_count=total_count, search=clean_search)


async def get_admin_packs_page(page: int = 1, per_page: int = 5, search: str | None = None) -> AdminPacksPage:
    clean_search = clean_search_query(search)
    where_sql = ""
    params: list[object] = []

    if clean_search:
        where_sql = "WHERE packs.name LIKE ? OR packs.code LIKE ? OR packs.description LIKE ?"
        params.extend([f"%{clean_search}%"] * 3)

    with get_connection() as connection:
        count_cursor = connection.execute(f"SELECT COUNT(*) AS total_count FROM packs {where_sql}", params)
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                packs.id,
                packs.code,
                packs.name,
                packs.price_amount,
                packs.price_currency_code,
                packs.active,
                packs.is_shop_available,
                COUNT(DISTINCT pack_slots.id) AS cards_count,
                COUNT(DISTINCT pack_cards.card_id) AS selected_cards_count
            FROM packs
            LEFT JOIN pack_slots ON pack_slots.pack_id = packs.id AND pack_slots.active = 1
            LEFT JOIN pack_cards ON pack_cards.pack_id = packs.id
            {where_sql}
            GROUP BY packs.id
            ORDER BY packs.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    packs = [
        AdminPackListItem(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            cards_count=row["cards_count"],
            selected_cards_count=row["selected_cards_count"],
            price_amount=row["price_amount"],
            price_currency_code=row["price_currency_code"],
            active=bool(row["active"]),
            is_shop_available=bool(row["is_shop_available"]),
        )
        for row in rows
    ]

    return AdminPacksPage(packs=packs, page=safe_page, pages_count=pages_count, total_count=total_count, search=clean_search)


async def get_pack_history_page(user_id: int, page: int = 1, per_page: int = 5) -> PackHistoryPage:
    with get_connection() as connection:
        count_cursor = connection.execute("SELECT COUNT(*) AS total_count FROM pack_openings WHERE user_id = ?", (user_id,))
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                pack_openings.id,
                packs.name AS pack_name,
                pack_openings.created_at,
                COUNT(pack_opening_rewards.id) AS rewards_count
            FROM pack_openings
            JOIN packs ON packs.id = pack_openings.pack_id
            LEFT JOIN pack_opening_rewards ON pack_opening_rewards.opening_id = pack_openings.id
            WHERE pack_openings.user_id = ?
            GROUP BY pack_openings.id
            ORDER BY pack_openings.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, per_page, offset),
        )
        rows = cursor.fetchall()

    openings = [
        PackHistoryItem(id=row["id"], pack_name=row["pack_name"], rewards_count=row["rewards_count"], created_at=row["created_at"])
        for row in rows
    ]

    return PackHistoryPage(openings=openings, page=safe_page, pages_count=pages_count, total_count=total_count)


async def create_admin_pack(draft: PackDraft) -> int:
    code_base = normalize_pack_code(draft.name)

    with get_connection() as connection:
        code = make_unique_pack_code(connection, code_base)
        sort_cursor = connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 AS next_sort FROM packs")
        sort_order = int(sort_cursor.fetchone()["next_sort"])

        cursor = connection.execute(
            """
            INSERT INTO packs (
                code,
                name,
                description,
                image_path,
                price_currency_code,
                price_amount,
                active,
                is_shop_available,
                is_starter,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, ?)
            """,
            (
                code,
                draft.name,
                draft.description,
                draft.image_path,
                draft.price_currency_code,
                draft.price_amount,
                1 if draft.is_shop_available else 0,
                sort_order,
            ),
        )
        pack_id = int(cursor.lastrowid)
        create_pack_slots(connection=connection, pack_id=pack_id, cards_count=draft.cards_count, rarity_chances=DEFAULT_RARITY_CHANCES)
        connection.commit()

    return pack_id


def make_unique_pack_code(connection, code_base: str) -> str:
    code = code_base
    counter = 2

    while True:
        cursor = connection.execute("SELECT id FROM packs WHERE code = ?", (code,))

        if cursor.fetchone() is None:
            return code

        code = f"{code_base}-{counter}"
        counter += 1


def create_pack_slots(connection, pack_id: int, cards_count: int, rarity_chances: dict[str, int] | None = None) -> None:
    safe_count = min(max(cards_count, 1), 20)
    encoded_chances = encode_rarity_chances(rarity_chances)

    connection.execute("DELETE FROM pack_slots WHERE pack_id = ?", (pack_id,))

    for index in range(1, safe_count + 1):
        connection.execute(
            """
            INSERT INTO pack_slots (pack_id, slot_number, title, rarity_chances, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (pack_id, index, f"Карта {index}", encoded_chances),
        )


async def update_pack_image_path(pack_id: int, image_path: str) -> bool:
    return await update_pack_field(pack_id, "image_path", image_path)


async def update_pack_animation_video_path(pack_id: int, video_path: str | None) -> bool:
    """Attach or remove the admin-uploaded 10-second opening video for a pack."""
    return await update_pack_field(pack_id, "animation_video_path", video_path)


async def update_pack_animation_video(
    pack_id: int,
    *,
    video_path: str | None,
    duration_seconds: int | None,
    file_size: int | None,
    file_id: str | None,
    file_unique_id: str | None,
    uploaded_by: int | None,
) -> bool:
    """Полная замена/загрузка видео открытия пака с метаданными (ТЗ "ВИДЕО В
    АДМИН-ПАНЕЛИ") — file_id/file_unique_id сохраняются ОТДЕЛЬНО от локального
    пути, чтобы видео не зависело только от временной директории контейнера."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE packs
            SET animation_video_path = ?,
                animation_duration_seconds = ?,
                animation_file_size = ?,
                animation_file_id = ?,
                animation_file_unique_id = ?,
                animation_uploaded_at = CURRENT_TIMESTAMP,
                animation_uploaded_by = ?,
                animation_enabled = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (video_path, duration_seconds, file_size, file_id, file_unique_id, uploaded_by, pack_id),
        )
        connection.commit()
    return True


async def remove_pack_animation_video(pack_id: int) -> bool:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE packs
            SET animation_video_path = NULL,
                animation_duration_seconds = NULL,
                animation_file_size = NULL,
                animation_file_id = NULL,
                animation_file_unique_id = NULL,
                animation_uploaded_at = NULL,
                animation_uploaded_by = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (pack_id,),
        )
        connection.commit()
    return True


async def set_pack_animation_enabled(pack_id: int, enabled: bool) -> bool:
    with get_connection() as connection:
        connection.execute(
            "UPDATE packs SET animation_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if enabled else 0, pack_id),
        )
        connection.commit()
    return enabled


@dataclass(frozen=True)
class PackAnimationMeta:
    video_path: str | None
    enabled: bool
    duration_seconds: int | None
    file_size: int | None
    file_id: str | None
    file_unique_id: str | None
    uploaded_at: str | None
    uploaded_by: int | None


async def get_pack_animation_meta(pack_id: int) -> PackAnimationMeta | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT animation_video_path, animation_enabled, animation_duration_seconds, animation_file_size,
                   animation_file_id, animation_file_unique_id, animation_uploaded_at, animation_uploaded_by
            FROM packs WHERE id = ?
            """,
            (pack_id,),
        ).fetchone()
    if row is None:
        return None
    return PackAnimationMeta(
        video_path=row["animation_video_path"],
        enabled=bool(row["animation_enabled"]),
        duration_seconds=row["animation_duration_seconds"],
        file_size=row["animation_file_size"],
        file_id=row["animation_file_id"],
        file_unique_id=row["animation_file_unique_id"],
        uploaded_at=row["animation_uploaded_at"],
        uploaded_by=row["animation_uploaded_by"],
    )


async def update_pack_text_field(pack_id: int, field: str, value: str) -> bool:
    allowed_fields = {"name", "description"}

    if field not in allowed_fields:
        return False

    return await update_pack_field(pack_id, field, value.strip())


async def update_pack_price(pack_id: int, currency_code: str | None, amount: int) -> bool:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE packs
            SET price_currency_code = ?, price_amount = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (currency_code, max(amount, 0), pack_id),
        )
        connection.commit()

    return True


async def update_pack_cards_count(pack_id: int, cards_count: int) -> bool:
    if cards_count < 1 or cards_count > 20:
        return False

    details = await get_admin_pack_details(pack_id)

    if details is None:
        return False

    rarity_chances = details.rarity_chances or DEFAULT_RARITY_CHANCES

    with get_connection() as connection:
        create_pack_slots(connection, pack_id, cards_count, rarity_chances)
        connection.execute("UPDATE packs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pack_id,))
        connection.commit()

    return True


async def update_pack_rarity_chances(pack_id: int, chances: dict[str, int]) -> bool:
    if sum(chances.values()) != 100:
        return False

    encoded = encode_rarity_chances(chances)

    if encoded is None:
        return False

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE pack_slots
            SET rarity = NULL, rarity_chances = ?, updated_at = CURRENT_TIMESTAMP
            WHERE pack_id = ? AND active = 1
            """,
            (encoded, pack_id),
        )
        connection.execute("UPDATE packs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pack_id,))
        connection.commit()

    return True


async def toggle_pack_active(pack_id: int) -> bool | None:
    with get_connection() as connection:
        cursor = connection.execute("SELECT active FROM packs WHERE id = ?", (pack_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        next_value = 0 if int(row["active"]) else 1
        connection.execute("UPDATE packs SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (next_value, pack_id))
        connection.commit()

    return bool(next_value)


async def toggle_pack_shop(pack_id: int) -> bool | None:
    with get_connection() as connection:
        cursor = connection.execute("SELECT is_shop_available FROM packs WHERE id = ?", (pack_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        next_value = 0 if int(row["is_shop_available"]) else 1
        connection.execute("UPDATE packs SET is_shop_available = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (next_value, pack_id))
        connection.commit()

    return bool(next_value)


async def update_pack_field(pack_id: int, field: str, value: object) -> bool:
    allowed_fields = {"image_path", "animation_video_path", "name", "description"}

    if field not in allowed_fields:
        return False

    with get_connection() as connection:
        connection.execute(f"UPDATE packs SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (value, pack_id))
        connection.commit()

    return True


async def get_pack_cards_page(pack_id: int, page: int = 1, per_page: int = 5) -> PackCardsPage:
    with get_connection() as connection:
        count_cursor = connection.execute("SELECT COUNT(*) AS total_count FROM pack_cards WHERE pack_id = ?", (pack_id,))
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            """
            SELECT
                cards.id AS card_id,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                collections.name AS collection_name
            FROM pack_cards
            JOIN cards ON cards.id = pack_cards.card_id
            JOIN collections ON collections.id = cards.collection_id
            WHERE pack_cards.pack_id = ?
            ORDER BY cards.overall DESC, cards.name
            LIMIT ? OFFSET ?
            """,
            (pack_id, per_page, offset),
        )
        rows = cursor.fetchall()

    return PackCardsPage(cards=[row_to_pack_card_item(row) for row in rows], page=safe_page, pages_count=pages_count, total_count=total_count)


async def get_pack_available_cards_page(pack_id: int, page: int = 1, per_page: int = 5, search: str | None = None) -> PackCardsPage:
    clean_search = clean_search_query(search)
    params: list[object] = [pack_id]
    search_sql = build_cards_search_sql(clean_search, params)

    with get_connection() as connection:
        count_cursor = connection.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1
              AND cards.id NOT IN (SELECT card_id FROM pack_cards WHERE pack_id = ?)
              {search_sql}
            """,
            params,
        )
        total_count = int(count_cursor.fetchone()["total_count"])
        pages_count = max(1, ceil(total_count / per_page))
        safe_page = min(max(page, 1), pages_count)
        offset = (safe_page - 1) * per_page

        cursor = connection.execute(
            f"""
            SELECT
                cards.id AS card_id,
                cards.name,
                cards.position,
                cards.overall,
                cards.team,
                cards.country,
                cards.rarity,
                cards.image_path,
                collections.name AS collection_name
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1
              AND cards.id NOT IN (SELECT card_id FROM pack_cards WHERE pack_id = ?)
              {search_sql}
            ORDER BY cards.overall DESC, cards.name
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        )
        rows = cursor.fetchall()

    return PackCardsPage(cards=[row_to_pack_card_item(row) for row in rows], page=safe_page, pages_count=pages_count, total_count=total_count, search=clean_search)


async def add_card_to_pack(pack_id: int, card_id: int) -> bool:
    with get_connection() as connection:
        pack_cursor = connection.execute("SELECT id FROM packs WHERE id = ?", (pack_id,))
        card_cursor = connection.execute("SELECT id FROM cards WHERE id = ? AND active = 1", (card_id,))

        if pack_cursor.fetchone() is None or card_cursor.fetchone() is None:
            return False

        connection.execute(
            """
            INSERT INTO pack_cards (pack_id, card_id)
            VALUES (?, ?)
            ON CONFLICT(pack_id, card_id) DO NOTHING
            """,
            (pack_id, card_id),
        )
        connection.execute("UPDATE packs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pack_id,))
        connection.commit()

    return True


async def remove_card_from_pack(pack_id: int, card_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM pack_cards WHERE pack_id = ? AND card_id = ?", (pack_id, card_id))
        connection.execute("UPDATE packs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pack_id,))
        connection.commit()

    return cursor.rowcount > 0


async def open_user_pack(user_id: int, pack_id: int) -> tuple[PackOpeningResult | None, str | None]:
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        pack_cursor = connection.execute(
            """
            SELECT id, code, name, price_currency_code, price_amount
            FROM packs
            WHERE id = ? AND active = 1
            """,
            (pack_id,),
        )
        pack_row = pack_cursor.fetchone()

        if pack_row is None:
            return None, "Пак не найден."

        quantity_cursor = connection.execute(
            "SELECT quantity FROM user_packs WHERE user_id = ? AND pack_id = ?",
            (user_id, pack_id),
        )
        quantity_row = quantity_cursor.fetchone()

        if quantity_row is None or int(quantity_row["quantity"]) <= 0:
            return None, "Этого пака пока нет в коллекции."

        if int(pack_row["price_amount"] or 0) <= 0 and pack_row["price_currency_code"] is None:
            opening_cursor = connection.execute(
                "SELECT id FROM pack_openings WHERE user_id = ? AND pack_id = ? LIMIT 1",
                (user_id, pack_id),
            )

            if opening_cursor.fetchone() is not None:
                return None, "Бесплатный пак уже открыт. Такой подарок можно забрать только один раз."

        selected_count_cursor = connection.execute("SELECT COUNT(*) AS total_count FROM pack_cards WHERE pack_id = ?", (pack_id,))
        selected_count = int(selected_count_cursor.fetchone()["total_count"])

        if selected_count <= 0:
            return None, "В пак пока не добавлены карточки. Пак ждёт настройки состава."

        slots_cursor = connection.execute(
            """
            SELECT
                id,
                slot_number,
                title,
                collection_id,
                position,
                rarity,
                rarity_chances,
                min_overall,
                max_overall,
                special_collection_id,
                special_image_hint,
                special_chance_percent
            FROM pack_slots
            WHERE pack_id = ? AND active = 1
            ORDER BY slot_number
            """,
            (pack_id,),
        )
        slots = slots_cursor.fetchall()

        if not slots:
            return None, "Пак пока ждёт настройку наград."

        chosen_cards = []

        for slot in slots:
            card_row = choose_card_for_slot(connection, pack_id, slot)

            if card_row is None:
                return None, "В паке пока нет подходящих карточек. Проверь выбранные карты и шансы."

            chosen_cards.append(card_row)

        try:
            opening_cursor = connection.execute(
                "INSERT INTO pack_openings (user_id, pack_id, source) VALUES (?, ?, 'inventory')",
                (user_id, pack_id),
            )
            opening_id = int(opening_cursor.lastrowid)

            decrement_cursor = connection.execute(
                """
                UPDATE user_packs
                SET quantity = quantity - 1, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND pack_id = ? AND quantity >= 1
                """,
                (user_id, pack_id),
            )

            if decrement_cursor.rowcount != 1:
                connection.rollback()
                return None, "Этого пака пока нет в коллекции."

            rewards: list[PackRewardItem] = []

            for card_row in chosen_cards:
                user_card_cursor = connection.execute(
                    """
                    INSERT INTO user_cards (user_id, card_id, obtained_from, is_in_lineup, trade_locked)
                    VALUES (?, ?, ?, 0, 0)
                    """,
                    (user_id, card_row["id"], pack_row["code"]),
                )
                user_card_id = int(user_card_cursor.lastrowid)

                connection.execute(
                    """
                    INSERT INTO pack_opening_rewards (opening_id, user_card_id, card_id, reward_type, title)
                    VALUES (?, ?, ?, 'card', ?)
                    """,
                    (opening_id, user_card_id, card_row["id"], card_row["name"]),
                )

                rewards.append(
                    PackRewardItem(
                        user_card_id=user_card_id,
                        card_id=card_row["id"],
                        name=card_row["name"],
                        position=card_row["position"],
                        overall=card_row["overall"],
                        team=card_row["team"],
                        country=card_row["country"],
                        collection_name=card_row["collection_name"],
                        rarity=card_row["rarity"],
                        image_path=card_row["image_path"],
                    )
                )

            # PENDING REVEAL: создаётся в ТОЙ ЖЕ транзакции, что и выдача наград —
            # награда уже "зафиксирована" (ТЗ) к моменту, когда будет отправлено
            # видео. request_id детерминирован от opening_id (свежий autoincrement
            # PK), этого достаточно для идемпотентности — повторный вызов с тем же
            # opening_id физически невозможен, а UNIQUE(opening_id)/UNIQUE(request_id)
            # защищают от повторной вставки, если код вызовется дважды по ошибке.
            reward_snapshot = json.dumps([reward.__dict__ for reward in rewards], ensure_ascii=False)
            connection.execute(
                """
                INSERT INTO pack_pending_reveals
                    (opening_id, user_id, pack_id, request_id, reward_snapshot, status, reveal_at)
                VALUES (?, ?, ?, ?, ?, 'pending', datetime('now', '+10 seconds'))
                """,
                (opening_id, user_id, pack_row["id"], f"pack-open-{opening_id}", reward_snapshot),
            )

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PackOpeningResult(opening_id=opening_id, pack_id=pack_row["id"], pack_code=pack_row["code"], pack_name=pack_row["name"], rewards=rewards), None


async def attach_reveal_message(opening_id: int, *, chat_id: int, message_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE pack_pending_reveals SET chat_id = ?, message_id = ? WHERE opening_id = ? AND status = 'pending'",
            (chat_id, message_id, opening_id),
        )
        connection.commit()


async def mark_reveal_completed(opening_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE pack_pending_reveals SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE opening_id = ? AND status = 'pending'",
            (opening_id,),
        )
        connection.commit()


async def mark_reveal_failed(opening_id: int, error: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE pack_pending_reveals SET status = 'failed', completed_at = CURRENT_TIMESTAMP, error = ? WHERE opening_id = ? AND status = 'pending'",
            (error[:500], opening_id),
        )
        connection.commit()


def rewards_from_snapshot(reward_snapshot: str) -> list[PackRewardItem]:
    return [PackRewardItem(**item) for item in json.loads(reward_snapshot)]


async def list_pending_reveals(status: str = "pending") -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM pack_pending_reveals WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
    return [dict(row) for row in rows]


def choose_card_for_slot(connection, pack_id: int, slot):
    special_chance = int(slot["special_chance_percent"] or 0)

    if special_chance > 0 and PACK_RANDOM.randint(1, 100) <= special_chance:
        special_row = select_random_card(
            connection=connection,
            pack_id=pack_id,
            collection_id=slot["special_collection_id"],
            position=slot["position"],
            rarity=slot["rarity"],
            min_overall=slot["min_overall"],
            max_overall=slot["max_overall"],
            image_hint=slot["special_image_hint"],
        )

        if special_row is not None:
            return special_row

    chances = decode_rarity_chances(slot["rarity_chances"])
    rarity = choose_rarity(chances) if chances else slot["rarity"]

    return select_random_card(
        connection=connection,
        pack_id=pack_id,
        collection_id=slot["collection_id"],
        position=slot["position"],
        rarity=rarity,
        min_overall=slot["min_overall"],
        max_overall=slot["max_overall"],
        image_hint=None,
    )


def select_random_card(
    connection,
    pack_id: int,
    collection_id: int | None,
    position: str | None,
    rarity: str | None,
    min_overall: int | None,
    max_overall: int | None,
    image_hint: str | None,
):
    filters = ["cards.active = 1", "pack_cards.pack_id = ?"]
    params: list[object] = [pack_id]

    if collection_id is not None:
        filters.append("cards.collection_id = ?")
        params.append(collection_id)

    if position:
        filters.append("cards.position = ?")
        params.append(position)

    if rarity:
        filters.append("cards.rarity = ?")
        params.append(rarity)

    if min_overall is not None:
        filters.append("cards.overall >= ?")
        params.append(min_overall)

    if max_overall is not None:
        filters.append("cards.overall <= ?")
        params.append(max_overall)

    if image_hint:
        filters.append("cards.image_path LIKE ?")
        params.append(f"%{image_hint}%")

    where_sql = " AND ".join(filters)

    cursor = connection.execute(
        f"""
        SELECT
            cards.id,
            cards.name,
            cards.position,
            cards.overall,
            cards.team,
            cards.country,
            cards.rarity,
            cards.image_path,
            collections.name AS collection_name
        FROM pack_cards
        JOIN cards ON cards.id = pack_cards.card_id
        JOIN collections ON collections.id = cards.collection_id
        WHERE {where_sql}
        ORDER BY RANDOM()
        LIMIT 1
        """,
        params,
    )

    return cursor.fetchone()


async def count_user_packs(user_id: int) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS total_count
            FROM user_packs
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()

    return int(row["total_count"]) if row else 0
