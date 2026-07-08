from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.services.lineup import LINEUP_SLOT_ORDER, LineupCard, LineupOverview, get_slot_info
from app.services.user_cards import PlayerCardsPage, PlayerCardListItem

ROOT_DIR = Path(__file__).resolve().parents[2]
VISUAL_DIR = ROOT_DIR / "assets" / "visual"
RENDER_DIR = ROOT_DIR / "data" / "render_cache"
RENDER_DIR.mkdir(parents=True, exist_ok=True)

RENDER_CACHE_TTL_SECONDS = 6 * 60 * 60  # старые рендеры чистим через 6 часов


def cleanup_render_cache() -> None:
    """Удаляет устаревшие файлы из кэша рендеров, чтобы диск не переполнялся."""
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


RARITY_COLORS = {
    "Common": "#b8c0cc",
    "Rare": "#4da3ff",
    "Epic": "#9f6bff",
    "Legendary": "#ffb347",
    "Event": "#ff5f8f",
    "Icon": "#ffd95c",
}


def _find_font_path() -> str | None:
    candidates = [
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        Path('C:/Windows/Fonts/arial.ttf'),
        Path('C:/Windows/Fonts/segoeui.ttf'),
        Path('C:/Windows/Fonts/tahoma.ttf'),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


FONT_PATH = _find_font_path()


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _load_background(name: str, size: tuple[int, int], fallback_color: str) -> Image.Image:
    path = VISUAL_DIR / name
    if path.exists():
        try:
            image = Image.open(path).convert('RGBA')
            return image.resize(size)
        except Exception:
            pass
    return Image.new('RGBA', size, fallback_color)


def _safe_open_card_image(image_path: str, size: tuple[int, int]) -> Image.Image | None:
    if not image_path:
        return None
    path = Path(image_path)
    if not path.is_absolute():
        path = ROOT_DIR / image_path
    if not path.exists():
        return None
    try:
        image = Image.open(path).convert('RGBA')
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    except Exception:
        return None


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    value = text
    while len(value) > 3:
        value = value[:-1]
        shortened = value + '...'
        if draw.textlength(shortened, font=font) <= max_width:
            return shortened
    return text[:10]


def _draw_card_tile(base: Image.Image, card: LineupCard | PlayerCardListItem, box: tuple[int, int, int, int], title: str | None = None) -> None:
    draw = ImageDraw.Draw(base)
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    rarity_color = RARITY_COLORS.get(getattr(card, 'rarity', ''), '#6aa9ff')

    shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x1 + 4, y1 + 6, x2 + 4, y2 + 6), radius=20, fill=(0, 0, 0, 80))
    base.alpha_composite(shadow)

    draw.rounded_rectangle(box, radius=20, fill=(12, 23, 44, 220), outline=rarity_color, width=4)

    image_height = int(height * 0.62)
    image_box = (x1 + 12, y1 + 12, x2 - 12, y1 + 12 + image_height)
    image = _safe_open_card_image(getattr(card, 'image_path', ''), (image_box[2] - image_box[0], image_box[3] - image_box[1]))

    if image is not None:
        base.alpha_composite(image, dest=(image_box[0], image_box[1]))
    else:
        draw.rounded_rectangle(image_box, radius=16, fill=(31, 54, 87, 235), outline=(130, 180, 255, 120), width=2)
        center_x = (image_box[0] + image_box[2]) // 2
        center_y = (image_box[1] + image_box[3]) // 2
        ovr_font = _font(30)
        draw.text((center_x, center_y - 18), f"{getattr(card, 'overall', '-')}", font=ovr_font, fill='white', anchor='mm')
        draw.text((center_x, center_y + 18), getattr(card, 'position', '-'), font=_font(22), fill=(180, 215, 255), anchor='mm')

    if title:
        draw.rounded_rectangle((x1 + 10, y1 - 22, x1 + 94, y1 + 18), radius=12, fill=(15, 37, 66, 240), outline=(130, 180, 255, 120))
        draw.text((x1 + 52, y1 - 2), title, font=_font(20), fill='white', anchor='mm')

    name_font = _font(22)
    small_font = _font(18)
    stats_font = _font(17)

    text_left = x1 + 14
    text_width = width - 28
    y = image_box[3] + 10

    name = _fit_text(draw, getattr(card, 'name', ''), name_font, text_width)
    draw.text((text_left, y), name, font=name_font, fill='white')
    y += 28

    second = f"{getattr(card, 'team', '—')} · {getattr(card, 'country', '—')}"
    second = _fit_text(draw, second, small_font, text_width)
    draw.text((text_left, y), second, font=small_font, fill=(194, 217, 255))
    y += 24

    collection_name = getattr(card, 'collection_name', '—')
    collection_name = _fit_text(draw, collection_name, stats_font, text_width)
    draw.text((text_left, y), collection_name, font=stats_font, fill=(170, 200, 240))

    badge_x = x2 - 56
    badge_y = y1 + 16
    draw.rounded_rectangle((badge_x, badge_y, badge_x + 44, badge_y + 28), radius=10, fill=rarity_color)
    draw.text((badge_x + 22, badge_y + 14), str(getattr(card, 'overall', '-')), font=_font(17), fill=(15, 20, 30), anchor='mm')


def _pair_strength(left: LineupCard, right: LineupCard) -> int:
    strength = 0
    if left.team and left.team == right.team:
        strength += 1
    if left.country and left.country == right.country:
        strength += 1
    if left.collection_name and left.collection_name == right.collection_name:
        strength += 1
    return strength


