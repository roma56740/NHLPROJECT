from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.mastery import MASTERY_TIERS, MasteryProgress, reward_label

REWARDS_PER_PAGE = 6


def build_mastery_main_keyboard(user_card_id: int, card_page: int = 1) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Награды мастерства", callback_data=f"mastery:rewards:{user_card_id}:1:{card_page}")],
        [InlineKeyboardButton(text="⬅️ К карточке", callback_data=f"user_cards:view:{user_card_id}:{card_page}")],
    ])


def build_mastery_rewards_keyboard(user_card_id: int, progress: MasteryProgress, page: int, card_page: int = 1) -> InlineKeyboardMarkup:
    total_pages=max(1,(len(MASTERY_TIERS)+REWARDS_PER_PAGE-1)//REWARDS_PER_PAGE)
    page=min(max(1,page),total_pages)
    start=(page-1)*REWARDS_PER_PAGE
    rows=[]
    for tier in MASTERY_TIERS[start:start+REWARDS_PER_PAGE]:
        claimed=tier.points in progress.claimed_points
        unlocked=progress.points>=tier.points
        if tier.reward_type == "future":
            text=f"🔒 {tier.points:,} · будущая награда".replace(","," ")
            rows.append([InlineKeyboardButton(text=text, callback_data="mastery:future")])
        elif claimed:
            text=f"✅ {tier.points:,} · {reward_label(progress.player,tier)}".replace(","," ")
            rows.append([InlineKeyboardButton(text=text, callback_data="mastery:claimed")])
        elif unlocked:
            text=f"🎁 Получить · {tier.points:,} · {reward_label(progress.player,tier)}".replace(","," ")
            rows.append([InlineKeyboardButton(text=text, callback_data=f"mastery:claim:{user_card_id}:{tier.points}:{page}:{card_page}")])
        else:
            text=f"🔒 {tier.points:,} · {reward_label(progress.player,tier)}".replace(","," ")
            rows.append([InlineKeyboardButton(text=text, callback_data="mastery:locked")])
    nav=[]
    if page>1: nav.append(InlineKeyboardButton(text="⬅️",callback_data=f"mastery:rewards:{user_card_id}:{page-1}:{card_page}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}",callback_data="mastery:page"))
    if page<total_pages: nav.append(InlineKeyboardButton(text="➡️",callback_data=f"mastery:rewards:{user_card_id}:{page+1}:{card_page}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="📈 Рендер мастерства",callback_data=f"mastery:open:{user_card_id}:{card_page}")])
    rows.append([InlineKeyboardButton(text="⬅️ К карточке",callback_data=f"user_cards:view:{user_card_id}:{card_page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
