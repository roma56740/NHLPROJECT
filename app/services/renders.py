from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.services.lineup import LINEUP_SLOT_ORDER, LineupCard, LineupOverview, get_slot_info
from app.services.user_cards import PlayerCardsPage, PlayerCardListItem

ROOT_DIR = Path(__file__).resolve().parents[2]
VISUAL_DIR = ROOT_DIR / "assets" / "visual"
RENDER_DIR = ROOT_DIR / "data" / "render_cache"
RENDER_DIR.mkdir(parents=True, exist_ok=True)

RENDER_CACHE_TTL_SECONDS = 6 * 60 * 60

# Стандарт пропорции берём из присланного примера карточки: 914x1280.
CARD_REFERENCE_WIDTH = 914
CARD_REFERENCE_HEIGHT = 1280
CARD_REFERENCE_RATIO = CARD_REFERENCE_WIDTH / CARD_REFERENCE_HEIGHT

LINEUP_CANVAS_SIZE = (1536, 864)
COLLECTION_CANVAS_SIZE = (1536, 864)
LINEUP_CARD_HEIGHT = 300
COLLECTION_CARD_HEIGHT = 330
PROFILE_CARD_HEIGHT = 720

RARITY_COLORS = {
    "Common": "#b8c0cc",
    "Rare": "#4da3ff",
    "Epic": "#9f6bff",
    "Legendary": "#ffb347",
    "Event": "#ff5f8f",
    "Icon": "#ffd95c",
}


def cleanup_render_cache() -> None:
    now = time.time()
    try:
        for path in RENDER_DIR.iterdir():
            if not path.is_file():
                continue
            try:
                if now - path.stat().st_mtime > RENDER_CACHE_TTL_SECONDS:
                    path.unlink()
            except OSError:
                continue
    except OSError:
        pass


def _find_font_path(bold: bool = False) -> str | None:
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_path = _find_font_path(bold=bold)
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _card_size(height: int) -> tuple[int, int]:
    return (round(height * CARD_REFERENCE_RATIO), height)


def resolve_asset_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    text = str(path_value).strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path if path.exists() and path.is_file() else None


def _load_background(name: str, size: tuple[int, int], fallback_color: str) -> Image.Image:
    path = VISUAL_DIR / name
    if path.exists():
        try:
            image = Image.open(path).convert("RGBA")
            return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        except Exception:
            pass
    return Image.new("RGBA", size, fallback_color)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = str(text or "").strip()
    if draw.textlength(text, font=font) <= max_width:
        return text
    value = text
    while len(value) > 3:
        value = value[:-1]
        shortened = value + "..."
        if draw.textlength(shortened, font=font) <= max_width:
            return shortened
    return text[:10]


