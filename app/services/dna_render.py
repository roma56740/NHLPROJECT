from __future__ import annotations

import math
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.services.dna_crafting import DnaTargetCard
from app.services.renders import RENDER_DIR, _font, _load_card_visual


CANVAS = (1536, 864)


def _dna_background() -> Image.Image:
    w, h = CANVAS
    base = Image.new("RGBA", CANVAS, (3, 7, 13, 255))
    draw = ImageDraw.Draw(base, "RGBA")

    # cold x-ray / laboratory grid
    for x in range(0, w, 64):
        draw.line((x, 0, x, h), fill=(60, 190, 220, 10), width=1)
    for y in range(0, h, 64):
        draw.line((0, y, w, y), fill=(60, 190, 220, 8), width=1)

    glow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    gd.ellipse((w * 0.05, -h * 0.35, w * 0.75, h * 0.55), fill=(20, 180, 220, 52))
    gd.ellipse((w * 0.55, h * 0.35, w * 1.12, h * 1.15), fill=(205, 32, 55, 38))
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(95)))

    # subtle DNA double helix behind the cards
    helix = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    hd = ImageDraw.Draw(helix, "RGBA")
    cx = w // 2
    amp = 108
    y0, y1 = 100, h - 40
    pts_a = []
    pts_b = []
    for y in range(y0, y1 + 1, 8):
        phase = (y - y0) / 88.0
        x = cx + math.sin(phase) * amp
        pts_a.append((x, y))
        pts_b.append((cx - math.sin(phase) * amp, y))
    hd.line(pts_a, fill=(96, 220, 239, 55), width=5)
    hd.line(pts_b, fill=(232, 62, 78, 42), width=5)
    for i in range(0, min(len(pts_a), len(pts_b)), 9):
        hd.line((pts_a[i], pts_b[i]), fill=(220, 235, 245, 24), width=2)
    base.alpha_composite(helix.filter(ImageFilter.GaussianBlur(1.4)))
    return base


def render_dna_event_image(cards: list[DnaTargetCard]) -> Path:
    image = _dna_background()
    draw = ImageDraw.Draw(image, "RGBA")
    w, h = CANVAS

    draw.text((72, 50), "DNA", font=_font(72, bold=True), fill=(239, 248, 255, 255))
    draw.text((72, 132), "BREAK THE 99 OVR CEILING", font=_font(28, bold=True), fill=(109, 221, 239, 240))
    draw.rounded_rectangle((72, 180, 430, 188), radius=4, fill=(214, 44, 65, 230))
    draw.text((w - 72, 65), "FIRST 100 OVR CARDS", font=_font(34, bold=True), fill=(240, 245, 250, 245), anchor="ra")
    draw.text((w - 72, 112), "IN GAME HISTORY  •  NEXT GEN → DNA → 100", font=_font(22, bold=True), fill=(151, 180, 201, 235), anchor="ra")

    card_h = 430
    card_w = round(card_h * 914 / 1280)
    gap = 40
    total = card_w * 4 + gap * 3
    start_x = (w - total) // 2
    top = 230

    padded = list(cards[:4])
    while len(padded) < 4:
        padded.append(DnaTargetCard("DNA", 100, None, "DNA", "F", "DNA", "", "", False))

    for idx, card in enumerate(padded):
        x = start_x + idx * (card_w + gap)
        # shadow + card
        shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow, "RGBA")
        sd.rounded_rectangle((x + 10, top + 16, x + card_w + 10, top + card_h + 16), radius=22, fill=(0, 0, 0, 155))
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))

        visual = _load_card_visual(card, (card_w, card_h))
        image.alpha_composite(visual, dest=(x, top))

        label_y = top + card_h + 18
        status = "CRAFTABLE" if card.available else "UPLOAD CARD"
        status_fill = (76, 219, 224, 230) if card.available else (214, 62, 77, 230)
        draw.rounded_rectangle((x + 12, label_y, x + card_w - 12, label_y + 42), radius=12, fill=(7, 14, 23, 225), outline=status_fill, width=2)
        draw.text((x + card_w // 2, label_y + 21), f"{card.surname}  {card.overall}", font=_font(22, bold=True), fill=(245, 250, 255, 255), anchor="mm")
        draw.text((x + card_w // 2, label_y + 62), status, font=_font(14, bold=True), fill=status_fill, anchor="ma")

    footer = "99 OVR WAS THE LIMIT  •  DNA BREAKS IT  •  100 OVR"
    draw.text((w // 2, h - 35), footer, font=_font(21, bold=True), fill=(189, 210, 224, 245), anchor="ms")

    output = RENDER_DIR / f"dna_event_{time.time_ns()}.png"
    image.convert("RGB").save(output, quality=94)
    return output
