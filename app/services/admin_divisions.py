from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil
from pathlib import Path

from app.database.db import get_connection

ANIMATION_ASSET_TYPES = {"division", "team", "country", "stage"}


@dataclass(frozen=True)
class DivisionItem:
    id: int
    code: str
    name: str
    image_path: str | None
    active: bool
    teams_count: int


@dataclass(frozen=True)
class TeamAssignmentItem:
    team_name: str
    division_id: int | None
    division_name: str | None
    selected: bool


@dataclass(frozen=True)
class TeamAssignmentsPage:
    teams: list[TeamAssignmentItem]
    page: int
    pages_count: int
    total_count: int


@dataclass(frozen=True)
class AnimationAssetItem:
    asset_type: str
    asset_key: str
    title: str
    image_path: str
    exists: bool


@dataclass(frozen=True)
class AnimationAssetsPage:
    assets: list[AnimationAssetItem]
    page: int
    pages_count: int
    total_count: int
    asset_type: str


@dataclass(frozen=True)
class MissingAssetReport:
    missing_cards: list[str]
    missing_packs: list[str]
    missing_divisions: list[str]
    teams_without_division: list[str]
    missing_pack_videos: list[str]
    missing_team_images: list[str]
    missing_country_images: list[str]

    @property
    def has_issues(self) -> bool:
        return any((
            self.missing_cards,
            self.missing_packs,
            self.missing_divisions,
            self.teams_without_division,
            self.missing_pack_videos,
            self.missing_team_images,
            self.missing_country_images,
        ))


def normalize_code(name: str) -> str:
    raw = " ".join((name or "").strip().split()).lower().replace("ё", "е")
    raw = re.sub(r"[^a-z0-9а-я]+", "-", raw).strip("-")
    return raw[:80] or "division"


def _image_exists(path_value: str | None) -> bool:
    if not path_value:
        return False
    return Path(str(path_value)).exists()


async def create_division(name: str) -> tuple[DivisionItem | None, str | None]:
    clean = " ".join((name or "").strip().split())
    if len(clean) < 2 or len(clean) > 64:
        return None, "Название должно быть от 2 до 64 символов."

    code_base = normalize_code(clean)
    code = code_base
    with get_connection() as connection:
        suffix = 2
        while connection.execute("SELECT 1 FROM team_divisions WHERE code = ?", (code,)).fetchone():
            code = f"{code_base}-{suffix}"
            suffix += 1
        try:
            cursor = connection.execute(
                "INSERT INTO team_divisions (code, name, active) VALUES (?, ?, 1)",
                (code, clean),
            )
            division_id = int(cursor.lastrowid)
            connection.commit()
        except Exception:
            return None, "Такой дивизион уже есть."
    return await get_division(division_id), None


async def get_divisions() -> list[DivisionItem]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.code, d.name, d.image_path, d.active, COUNT(t.id) AS teams_count
            FROM team_divisions d
            LEFT JOIN team_division_teams t ON t.division_id = d.id
            GROUP BY d.id
            ORDER BY d.name COLLATE NOCASE ASC
            """
        ).fetchall()
    return [DivisionItem(
        id=int(row["id"]),
        code=str(row["code"]),
        name=str(row["name"]),
        image_path=row["image_path"],
        active=bool(row["active"]),
        teams_count=int(row["teams_count"] or 0),
    ) for row in rows]


async def get_division(division_id: int) -> DivisionItem | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT d.id, d.code, d.name, d.image_path, d.active, COUNT(t.id) AS teams_count
            FROM team_divisions d
            LEFT JOIN team_division_teams t ON t.division_id = d.id
            WHERE d.id = ?
            GROUP BY d.id
            """,
            (division_id,),
        ).fetchone()
    if row is None:
        return None
    return DivisionItem(
        id=int(row["id"]), code=str(row["code"]), name=str(row["name"]),
        image_path=row["image_path"], active=bool(row["active"]), teams_count=int(row["teams_count"] or 0)
    )


async def toggle_division_active(division_id: int) -> DivisionItem | None:
    div = await get_division(division_id)
    if div is None:
        return None
    with get_connection() as connection:
        connection.execute(
            "UPDATE team_divisions SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (0 if div.active else 1, division_id),
        )
        connection.commit()
    return await get_division(division_id)