def _placeholder_card(card: Any, size: tuple[int, int]) -> Image.Image:
    width, height = size
    rarity = getattr(card, "rarity", "")
    color = RARITY_COLORS.get(rarity, "#4da3ff")
    image = Image.new("RGBA", size, (8, 10, 16, 255))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=22, fill=(12, 17, 28, 255), outline=color, width=5)
    draw.rectangle((10, 10, width - 11, height - 11), outline=(255, 255, 255, 60), width=2)

    overall = str(getattr(card, "overall", "—"))
    position = str(getattr(card, "position", "—"))
    name = str(getattr(card, "name", "NO IMAGE"))
    team = str(getattr(card, "team", ""))

    draw.text((22, 20), overall, font=_font(max(28, height // 12), bold=True), fill="white")
    draw.text((24, 20 + max(38, height // 12)), position, font=_font(max(18, height // 30), bold=True), fill=(210, 230, 255))

    center_y = height // 2
    draw.text((width // 2, center_y - 20), "NO CARD", font=_font(max(24, height // 18), bold=True), fill=(210, 225, 250), anchor="mm")
    draw.text((width // 2, center_y + 25), "IMAGE", font=_font(max(22, height // 22), bold=True), fill=(160, 190, 230), anchor="mm")

    name_font = _font(max(22, height // 24), bold=True)
    small_font = _font(max(15, height // 36), bold=True)
    name = _fit_text(draw, name.upper(), name_font, width - 28)
    team = _fit_text(draw, team.upper(), small_font, width - 28)
    draw.text((width // 2, height - 76), name, font=name_font, fill="white", anchor="mm")
    if team:
        draw.text((width // 2, height - 40), team, font=small_font, fill=(190, 215, 255), anchor="mm")

    return image


def _load_card_visual(card: Any, size: tuple[int, int]) -> Image.Image:
    path = resolve_asset_path(getattr(card, "image_path", None))
    if path is None:
        return _placeholder_card(card, size)
    try:
        image = Image.open(path).convert("RGBA")
        # Именно растягиваем/сжимаем к единому стандарту, как просил пользователь.
        return image.resize(size, Image.Resampling.LANCZOS)
    except Exception:
        return _placeholder_card(card, size)


def _paste_shadowed_card(base: Image.Image, card: Any, center: tuple[int, int], card_size: tuple[int, int], angle: float = 0) -> None:
    card_image = _load_card_visual(card, card_size)
    if angle:
        card_image = card_image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)

    x = center[0] - card_image.width // 2
    y = center[1] - card_image.height // 2

    # Простая тень: смещённая полупрозрачная подложка.
    shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.rounded_rectangle((x + 8, y + 10, x + card_image.width + 8, y + card_image.height + 10), radius=18, fill=(0, 0, 0, 110))
    base.alpha_composite(shadow_layer)
    base.alpha_composite(card_image, dest=(x, y))


def _draw_ovr_text(image: Image.Image, overview: LineupOverview | None, fallback_ovr: int | None = None) -> None:
    draw = ImageDraw.Draw(image)
    base_ovr = overview.average_overall if overview is not None else fallback_ovr
    chemistry = overview.chemistry_bonus if overview is not None else 0
    text = f"OVR: {base_ovr if base_ovr is not None else 'XX'} (+{chemistry})"
    x, y = 28, image.height - 86

    # Белая подложка как на референсе, чтобы текст читался на льду.
    bbox = draw.textbbox((x, y), text, font=_font(58, bold=True))
    draw.rounded_rectangle((bbox[0] - 14, bbox[1] - 8, bbox[2] + 14, bbox[3] + 8), radius=12, fill=(255, 255, 255, 195))
    draw.text((x, y), text, font=_font(58, bold=True), fill=(0, 0, 0))


def render_lineup_image(overview: LineupOverview, user_id: int, title: str | None = None) -> Path:
    size = LINEUP_CANVAS_SIZE
    image = _load_background("lineup_match_bg.png", size, "#071322")
    if image is None:
        image = _load_background("lineup_bg.png", size, "#071322")
    draw = ImageDraw.Draw(image)

    if title:
        draw.rounded_rectangle((28, 26, min(720, 70 + len(title) * 24), 82), radius=18, fill=(0, 0, 0, 135))
        draw.text((50, 38), title, font=_font(32, bold=True), fill="white")

    card_size = _card_size(LINEUP_CARD_HEIGHT)
    positions = {
        "F1": (314, 215),
        "F2": (768, 215),
        "F3": (1222, 215),
        "D1": (510, 575),
        "G": (768, 625),
        "D2": (1026, 575),
    }

    for slot_code in ["F1", "F2", "F3", "D1", "G", "D2"]:
        card = overview.slots.get(slot_code)
        center = positions[slot_code]
        if card is None:
            slot_info = get_slot_info(slot_code)
            placeholder = type("PlaceholderCard", (), {
                "name": slot_info.title,
                "overall": "—",
                "position": slot_info.short_title,
                "team": "EMPTY SLOT",
                "rarity": "Common",
                "image_path": "",
            })()
            _paste_shadowed_card(image, placeholder, center, card_size)
        else:
            _paste_shadowed_card(image, card, center, card_size)

    _draw_ovr_text(image, overview)
    cleanup_render_cache()
    output = RENDER_DIR / f"lineup_{user_id}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output


def render_opponent_lineup_placeholder(opponent_name: str, opponent_ovr: int, user_id: int) -> Path:
    size = LINEUP_CANVAS_SIZE
    image = _load_background("lineup_match_bg.png", size, "#071322")
    draw = ImageDraw.Draw(image)
    title = f"СОСТАВ СОПЕРНИКА: {opponent_name}"
    draw.rounded_rectangle((28, 26, min(900, 70 + len(title) * 20), 82), radius=18, fill=(0, 0, 0, 150))
    draw.text((50, 38), title, font=_font(30, bold=True), fill="white")

    card_size = _card_size(LINEUP_CARD_HEIGHT)
    positions = [(314, 215), (768, 215), (1222, 215), (510, 575), (768, 625), (1026, 575)]
    labels = ["FWD", "FWD", "FWD", "DEF", "GK", "DEF"]
    for index, center in enumerate(positions, start=1):
        placeholder = type("OpponentCard", (), {
            "name": f"{opponent_name} #{index}",
            "overall": opponent_ovr,
            "position": labels[index - 1],
            "team": "BOT TEAM",
            "rarity": "Rare",
            "image_path": "",
        })()
        _paste_shadowed_card(image, placeholder, center, card_size)

    _draw_ovr_text(image, None, fallback_ovr=opponent_ovr)
    cleanup_render_cache()
    output = RENDER_DIR / f"opponent_lineup_{user_id}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output


def render_collection_image(cards_page: PlayerCardsPage, user_id: int) -> Path:
    size = COLLECTION_CANVAS_SIZE
    # Для коллекции нужен чистый тёмный фон, без уже нарисованных карточек.
    image = Image.new("RGBA", size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    # Неброская графика на фоне, чтобы сетка не была пустой.
    for y in range(0, size[1], 96):
        draw.line((0, y, size[0], y + 28), fill=(255, 255, 255, 10), width=2)
    for x in range(0, size[0], 160):
        draw.line((x, 0, x + 80, size[1]), fill=(70, 130, 180, 10), width=2)

    card_size = _card_size(COLLECTION_CARD_HEIGHT)
    card_w, card_h = card_size
    gap_x = (size[0] - 4 * card_w) // 5
    x_values = [gap_x + i * (card_w + gap_x) for i in range(4)]
    y_values = [42, 430]

    for idx in range(8):
        x = x_values[idx % 4]
        y = y_values[idx // 4]
        center = (x + card_w // 2, y + card_h // 2)
        if idx < len(cards_page.cards):
            _paste_shadowed_card(image, cards_page.cards[idx], center, card_size)
        else:
            placeholder = type("EmptyCard", (), {
                "name": "EMPTY",
                "overall": "—",
                "position": "—",
                "team": "SLOT",
                "rarity": "Common",
                "image_path": "",
            })()
            _paste_shadowed_card(image, placeholder, center, card_size)

    footer = f"{cards_page.page}/{cards_page.pages_count} · всего карт: {cards_page.total_count}"
    draw.rounded_rectangle((size[0] - 360, size[1] - 56, size[0] - 28, size[1] - 20), radius=12, fill=(0, 0, 0, 160))
    draw.text((size[0] - 344, size[1] - 50), footer, font=_font(20, bold=True), fill=(230, 240, 255))

    cleanup_render_cache()
    output = RENDER_DIR / f"collection_{user_id}_{cards_page.page}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output


def render_card_profile_image(card: Any, user_id: int = 0) -> Path:
    card_size = _card_size(PROFILE_CARD_HEIGHT)
    image = _load_card_visual(card, card_size)
    cleanup_render_cache()
    card_id = getattr(card, "id", getattr(card, "card_id", "card"))
    output = RENDER_DIR / f"card_{user_id}_{card_id}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output
