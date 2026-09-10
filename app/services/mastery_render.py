from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.services.mastery import MASTERY_MAX_POINTS, MASTERY_TIERS, MasteryProgress, reward_label
from app.services.renders import RENDER_DIR, _font, _load_card_visual, _transparent_white_background, resolve_asset_path
from app.services.xfactors import get_xfactor_by_code
from app.services.mastery import xfactor_code_for_tier

CANVAS = (1536, 864)


def _compact(value: int) -> str:
    if value >= 1_000_000:
        return f"{value/1_000_000:.0f}M"
    if value >= 1_000:
        if value < 10_000 and value % 1_000:
            return f"{value/1_000:.1f}K"
        return f"{value/1_000:.0f}K"
    return str(value)


def _short_reward(progress: MasteryProgress, tier) -> str:
    if tier.reward_type == "coins":
        return f"{_compact(tier.amount)} COINS"
    if tier.reward_type == "rank_point":
        return f"{tier.amount} RANK"
    if tier.reward_type == "combo":
        return "3M + 50 RANK"
    if tier.reward_type == "future":
        return "FUTURE"
    code = xfactor_code_for_tier(progress.player, tier)
    if code:
        xf = get_xfactor_by_code(code)
        return (xf.name if xf else code).upper()
    return "—"


def render_mastery_image(card, progress: MasteryProgress) -> Path:
    w, h = CANVAS
    image = Image.new("RGBA", CANVAS, (5, 8, 14, 255))
    bg = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(bg, "RGBA")
    for y in range(h):
        ratio = y / max(1, h - 1)
        bdraw.line((0, y, w, y), fill=(8 + int(7*ratio), 13 + int(10*ratio), 23 + int(15*ratio), 255))
    image.alpha_composite(bg)

    # subtle glow
    glow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    gd.ellipse((-250, -180, 760, 1040), fill=(176, 32, 38, 74))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))

    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((52, 38), "MASTERY", font=_font(24, bold=True), fill=(230, 70, 75, 255))
    draw.text((52, 75), progress.player.name.upper(), font=_font(44, bold=True), fill="white")
    draw.text((52, 132), f"{progress.points:,} / {MASTERY_MAX_POINTS:,}".replace(",", " "), font=_font(24, bold=True), fill=(203, 210, 224, 255))

    # progress bar
    bar=(52, 176, 520, 204)
    draw.rounded_rectangle(bar, radius=14, fill=(28, 34, 46, 255))
    fill_w=max(0, int((bar[2]-bar[0]) * progress.points / MASTERY_MAX_POINTS))
    if fill_w:
        draw.rounded_rectangle((bar[0],bar[1],bar[0]+fill_w,bar[3]), radius=14, fill=(218, 42, 49, 255))

    # Player card visual
    card_visual = _load_card_visual(card, (420, 588))
    shadow = Image.new("RGBA", (460, 628), (0,0,0,0))
    sd=ImageDraw.Draw(shadow,"RGBA")
    sd.rounded_rectangle((20,20,440,608), radius=26, fill=(0,0,0,155))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)), dest=(32,214))
    image.alpha_composite(card_visual, dest=(52,234))

    # tiers grid
    grid_x=545; grid_y=44; cols=5
    tile_w=184; tile_h=146; gap=8
    for index,tier in enumerate(MASTERY_TIERS):
        col=index%cols; row=index//cols
        x=grid_x+col*(tile_w+gap); y=grid_y+row*(tile_h+gap)
        claimed=tier.points in progress.claimed_points
        unlocked=progress.points>=tier.points and tier.reward_type!="future"
        future=tier.reward_type=="future"
        if claimed:
            fill=(24,72,48,235); outline=(86,222,142,210); marker="✓"
        elif unlocked:
            fill=(74,45,18,235); outline=(243,184,76,220); marker="!"
        elif future:
            fill=(29,31,39,230); outline=(92,98,112,170); marker="◇"
        else:
            fill=(18,23,33,230); outline=(55,64,78,190); marker="•"
        draw.rounded_rectangle((x,y,x+tile_w,y+tile_h),radius=16,fill=fill,outline=outline,width=2)
        draw.text((x+12,y+10),f"LV {index+1:02d}",font=_font(14,bold=True),fill=(174,184,201,255))
        draw.text((x+tile_w-12,y+8),marker,font=_font(20,bold=True),fill=outline,anchor="ra")
        draw.text((x+12,y+39),_compact(tier.points),font=_font(24,bold=True),fill="white")
        reward=_short_reward(progress,tier)
        # wrap into at most two short lines
        words=reward.split()
        lines=[]; current=""
        for word in words:
            trial=(current+" "+word).strip()
            if draw.textlength(trial,font=_font(13,bold=True)) <= tile_w-24:
                current=trial
            else:
                if current: lines.append(current)
                current=word
        if current: lines.append(current)
        for li,line in enumerate(lines[:2]):
            draw.text((x+12,y+86+li*20),line,font=_font(13,bold=True),fill=(220,224,232,255))

    # unique icon preview at bottom-left if available
    unique_code=progress.player.unique_xfactor
    unique=get_xfactor_by_code(unique_code)
    if unique:
        path=resolve_asset_path(unique.icon_path)
        if path:
            try:
                icon=_transparent_white_background(Image.open(path).convert("RGBA"))
                icon=ImageOps.contain(icon,(92,92),method=Image.Resampling.LANCZOS)
                image.alpha_composite(icon,dest=(408,722))
                draw.text((52,828),"1 000 000 — UNIQUE MASTERY X-FACTOR",font=_font(16,bold=True),fill=(228,79,82,255))
            except Exception:
                pass

    output=RENDER_DIR / f"mastery_{progress.player.player_key}_{getattr(card,'id','card')}_{time.time_ns()}.png"
    image.convert("RGB").save(output,quality=95)
    return output
