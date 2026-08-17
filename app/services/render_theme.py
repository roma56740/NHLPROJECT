from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.database.db import get_connection

ROOT_DIR = Path(__file__).resolve().parents[2]
RENDER_UPLOAD_DIR = ROOT_DIR / "assets" / "uploads" / "render_themes"
RENDER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class RenderThemeConfig:
    menu_background_path: str
    menu_video_path: str
    menu_title: str
    menu_subtitle: str
    menu_accent: str
    lineup_background_path: str
    lineup_accent: str
    lineup_chemistry_enabled: bool


def _get_setting(key: str, default: str = "") -> str:
    try:
        with get_connection() as connection:
            row = connection.execute("SELECT value FROM game_settings WHERE key = ?", (key,)).fetchone()
        if row is not None:
            return str(row["value"] or "")
    except Exception:
        pass
    return default


def normalize_hex_color(value: str | None, default: str) -> str:
    text = str(value or "").strip()
    return text.upper() if HEX_COLOR_RE.match(text) else default


def get_render_theme_config() -> RenderThemeConfig:
    return RenderThemeConfig(
        menu_background_path=_get_setting("render_menu_background_path", ""),
        menu_video_path=_get_setting("render_menu_video_path", ""),
        menu_title=_get_setting("render_menu_title", "NHL CARD LEAGUE") or "NHL CARD LEAGUE",
        menu_subtitle=_get_setting("render_menu_subtitle", "SEASON 1") or "SEASON 1",
        menu_accent=normalize_hex_color(_get_setting("render_menu_accent", "#4CB8FF"), "#4CB8FF"),
        lineup_background_path=_get_setting("render_lineup_background_path", "assets/visual/lineup_match_bg.png"),
        lineup_accent=normalize_hex_color(_get_setting("render_lineup_accent", "#4CB8FF"), "#4CB8FF"),
        lineup_chemistry_enabled=_get_setting("render_lineup_chemistry_enabled", "1").strip().lower()
        in {"1", "true", "yes", "on", "да", "вкл"},
    )


def asset_absolute_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value).strip())
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path if path.exists() and path.is_file() else None


def relative_asset_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR.resolve()).as_posix()
    except Exception:
        return path.as_posix()