async def update_division_image(division_id: int, image_path: str) -> DivisionItem | None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE team_divisions SET image_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (image_path, division_id),
        )
        connection.execute(
            """
            INSERT INTO animation_assets (asset_type, asset_key, title, image_path)
            SELECT 'division', code, name, ? FROM team_divisions WHERE id = ?
            ON CONFLICT(asset_type, asset_key) DO UPDATE SET
                title = excluded.title,
                image_path = excluded.image_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (image_path, division_id),
        )
        connection.commit()
    return await get_division(division_id)


async def list_existing_teams() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT TRIM(team) AS team_name
            FROM cards
            WHERE TRIM(team) != ''
            ORDER BY team_name COLLATE NOCASE ASC
            """
        ).fetchall()
    return [str(row["team_name"]) for row in rows]


async def get_team_assignments_page(division_id: int, page: int = 1, per_page: int = 8) -> TeamAssignmentsPage:
    with get_connection() as connection:
        total_row = connection.execute("SELECT COUNT(DISTINCT TRIM(team)) AS total FROM cards WHERE TRIM(team) != ''").fetchone()
        total = int(total_row["total"] or 0)
        pages = max(1, ceil(total / per_page))
        safe_page = min(max(page, 1), pages)
        offset = (safe_page - 1) * per_page
        rows = connection.execute(
            """
            SELECT base.team_name, t.division_id, d.name AS division_name
            FROM (
                SELECT DISTINCT TRIM(team) AS team_name
                FROM cards
                WHERE TRIM(team) != ''
                ORDER BY team_name COLLATE NOCASE ASC
                LIMIT ? OFFSET ?
            ) base
            LEFT JOIN team_division_teams t ON t.team_name = base.team_name
            LEFT JOIN team_divisions d ON d.id = t.division_id
            ORDER BY base.team_name COLLATE NOCASE ASC
            """,
            (per_page, offset),
        ).fetchall()
    items = [TeamAssignmentItem(
        team_name=str(row["team_name"]),
        division_id=int(row["division_id"]) if row["division_id"] is not None else None,
        division_name=row["division_name"],
        selected=(row["division_id"] == division_id),
    ) for row in rows]
    return TeamAssignmentsPage(teams=items, page=safe_page, pages_count=pages, total_count=total)


async def toggle_team_in_division(division_id: int, team_name: str) -> bool:
    clean_team = " ".join((team_name or "").strip().split())
    if not clean_team:
        return False
    with get_connection() as connection:
        current = connection.execute("SELECT division_id FROM team_division_teams WHERE team_name = ?", (clean_team,)).fetchone()
        if current and int(current["division_id"]) == division_id:
            connection.execute("DELETE FROM team_division_teams WHERE team_name = ?", (clean_team,))
            selected = False
        else:
            connection.execute(
                """
                INSERT INTO team_division_teams (division_id, team_name)
                VALUES (?, ?)
                ON CONFLICT(team_name) DO UPDATE SET
                    division_id = excluded.division_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (division_id, clean_team),
            )
            selected = True
        connection.commit()
    return selected


async def get_division_for_team(team_name: str) -> DivisionItem | None:
    clean_team = " ".join((team_name or "").strip().split())
    if not clean_team:
        return None
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT d.id, d.code, d.name, d.image_path, d.active, COUNT(tt.id) AS teams_count
            FROM team_division_teams t
            JOIN team_divisions d ON d.id = t.division_id AND d.active = 1
            LEFT JOIN team_division_teams tt ON tt.division_id = d.id
            WHERE t.team_name = ?
            GROUP BY d.id
            """,
            (clean_team,),
        ).fetchone()
    if row is None:
        return None
    return DivisionItem(int(row["id"]), str(row["code"]), str(row["name"]), row["image_path"], bool(row["active"]), int(row["teams_count"] or 0))


async def upsert_animation_asset(asset_type: str, asset_key: str, title: str, image_path: str) -> None:
    asset_type = asset_type.strip().lower()
    if asset_type not in ANIMATION_ASSET_TYPES:
        raise ValueError("Unknown asset type")
    clean_key = " ".join((asset_key or "").strip().split())
    clean_title = " ".join((title or clean_key).strip().split()) or clean_key
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO animation_assets (asset_type, asset_key, title, image_path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(asset_type, asset_key) DO UPDATE SET
                title = excluded.title,
                image_path = excluded.image_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (asset_type, clean_key, clean_title, image_path),
        )
        connection.commit()


