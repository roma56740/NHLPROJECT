from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

from app.services.lineup import LINEUP_SLOT_ORDER, LineupCard, LineupOverview, get_slot_info
from app.database.db import get_connection
from app.services.user_cards import PlayerCardsPage, PlayerCardListItem
from app.services.render_theme import get_render_theme_config, asset_absolute_path

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


def _load_background(
    name: str,
    size: tuple[int, int],
    fallback_color: str,
    override_path: str | None = None,
) -> Image.Image:
    """CLAN WAR 2.0: `override_path` — путь к экипированному BACKGROUND-предмету
    игрока (app.services.war2_cosmetics.get_equipped_background_path). Опциональный
    параметр по умолчанию None — существующие вызовы без него дают тот же результат,
    что и раньше, байт-в-байт."""
    if override_path:
        resolved = resolve_asset_path(override_path)
        if resolved is not None:
            try:
                image = Image.open(resolved).convert("RGBA")
                return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
            except Exception:
                pass

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


def _hex_rgb(value: str, fallback: tuple[int, int, int] = (76, 184, 255)) -> tuple[int, int, int]:
    try:
        raw = value.strip().lstrip("#")
        if len(raw) != 6:
            raise ValueError
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (*top, 255))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(round(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=(*color, 255))
    return image


def _load_custom_or_generated_background(path_value: str | None, size: tuple[int, int], accent: str) -> Image.Image:
    path = asset_absolute_path(path_value)
    if path is not None:
        try:
            return ImageOps.fit(Image.open(path).convert("RGBA"), size, method=Image.Resampling.LANCZOS)
        except Exception:
            pass
    accent_rgb = _hex_rgb(accent)
    top = tuple(max(4, int(channel * 0.10)) for channel in accent_rgb)
    image = _vertical_gradient(size, top, (4, 8, 15))
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(7):
        x = round(size[0] * (0.05 + index * 0.15))
        draw.polygon(
            [(x, 0), (x + round(size[0] * 0.07), 0), (x + round(size[0] * 0.22), size[1]), (x - round(size[0] * 0.03), size[1])],
            fill=(*accent_rgb, 7 if index % 2 == 0 else 4),
        )
    return image


def _add_vignette(image: Image.Image, strength: int = 150) -> None:
    width, height = image.size
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    margin_x = max(30, width // 8)
    margin_y = max(30, height // 8)
    draw.ellipse((-margin_x, -margin_y, width + margin_x, height + margin_y), fill=230)
    mask = ImageOps.invert(mask).filter(ImageFilter.GaussianBlur(radius=max(width, height) // 10))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, min(255, strength)))
    overlay.putalpha(mask.point(lambda value: min(255, value * strength // 255)))
    image.alpha_composite(overlay)


def _draw_glass_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int = 24,
    fill: tuple[int, int, int, int] = (6, 11, 19, 178),
    outline: tuple[int, int, int, int] = (255, 255, 255, 28),
    width: int = 2,
) -> None:
    ImageDraw.Draw(image, "RGBA").rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw_accent_rule(image: Image.Image, box: tuple[int, int, int, int], accent: str, alpha: int = 255) -> None:
    color = _hex_rgb(accent)
    ImageDraw.Draw(image, "RGBA").rounded_rectangle(box, radius=max(2, (box[3] - box[1]) // 2), fill=(*color, alpha))


def _draw_glow_line(image: Image.Image, p1: tuple[int, int], p2: tuple[int, int], color: tuple[int, int, int], width: int = 6) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    gd.line((*p1, *p2), fill=(*color, 175), width=width + 12)
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=11)))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.line((*p1, *p2), fill=(*color, 230), width=width)
    draw.line((*p1, *p2), fill=(255, 255, 255, 110), width=max(1, width // 3))


def _chemistry_pair_score(left: Any | None, right: Any | None) -> int:
    if left is None or right is None:
        return 0
    score = 0
    if getattr(left, "team", "") and str(left.team).casefold() == str(getattr(right, "team", "")).casefold():
        score += 2
    if getattr(left, "country", "") and str(left.country).casefold() == str(getattr(right, "country", "")).casefold():
        score += 1
    lc = str(getattr(left, "collection_code", getattr(left, "collection_name", ""))).casefold()
    rc = str(getattr(right, "collection_code", getattr(right, "collection_name", ""))).casefold()
    if lc and lc == rc:
        score += 1
    return score


def _chemistry_visual(score: int) -> tuple[int, int, int]:
    if score >= 3:
        return (236, 190, 74)
    if score >= 1:
        return (76, 184, 255)
    return (220, 73, 88)


def _format_compact_amount(value: int | None) -> str:
    amount = int(value or 0)
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(amount) >= 1_000:
        return f"{amount / 1_000:.0f}K"
    return str(amount)


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


def _paste_shadowed_card(
    base: Image.Image,
    card: Any,
    center: tuple[int, int],
    card_size: tuple[int, int],
    angle: float = 0,
    frame_override_path: str | None = None,
) -> None:
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

    # CLAN WAR 2.0: экипированный FRAME поверх карты (app.services.war2_cosmetics.
    # get_equipped_frame_path). None по умолчанию — обычные карты выглядят как раньше.
    if frame_override_path:
        frame_path = resolve_asset_path(frame_override_path)
        if frame_path is not None:
            try:
                frame_image = Image.open(frame_path).convert("RGBA").resize(card_image.size, Image.Resampling.LANCZOS)
                base.alpha_composite(frame_image, dest=(x, y))
            except Exception:
                pass


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


def _draw_simple_ovr_text(image: Image.Image, overall: int) -> None:
    """Тот же визуал, что _draw_ovr_text, но без химии/LineupOverview — для CLAN WAR
    2.0, где состав не 6-слотовый и бонус химии не считается (см. war2_draft.py:
    compute_war2_lineup_ovr)."""
    draw = ImageDraw.Draw(image)
    text = f"OVR: {overall}"
    x, y = 28, image.height - 86
    bbox = draw.textbbox((x, y), text, font=_font(58, bold=True))
    draw.rounded_rectangle((bbox[0] - 14, bbox[1] - 8, bbox[2] + 14, bbox[3] + 8), radius=12, fill=(255, 255, 255, 195))
    draw.text((x, y), text, font=_font(58, bold=True), fill=(0, 0, 0))


def _draw_nickname_badge(image: Image.Image, nickname: str, badge_text: str | None) -> None:
    """CLAN WAR 2.0 NICK_BADGE (раздел ТЗ "NICK BADGE"): подпись вида "Hudson [GOAT]"
    в правом верхнем углу — тот же rounded-rect+text идиома, что и у _draw_ovr_text."""
    if not badge_text:
        return
    draw = ImageDraw.Draw(image)
    text = f"{nickname} [{badge_text}]"
    font = _font(30, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = image.width - text_width - 42
    y = 28
    padded_bbox = draw.textbbox((x, y), text, font=font)
    draw.rounded_rectangle((padded_bbox[0] - 14, padded_bbox[1] - 8, padded_bbox[2] + 14, padded_bbox[3] + 8), radius=12, fill=(0, 0, 0, 150))
    draw.text((x, y), text, font=font, fill="white")


def _bound_frame_paths(cards: list[Any]) -> dict[int, str]:
    user_card_ids = sorted({
        int(getattr(card, "user_card_id", getattr(card, "id", 0)) or 0)
        for card in cards
        if int(getattr(card, "user_card_id", getattr(card, "id", 0)) or 0) > 0
    })
    if not user_card_ids:
        return {}
    placeholders = ",".join("?" for _ in user_card_ids)
    try:
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT ucf.user_card_id, wci.image_path
                FROM user_card_frames ucf
                JOIN user_cosmetic_items uci ON uci.id = ucf.user_cosmetic_item_id
                JOIN war2_cosmetic_items wci ON wci.id = uci.cosmetic_item_id
                WHERE ucf.user_card_id IN ({placeholders})
                """,
                user_card_ids,
            ).fetchall()
        return {int(row["user_card_id"]): row["image_path"] for row in rows if row["image_path"]}
    except Exception:
        return {}


def _card_bound_frame(card: Any, paths: dict[int, str]) -> str | None:
    user_card_id = int(getattr(card, "user_card_id", getattr(card, "id", 0)) or 0)
    return paths.get(user_card_id)


def render_lineup_image(
    overview: LineupOverview,
    user_id: int,
    title: str | None = None,
    background_override_path: str | None = None,
    frame_override_path: str | None = None,
    show_salary_cap: bool = False,
) -> Path:
    """Unified premium 3F/2D/1G lineup render.

    Personal background overrides the admin default. A card-frame cosmetic is always
    loaded from the concrete user_card binding; it is never applied globally to all cards.
    Salary cap is rendered only when the caller explicitly requests it (Ranked).
    """
    cfg = get_render_theme_config()
    size = LINEUP_CANVAS_SIZE
    bg_path = background_override_path or cfg.lineup_background_path
    image = _load_custom_or_generated_background(bg_path, size, cfg.lineup_accent)
    image.alpha_composite(Image.new("RGBA", size, (3, 8, 15, 78)))
    _add_vignette(image, 170)
    draw = ImageDraw.Draw(image, "RGBA")
    accent_rgb = _hex_rgb(cfg.lineup_accent)

    _draw_glass_panel(image, (28, 22, 1508, 128), radius=26, fill=(4, 9, 16, 202))
    _draw_accent_rule(image, (28, 22, 40, 128), cfg.lineup_accent)
    draw.text((64, 43), (title or "MAIN LINEUP").upper(), font=_font(38, bold=True), fill=(248, 251, 255, 255))
    draw.text((65, 88), "3 FWD · 2 DEF · 1 GK", font=_font(17, bold=True), fill=(158, 175, 195, 230))

    salary_value = _format_compact_amount(overview.salary_total)
    if show_salary_cap:
        salary_value = f"{salary_value} / {_format_compact_amount(overview.salary_cap)}"
    metrics = [
        (870, "OVR", str(overview.final_overall if overview.final_overall is not None else "—")),
        (1085, "CHEM", f"+{overview.chemistry_bonus}"),
        (1300, "SALARY", salary_value),
    ]
    for x, label, value in metrics:
        draw.text((x, 43), label, font=_font(16, bold=True), fill=(139, 158, 180, 240))
        draw.text((x, 70), value, font=_font(31, bold=True), fill=(248, 251, 255, 255))

    card_height = 278
    card_size = _card_size(card_height)
    positions = {
        "F1": (334, 310), "F2": (768, 310), "F3": (1202, 310),
        "D1": (520, 645), "G": (768, 665), "D2": (1016, 645),
    }

    if cfg.lineup_chemistry_enabled:
        for left_code, right_code in [
            ("F1", "F2"), ("F2", "F3"), ("F1", "D1"), ("F2", "D1"),
            ("F2", "D2"), ("F3", "D2"), ("D1", "G"), ("D2", "G"),
        ]:
            score = _chemistry_pair_score(overview.slots.get(left_code), overview.slots.get(right_code))
            color = _chemistry_visual(score)
            p1, p2 = positions[left_code], positions[right_code]
            _draw_glow_line(image, p1, p2, color, width=5)
            mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
            draw.ellipse((mx - 18, my - 18, mx + 18, my + 18), fill=(4, 8, 14, 228), outline=(*color, 230), width=3)
            draw.text((mx, my - 1), str(score), font=_font(17, bold=True), fill="white", anchor="mm")

    owned_cards = [card for card in overview.slots.values() if card is not None]
    frame_paths = _bound_frame_paths(owned_cards)
    for slot_code in ["F1", "F2", "F3", "D1", "G", "D2"]:
        center = positions[slot_code]
        card = overview.slots.get(slot_code)
        x1 = center[0] - card_size[0] // 2 - 12
        y1 = center[1] - card_size[1] // 2 - 12
        x2 = center[0] + card_size[0] // 2 + 12
        y2 = center[1] + card_size[1] // 2 + 12
        _draw_glass_panel(image, (x1, y1, x2, y2), radius=24, fill=(4, 9, 17, 168), outline=(*accent_rgb, 78), width=2)
        _draw_accent_rule(image, (x1 + 18, y1 + 7, x2 - 18, y1 + 12), cfg.lineup_accent, alpha=210)
        if card is None:
            slot_info = get_slot_info(slot_code)
            placeholder = type("PlaceholderCard", (), {
                "name": slot_info.title, "overall": "—", "position": slot_info.short_title,
                "team": "EMPTY SLOT", "rarity": "Common", "image_path": "",
            })()
            _paste_shadowed_card(image, placeholder, center, card_size)
        else:
            _paste_shadowed_card(
                image, card, center, card_size,
                frame_override_path=_card_bound_frame(card, frame_paths) or frame_override_path,
            )
        label = "GK" if slot_code == "G" else ("DEF" if slot_code.startswith("D") else "FWD")
        pill_w = 58 if label == "GK" else 72
        px1, py1 = center[0] - pill_w // 2, y2 - 7
        draw.rounded_rectangle((px1, py1, px1 + pill_w, py1 + 31), radius=15, fill=(5, 10, 18, 238), outline=(*accent_rgb, 155), width=2)
        draw.text((center[0], py1 + 15), label, font=_font(14, bold=True), fill="white", anchor="mm")

    if cfg.lineup_chemistry_enabled:
        x, y = 54, 824
        draw.text((x, y), "CHEMISTRY", font=_font(15, bold=True), fill=(164, 181, 200, 240), anchor="lm")
        x += 118
        for color, label in [((236, 190, 74), "ELITE 3+"), ((76, 184, 255), "GOOD 1–2"), ((220, 73, 88), "WEAK 0")]:
            draw.ellipse((x, y - 7, x + 14, y + 7), fill=(*color, 255))
            draw.text((x + 22, y), label, font=_font(14, bold=True), fill=(218, 228, 240, 245), anchor="lm")
            x += 135

    cleanup_render_cache()
    output = RENDER_DIR / f"lineup_{user_id}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output


WAR2_CANVAS_SIZE = (1536, 864)
WAR2_CARD_HEIGHT = 320


def _cards_to_standard_slots(cards: list[LineupCard]) -> dict[str, LineupCard | None]:
    slots: dict[str, LineupCard | None] = {code: None for code in LINEUP_SLOT_ORDER}
    queues = {"F": ["F1", "F2", "F3"], "D": ["D1", "D2"], "G": ["G"]}
    overflow: list[LineupCard] = []
    for card in cards:
        position = str(getattr(card, "position", "")).upper()
        normalized = "G" if position in {"G", "GK", "GOALIE"} else ("D" if position.startswith("D") else "F")
        if queues[normalized]:
            slots[queues[normalized].pop(0)] = card
        else:
            overflow.append(card)
    remaining = [code for code in ("F1", "F2", "F3", "D1", "D2") if slots[code] is None]
    for card, slot in zip(overflow, remaining):
        slots[slot] = card
    return slots


def render_war2_lineup_image(
    cards: list[LineupCard],
    user_id: int,
    average_overall: int,
    title: str | None = None,
    background_override_path: str | None = None,
    frame_override_path: str | None = None,
    nickname: str | None = None,
    badge_text: str | None = None,
) -> Path:
    """Clan Wars uses the same visual shell as the ordinary lineup."""
    slots = _cards_to_standard_slots(cards)
    overview = LineupOverview(
        slots=slots,
        filled_count=sum(card is not None for card in slots.values()),
        total_slots=6,
        average_overall=average_overall,
        chemistry_bonus=0,
        final_overall=average_overall,
        chemistry_bonuses=[],
        is_complete=all(card is not None for card in slots.values()),
        salary_total=sum(int(getattr(card, "salary", 0) or 0) for card in cards),
        salary_cap=0,
    )
    base_path = render_lineup_image(
        overview, user_id=user_id, title=title or "CLAN WAR 2.0",
        background_override_path=background_override_path,
        frame_override_path=frame_override_path, show_salary_cap=False,
    )
    if not nickname or not badge_text:
        return base_path
    try:
        image = Image.open(base_path).convert("RGBA")
        _draw_nickname_badge(image, nickname, badge_text)
        output = RENDER_DIR / f"war2_{user_id}_{time.time_ns()}.png"
        image.convert("RGB").save(output, quality=95)
        try:
            base_path.unlink()
        except OSError:
            pass
        return output
    except Exception:
        return base_path


def _bot_pool_rows_for_position(overall: int, position: str) -> list[Any]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT cards.id, cards.name, cards.player_key, cards.position, cards.overall,
                   cards.team, cards.country, cards.rarity, cards.image_path, cards.salary,
                   collections.name AS collection_name, collections.code AS collection_code
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1 AND collections.active = 1
              AND cards.overall = ? AND cards.position = ?
            ORDER BY RANDOM()
            """,
            (int(overall), position),
        ).fetchall()
    return list(rows)


def _all_bot_pool_rows(overall: int) -> list[Any]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT cards.id, cards.name, cards.player_key, cards.position, cards.overall,
                   cards.team, cards.country, cards.rarity, cards.image_path, cards.salary,
                   collections.name AS collection_name, collections.code AS collection_code
            FROM cards
            JOIN collections ON collections.id = cards.collection_id
            WHERE cards.active = 1 AND collections.active = 1 AND cards.overall = ?
            ORDER BY RANDOM()
            """, (int(overall),)
        ).fetchall()
    return list(rows)


def _row_to_bot_lineup_card(row: Any, slot: str) -> LineupCard:
    return LineupCard(
        user_card_id=-int(row["id"]), card_id=int(row["id"]), name=row["name"],
        player_key=row["player_key"], position=row["position"], overall=int(row["overall"]),
        team=row["team"], country=row["country"], collection_name=row["collection_name"],
        rarity=row["rarity"], image_path=row["image_path"], lineup_slot=slot,
        collection_code=row["collection_code"], salary=int(row["salary"] or 0),
    )


def _build_real_bot_slots(opponent_ovr: int) -> dict[str, LineupCard | None]:
    """Every bot card is a real active catalog card with exactly opponent_ovr."""
    slots: dict[str, LineupCard | None] = {code: None for code in LINEUP_SLOT_ORDER}
    plan = [("F", ["F1", "F2", "F3"]), ("D", ["D1", "D2"]), ("G", ["G"])]
    used_ids: set[int] = set()
    for position, slot_codes in plan:
        rows = _bot_pool_rows_for_position(opponent_ovr, position)
        if rows:
            idx = 0
            for slot in slot_codes:
                row = rows[idx % len(rows)]
                idx += 1
                slots[slot] = _row_to_bot_lineup_card(row, slot)
                used_ids.add(int(row["id"]))

    # Never invent a fake card or change OVR. If some positional catalog slice is
    # empty, fill remaining visual slots with any real exact-OVR cards.
    exact_rows = _all_bot_pool_rows(opponent_ovr)
    if exact_rows:
        idx = 0
        for slot in [code for code, card in slots.items() if card is None]:
            candidates = [row for row in exact_rows if int(row["id"]) not in used_ids] or exact_rows
            row = candidates[idx % len(candidates)]
            idx += 1
            slots[slot] = _row_to_bot_lineup_card(row, slot)
            used_ids.add(int(row["id"]))
    return slots


def render_opponent_lineup_placeholder(opponent_name: str, opponent_ovr: int, user_id: int) -> Path:
    slots = _build_real_bot_slots(opponent_ovr)
    cards = [card for card in slots.values() if card is not None]
    overview = LineupOverview(
        slots=slots, filled_count=len(cards), total_slots=6, average_overall=opponent_ovr,
        chemistry_bonus=0, final_overall=opponent_ovr, chemistry_bonuses=[],
        is_complete=len(cards) == 6, salary_total=sum(card.salary for card in cards), salary_cap=0,
    )
    return render_lineup_image(overview, user_id=user_id, title=f"СОСТАВ СОПЕРНИКА: {opponent_name}", show_salary_cap=False)


def render_collection_image(cards_page: PlayerCardsPage, user_id: int) -> Path:
    cfg = get_render_theme_config()
    size = COLLECTION_CANVAS_SIZE
    image = _load_custom_or_generated_background(None, size, cfg.menu_accent)
    image.alpha_composite(Image.new("RGBA", size, (2, 6, 12, 105)))
    _add_vignette(image, 145)
    draw = ImageDraw.Draw(image, "RGBA")
    accent_rgb = _hex_rgb(cfg.menu_accent)
    _draw_glass_panel(image, (28, 24, 1508, 118), radius=24, fill=(4, 9, 16, 206))
    _draw_accent_rule(image, (28, 24, 40, 118), cfg.menu_accent)
    draw.text((64, 43), "COLLECTION", font=_font(38, bold=True), fill="white")
    draw.text((65, 86), "YOUR PLAYER CARDS", font=_font(16, bold=True), fill=(151, 169, 190, 240))
    draw.text((1245, 42), f"{cards_page.total_count}", font=_font(36, bold=True), fill="white")
    draw.text((1246, 84), "CARDS OWNED", font=_font(15, bold=True), fill=(151, 169, 190, 240))

    card_height = 300
    card_size = _card_size(card_height)
    card_w, card_h = card_size
    gap_x = (size[0] - 4 * card_w) // 5
    x_values = [gap_x + i * (card_w + gap_x) for i in range(4)]
    y_values = [150, 506]
    frame_paths = _bound_frame_paths(list(cards_page.cards))
    for idx in range(8):
        x, y = x_values[idx % 4], y_values[idx // 4]
        center = (x + card_w // 2, y + card_h // 2)
        _draw_glass_panel(image, (x - 10, y - 10, x + card_w + 10, y + card_h + 28), radius=22, fill=(4, 8, 15, 165), outline=(255, 255, 255, 20))
        if idx < len(cards_page.cards):
            card = cards_page.cards[idx]
            _paste_shadowed_card(image, card, center, card_size, frame_override_path=_card_bound_frame(card, frame_paths))
            status = "LINEUP" if getattr(card, "is_in_lineup", False) else ("LOCKED" if getattr(card, "trade_locked", False) else getattr(card, "position", ""))
            draw.text((center[0], y + card_h + 12), status, font=_font(13, bold=True), fill=(*accent_rgb, 240), anchor="mm")
        else:
            draw.rounded_rectangle((x + 16, y + 16, x + card_w - 16, y + card_h - 16), radius=16, outline=(255, 255, 255, 28), width=2)
            draw.text(center, "EMPTY", font=_font(18, bold=True), fill=(126, 143, 163, 180), anchor="mm")
    draw.text((1508, 838), f"PAGE {cards_page.page} / {cards_page.pages_count}", font=_font(17, bold=True), fill=(174, 190, 208, 235), anchor="rs")
    cleanup_render_cache()
    output = RENDER_DIR / f"collection_{user_id}_{cards_page.page}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output


def render_card_profile_image(card: Any, user_id: int = 0) -> Path:
    cfg = get_render_theme_config()
    size = (900, 1400)
    rarity = str(getattr(card, "rarity", "Rare"))
    rarity_color = RARITY_COLORS.get(rarity, cfg.menu_accent)
    image = _load_custom_or_generated_background(None, size, rarity_color)
    image.alpha_composite(Image.new("RGBA", size, (2, 5, 11, 80)))
    _add_vignette(image, 175)
    draw = ImageDraw.Draw(image, "RGBA")
    accent_rgb = _hex_rgb(rarity_color)
    draw.text((54, 44), "PLAYER CARD", font=_font(18, bold=True), fill=(162, 180, 202, 245))
    draw.text((54, 78), str(getattr(card, "name", "PLAYER")).upper(), font=_font(42, bold=True), fill="white")
    draw.text((846, 66), str(getattr(card, "overall", "—")), font=_font(62, bold=True), fill="white", anchor="ra")
    draw.text((846, 114), str(getattr(card, "position", "")), font=_font(18, bold=True), fill=(*accent_rgb, 255), anchor="ra")

    card_height = 980
    card_size = _card_size(card_height)
    center = (450, 700)
    _draw_glass_panel(image, (center[0] - card_size[0] // 2 - 18, 174, center[0] + card_size[0] // 2 + 18, 174 + card_size[1] + 36), radius=28, fill=(4, 8, 15, 160), outline=(*accent_rgb, 68), width=2)
    frame_path = _card_bound_frame(card, _bound_frame_paths([card]))
    _paste_shadowed_card(image, card, center, card_size, frame_override_path=frame_path)

    _draw_glass_panel(image, (44, 1214, 856, 1360), radius=24, fill=(4, 9, 16, 214))
    fields = [
        ("TEAM", str(getattr(card, "team", "—"))),
        ("SET", str(getattr(card, "collection_name", "—"))),
        ("SALARY", _format_compact_amount(getattr(card, "salary", 0))),
        ("STATUS", "LINEUP" if getattr(card, "is_in_lineup", False) else ("LOCKED" if getattr(card, "trade_locked", False) else "AVAILABLE")),
    ]
    for (label, value), x, max_w in zip(fields, [72, 294, 552, 726], [196, 236, 150, 110]):
        draw.text((x, 1240), label, font=_font(14, bold=True), fill=(142, 160, 181, 235))
        draw.text((x, 1271), _fit_text(draw, value.upper(), _font(18, bold=True), max_w), font=_font(18, bold=True), fill="white")
    draw.text((72, 1320), f"INSTANCE #{getattr(card, 'id', getattr(card, 'user_card_id', getattr(card, 'card_id', '—')))}", font=_font(13, bold=True), fill=(112, 131, 154, 230))
    cleanup_render_cache()
    card_id = getattr(card, "id", getattr(card, "card_id", "card"))
    output = RENDER_DIR / f"card_{user_id}_{card_id}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=95)
    return output


PREVIEW_DIR = ROOT_DIR / "data" / "render_cache" / "black_market_previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def render_black_market_item_preview(
    *,
    item_type: str,
    cache_key: str,
    image_path: str | None,
    rarity: str = "Common",
    cosmetic_type: str | None = None,
) -> Path:
    """Превью товара BLACK MARKET для витрины/админ-панели (раздел 2 ТЗ аудита).

    Переиспользует ТОТ ЖЕ compositor, что и весь остальной рендеринг игры — CARD идёт
    через render_card_profile_image (без второго движка), FRAME/BACKGROUND — демо-карта
    с применённым предметом через _paste_shadowed_card/_load_background (те же функции,
    которыми уже рендерится экипировка CLAN WAR 2.0). `_load_card_visual`/`_load_background`
    уже дают безопасную заглушку при отсутствующем/битом asset — здесь ничего
    дополнительно на этот счёт делать не нужно.

    Кэшируется по `cache_key` (стабильный, например f"pool_item_{id}") — повторный вызов
    для того же предмета переиспользует уже отрендеренный файл вместо перерисовки.
    Это НЕ тот же TTL-кэш, что RENDER_DIR/cleanup_render_cache() (тот подходит для
    "рендерится один раз на конкретный экран и больше не нужен"; здесь наоборот —
    превью долгоживущее и должно инвалидироваться явно при правке предмета пула,
    см. invalidate_black_market_preview(), а не по времени).
    """
    safe_key = "".join(char if char.isalnum() or char in "-_" else "_" for char in cache_key)
    output = PREVIEW_DIR / f"{safe_key}.png"
    if output.exists():
        return output

    if item_type == "card":
        demo_card = type(
            "BMCardPreview", (), {"id": safe_key, "name": "?", "overall": "?", "position": "?", "team": "", "rarity": rarity, "image_path": image_path}
        )()
        card_size = _card_size(PROFILE_CARD_HEIGHT)
        image = _load_card_visual(demo_card, card_size)
    else:
        demo_card = type(
            "BMDemoCard", (), {"name": "DEMO CARD", "overall": 88, "position": "F", "team": "PREVIEW", "rarity": rarity, "image_path": ""}
        )()
        card_size = _card_size(PROFILE_CARD_HEIGHT)
        canvas_size = (card_size[0] + 140, card_size[1] + 140)
        center = (canvas_size[0] // 2, canvas_size[1] // 2)

        if cosmetic_type in ("BACKGROUND", "PROFILE_BACKGROUND"):
            image = _load_background("lineup_match_bg.png", canvas_size, "#071322", override_path=image_path)
            _paste_shadowed_card(image, demo_card, center, card_size)
        else:
            # FRAME (или неизвестный косметический подтип — тоже показываем поверх демо-карты,
            # это самый информативный fallback для превью).
            image = Image.new("RGBA", canvas_size, (8, 10, 16, 255))
            _paste_shadowed_card(image, demo_card, center, card_size, frame_override_path=image_path)

    cleanup_render_cache()
    image.convert("RGB").save(output, quality=95)
    return output


def invalidate_black_market_preview(cache_key: str) -> None:
    """Удаляет закэшированное превью — вызывать при правке предмета пула, чей визуал
    мог измениться (сменили card_id/pack_id/cosmetic_item_id/rarity)."""
    safe_key = "".join(char if char.isalnum() or char in "-_" else "_" for char in cache_key)
    path = PREVIEW_DIR / f"{safe_key}.png"
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def render_main_menu_image(
    profile: Any,
    match_info: Any | None,
    user_id: int,
    background_override_path: str | None = None,
) -> Path:
    cfg = get_render_theme_config()
    size = (1024, 1280)
    bg_path = background_override_path or cfg.menu_background_path
    image = _load_custom_or_generated_background(bg_path, size, cfg.menu_accent)
    image.alpha_composite(Image.new("RGBA", size, (2, 5, 10, 86)))
    _add_vignette(image, 165)
    draw = ImageDraw.Draw(image, "RGBA")
    accent_rgb = _hex_rgb(cfg.menu_accent)

    _draw_glass_panel(image, (34, 34, 990, 166), radius=30, fill=(4, 8, 15, 206))
    draw.ellipse((58, 62, 126, 130), fill=(*accent_rgb, 28), outline=(*accent_rgb, 180), width=3)
    initials = "".join(part[:1] for part in str(getattr(profile, "nickname", "P")).split()[:2]).upper() or "P"
    draw.text((92, 96), initials, font=_font(24, bold=True), fill="white", anchor="mm")
    nickname = _fit_text(draw, str(getattr(profile, "nickname", "PLAYER")), _font(28, bold=True), 300)
    draw.text((150, 69), nickname, font=_font(28, bold=True), fill="white")
    draw.text((150, 111), f"{getattr(profile, 'league', 'LEAGUE')}  ·  {getattr(profile, 'rating_points', 0)} RP", font=_font(15, bold=True), fill=(151, 169, 190, 245))

    balances = list(getattr(profile, "balances", []) or [])[:3]
    x = 966
    for balance in reversed(balances):
        value = _format_compact_amount(getattr(balance, "amount", 0))
        label = f"{getattr(balance, 'icon', '')} {value}".strip()
        font = _font(17, bold=True)
        w = int(draw.textlength(label, font=font)) + 34
        x -= w
        draw.rounded_rectangle((x, 76, x + w, 124), radius=20, fill=(18, 26, 37, 255), outline=(48, 63, 82, 255), width=1)
        draw.text((x + 17, 100), label, font=font, fill="white", anchor="lm")
        x -= 10

    # No logo: the seasonal scene and typography are the identity.
    hero_y = 315
    draw.text((512, hero_y), cfg.menu_title.upper(), font=_font(60, bold=True), fill="white", anchor="ma")
    draw.text((512, hero_y + 72), cfg.menu_subtitle.upper(), font=_font(22, bold=True), fill=(*accent_rgb, 255), anchor="ma")
    _draw_accent_rule(image, (420, hero_y + 116, 604, hero_y + 122), cfg.menu_accent)

    block_y = 640
    _draw_glass_panel(image, (48, block_y, 976, block_y + 174), radius=28, fill=(4, 9, 16, 210), outline=(*accent_rgb, 48))
    draw.text((78, block_y + 30), "READY TO PLAY", font=_font(15, bold=True), fill=(*accent_rgb, 255))
    ready = bool(getattr(match_info, "is_ready", False)) if match_info is not None else False
    lineup_ovr = getattr(match_info, "lineup_ovr", None) if match_info is not None else None
    draw.text((78, block_y + 68), "YOUR LINEUP", font=_font(34, bold=True), fill="white")
    draw.text((78, block_y + 120), "READY" if ready else "COMPLETE YOUR LINEUP", font=_font(17, bold=True), fill=(178, 194, 212, 240))
    if lineup_ovr is not None:
        draw.text((914, block_y + 49), str(lineup_ovr), font=_font(62, bold=True), fill="white", anchor="ra")
        draw.text((914, block_y + 111), "TEAM OVR", font=_font(14, bold=True), fill=(147, 165, 186, 240), anchor="ra")

    tile_y = 846
    labels = [("LINEUP", "6"), ("CARDS", "COLLECTION"), ("MATCH", "PLAY"), ("SHOP", "PACKS")]
    gap = 14
    tile_w = (928 - gap * 3) // 4
    for index, (label, secondary) in enumerate(labels):
        x1 = 48 + index * (tile_w + gap)
        x2 = x1 + tile_w
        _draw_glass_panel(image, (x1, tile_y, x2, tile_y + 150), radius=24, fill=(5, 10, 18, 196))
        draw.text((x1 + 20, tile_y + 29), label, font=_font(18, bold=True), fill="white")
        draw.text((x1 + 20, tile_y + 73), secondary, font=_font(14, bold=True), fill=(137, 157, 180, 235))
        draw.ellipse((x2 - 50, tile_y + 100, x2 - 28, tile_y + 122), fill=(*accent_rgb, 210))

    _draw_glass_panel(image, (48, 1022, 976, 1218), radius=28, fill=(4, 9, 16, 214))
    draw.text((78, 1055), "HOCKEY PASS", font=_font(16, bold=True), fill=(147, 165, 186, 240))
    pass_level = int(getattr(profile, "hockey_pass_level", 1) or 1)
    draw.text((78, 1094), f"LEVEL {pass_level}", font=_font(38, bold=True), fill="white")
    progress = max(0.04, min(1.0, (pass_level % 10) / 10 or 1.0))
    draw.rounded_rectangle((78, 1168, 702, 1182), radius=7, fill=(34, 45, 59, 255))
    draw.rounded_rectangle((78, 1168, 78 + round(624 * progress), 1182), radius=7, fill=(*accent_rgb, 245))
    draw.text((914, 1102), "SEASON ACTIVE", font=_font(17, bold=True), fill=(*accent_rgb, 255), anchor="ra")

    cleanup_render_cache()
    output = RENDER_DIR / f"menu_{user_id}_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=94)
    return output


def render_admin_preview(kind: str, user_id: int) -> Path:
    if kind == "menu":
        Balance = type("Balance", (), {})
        balances = []
        for code, icon, amount in [("coins", "C", 2450000), ("energy", "R", 1250), ("rank", "RP", 840)]:
            item = Balance(); item.code, item.icon, item.amount = code, icon, amount; balances.append(item)
        Profile = type("Profile", (), {})
        profile = Profile(); profile.nickname = "Loko 2000"; profile.league = "NHL"; profile.rating_points = 1840; profile.hockey_pass_level = 27; profile.balances = balances
        MatchInfo = type("MatchInfo", (), {})
        match = MatchInfo(); match.is_ready = True; match.lineup_ovr = 98
        return render_main_menu_image(profile, match, user_id)
    if kind != "lineup":
        raise ValueError("unknown preview kind")
    card_paths = sorted((ROOT_DIR / "assets" / "uploads" / "cards").glob("*"))[:6]
    slots: dict[str, LineupCard | None] = {code: None for code in LINEUP_SLOT_ORDER}
    preview_order = ["F1", "F2", "F3", "D1", "G", "D2"]
    for index, slot in enumerate(preview_order):
        path = card_paths[index].as_posix() if index < len(card_paths) else ""
        position = "G" if slot == "G" else ("D" if slot.startswith("D") else "F")
        slots[slot] = LineupCard(
            user_card_id=-(index + 1), card_id=index + 1, name=f"PLAYER {index + 1}", player_key=f"preview-{index + 1}",
            position=position, overall=99 - index // 2, team=["Florida", "Edmonton", "Edmonton", "Boston", "Tampa", "Boston"][index],
            country=["USA", "Canada", "Canada", "USA", "Russia", "USA"][index], collection_name="Preview Set", rarity="Epic",
            image_path=path, lineup_slot=slot, collection_code="preview", salary=9_000_000 - index * 500_000,
        )
    overview = LineupOverview(slots=slots, filled_count=6, total_slots=6, average_overall=98, chemistry_bonus=3, final_overall=101, chemistry_bonuses=[], is_complete=True, salary_total=sum(card.salary for card in slots.values() if card), salary_cap=54_000_000)
    return render_lineup_image(overview, user_id, title="RENDER PREVIEW", show_salary_cap=False)