def render_lineup_image(overview: LineupOverview, user_id: int) -> Path:
    size = (1600, 900)
    image = _load_background('lineup_bg.png', size, '#081a33')
    draw = ImageDraw.Draw(image)

    title_font = _font(42)
    text_font = _font(24)
    draw.text((60, 40), 'LINEUP', font=title_font, fill='white')
    draw.text((60, 92), f"OVR: {overview.average_overall or '—'}   CHEM: +{overview.chemistry_bonus}   FINAL: {overview.final_overall or '—'}", font=text_font, fill=(208, 229, 255))

    boxes = {
        'F1': (205, 90, 455, 390),
        'F2': (675, 90, 925, 390),
        'F3': (1145, 90, 1395, 390),
        'D1': (395, 460, 645, 760),
        'D2': (955, 460, 1205, 760),
        'G': (675, 560, 925, 860),
    }

    centers = {code: ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2) for code, box in boxes.items()}
    line_layer = Image.new('RGBA', size, (0, 0, 0, 0))
    line_draw = ImageDraw.Draw(line_layer)

    ordered_cards = [(code, overview.slots.get(code)) for code in LINEUP_SLOT_ORDER if overview.slots.get(code) is not None]
    for index, (code_a, card_a) in enumerate(ordered_cards):
        for code_b, card_b in ordered_cards[index + 1:]:
            if card_a is None or card_b is None:
                continue
            strength = _pair_strength(card_a, card_b)
            if strength <= 0:
                continue
            color = (120, 160, 200, 140)
            width = 4
            if strength == 1:
                color = (255, 214, 102, 170)
                width = 5
            elif strength == 2:
                color = (88, 255, 153, 190)
                width = 7
            elif strength >= 3:
                color = (120, 220, 255, 210)
                width = 9
            line_draw.line([centers[code_a], centers[code_b]], fill=color, width=width)
    image.alpha_composite(line_layer)

    for slot_code in LINEUP_SLOT_ORDER:
        box = boxes[slot_code]
        card = overview.slots.get(slot_code)
        slot_title = get_slot_info(slot_code).short_title
        if card is None:
            draw.rounded_rectangle(box, radius=24, fill=(10, 29, 55, 175), outline=(130, 180, 255, 120), width=3)
            draw.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 - 15), slot_title, font=_font(34), fill=(220, 235, 255), anchor='mm')
            draw.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 + 20), 'empty', font=_font(22), fill=(170, 200, 240), anchor='mm')
        else:
            _draw_card_tile(image, card, box, title=slot_title)

    bonus_title_y = 790
    draw.rounded_rectangle((40, bonus_title_y, 570, 870), radius=18, fill=(8, 20, 38, 205), outline=(110, 170, 255, 110), width=2)
    draw.text((60, bonus_title_y + 18), 'CHEMISTRY', font=_font(24), fill='white')
    if overview.chemistry_bonuses:
        y = bonus_title_y + 52
        for bonus in overview.chemistry_bonuses[:3]:
            line = f"{bonus.icon} {bonus.value}  {bonus.matched_cards}/{bonus.required_cards}  +{bonus.bonus_ovr}"
            draw.text((60, y), line, font=_font(18), fill=(206, 227, 255))
            y += 24
    else:
        draw.text((60, bonus_title_y + 54), 'No active chemistry yet', font=_font(18), fill=(206, 227, 255))

    cleanup_render_cache()
    output = RENDER_DIR / f'lineup_{user_id}_{time.time_ns()}.png'
    image.convert('RGB').save(output, quality=95)
    return output


def render_collection_image(cards_page: PlayerCardsPage, user_id: int) -> Path:
    size = (1600, 900)
    image = _load_background('collection_bg.png', size, '#0a1e3a')
    draw = ImageDraw.Draw(image)

    draw.text((60, 38), 'COLLECTION', font=_font(42), fill='white')
    draw.text((60, 86), f"Cards: {cards_page.total_count}   Page: {cards_page.page}/{cards_page.pages_count}", font=_font(24), fill=(208, 229, 255))

    filters: list[str] = []
    if cards_page.search:
        filters.append(f"search: {cards_page.search}")
    if cards_page.position:
        filters.append(f"pos: {cards_page.position}")
    if cards_page.rarity:
        filters.append(f"rarity: {cards_page.rarity}")
    if filters:
        draw.text((60, 122), ' · '.join(filters), font=_font(20), fill=(180, 214, 255))

    grid = [
        (70, 180, 325, 520),
        (370, 180, 625, 520),
        (670, 180, 925, 520),
        (970, 180, 1225, 520),
        (1270, 180, 1525, 520),
    ]

    for idx, box in enumerate(grid):
        if idx < len(cards_page.cards):
            _draw_card_tile(image, cards_page.cards[idx], box)
        else:
            draw.rounded_rectangle(box, radius=20, fill=(12, 23, 44, 150), outline=(130, 180, 255, 70), width=2)
            draw.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 - 8), 'EMPTY', font=_font(28), fill=(210, 225, 248), anchor='mm')
            draw.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 + 22), 'slot', font=_font(18), fill=(168, 195, 232), anchor='mm')

    footer = 'Open filters or search to rebuild the view automatically'
    draw.text((60, 845), footer, font=_font(18), fill=(180, 214, 255))

    cleanup_render_cache()
    output = RENDER_DIR / f'collection_{user_id}_{cards_page.page}_{time.time_ns()}.png'
    image.convert('RGB').save(output, quality=95)
    return output