async def get_animation_asset(asset_type: str, asset_key: str) -> AnimationAssetItem | None:
    clean_key = " ".join((asset_key or "").strip().split())
    with get_connection() as connection:
        row = connection.execute(
            "SELECT asset_type, asset_key, title, image_path FROM animation_assets WHERE asset_type = ? AND asset_key = ?",
            (asset_type, clean_key),
        ).fetchone()
    if row is None:
        return None
    path = str(row["image_path"] or "")
    return AnimationAssetItem(str(row["asset_type"]), str(row["asset_key"]), str(row["title"] or row["asset_key"]), path, _image_exists(path))


async def resolve_pack_animation_media(team: str, country: str) -> dict[str, str | None]:
    division = await get_division_for_team(team)
    team_asset = await get_animation_asset("team", team)
    country_asset = await get_animation_asset("country", country)
    return {
        "division_name": division.name if division else "Без дивизиона",
        "division_image": division.image_path if division and _image_exists(division.image_path) else None,
        "team_image": team_asset.image_path if team_asset and team_asset.exists else None,
        "country_image": country_asset.image_path if country_asset and country_asset.exists else None,
    }


async def get_animation_assets_page(asset_type: str, page: int = 1, per_page: int = 8) -> AnimationAssetsPage:
    if asset_type == "team":
        keys = await list_existing_teams()
    elif asset_type == "country":
        with get_connection() as connection:
            rows = connection.execute("SELECT DISTINCT TRIM(country) AS value FROM cards WHERE TRIM(country) != '' ORDER BY value COLLATE NOCASE ASC").fetchall()
        keys = [str(row["value"]) for row in rows]
    else:
        keys = []
    total = len(keys)
    pages = max(1, ceil(total / per_page))
    safe_page = min(max(page, 1), pages)
    chunk = keys[(safe_page - 1) * per_page:safe_page * per_page]
    assets: list[AnimationAssetItem] = []
    for key in chunk:
        asset = await get_animation_asset(asset_type, key)
        if asset is None:
            assets.append(AnimationAssetItem(asset_type=asset_type, asset_key=key, title=key, image_path="", exists=False))
        else:
            assets.append(asset)
    return AnimationAssetsPage(assets=assets, page=safe_page, pages_count=pages, total_count=total, asset_type=asset_type)


async def build_missing_asset_report(limit: int = 20) -> MissingAssetReport:
    with get_connection() as connection:
        card_rows = connection.execute(
            """
            SELECT id, name, team, country, image_path
            FROM cards
            WHERE active = 1
            ORDER BY id DESC
            """
        ).fetchall()
        pack_rows = connection.execute(
            "SELECT id, name, image_path, animation_video_path FROM packs WHERE active = 1 ORDER BY id DESC"
        ).fetchall()
        division_rows = connection.execute(
            "SELECT name, image_path FROM team_divisions WHERE active = 1 ORDER BY name"
        ).fetchall()
        team_rows = connection.execute(
            """
            SELECT DISTINCT TRIM(team) AS team_name
            FROM cards
            WHERE active = 1 AND TRIM(team) != ''
            ORDER BY team_name COLLATE NOCASE ASC
            """
        ).fetchall()
        assigned = {str(row["team_name"]) for row in connection.execute("SELECT team_name FROM team_division_teams").fetchall()}

    missing_cards = []
    for row in card_rows:
        reasons = []
        if not str(row["team"] or "").strip():
            reasons.append("команда")
        if not str(row["country"] or "").strip():
            reasons.append("страна")
        if not _image_exists(row["image_path"]):
            reasons.append("фото")
        if reasons:
            missing_cards.append(f"ID {row['id']} {row['name']} — нет: {', '.join(reasons)}")

    missing_packs = [f"ID {row['id']} {row['name']} — нет картинки" for row in pack_rows if not _image_exists(row["image_path"])]
    missing_pack_videos = [
        f"ID {row['id']} {row['name']} — нет видео открытия"
        for row in pack_rows
        if not _image_exists(row["animation_video_path"])
    ]
    missing_divisions = [f"{row['name']} — нет картинки" for row in division_rows if not _image_exists(row["image_path"])]
    teams = [str(row["team_name"]) for row in team_rows]
    teams_without_division = [team for team in teams if team not in assigned]

    return MissingAssetReport(
        missing_cards=missing_cards[:limit],
        missing_packs=missing_packs[:limit],
        missing_divisions=missing_divisions[:limit],
        teams_without_division=teams_without_division[:limit],
        missing_pack_videos=missing_pack_videos[:limit],
        missing_team_images=[],
        missing_country_images=[],
    )
