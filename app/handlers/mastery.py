from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards.mastery import REWARDS_PER_PAGE, build_mastery_main_keyboard, build_mastery_rewards_keyboard
from app.services.cache_cleanup import remove_render_cache_file
from app.services.mastery import MASTERY_MAX_POINTS, MASTERY_TIERS, claim_mastery_reward, get_mastery_progress_for_user_card, reward_label
from app.services.mastery_render import render_mastery_image
from app.services.user_cards import get_player_card_profile
from app.services.users import get_player_profile_by_telegram_id
from app.utils.messages import safe_delete_callback_message

router=Router()


def _progress_text(progress) -> str:
    claimable=sum(1 for tier in MASTERY_TIERS if tier.reward_type!="future" and tier.points<=progress.points and tier.points not in progress.claimed_points)
    return (
        f"<b>🏆 Мастерство · {escape(progress.player.name)}</b>\n\n"
        f"Очки: <b>{progress.points:,} / {MASTERY_MAX_POINTS:,}</b>\n".replace(","," ")
        + f"За победу: <b>+50</b> · за поражение: <b>+10</b>\n"
        + f"Доступно наград: <b>{claimable}</b>\n\n"
        + "Очки общие для всех копий этого хоккеиста. Начисление идёт только в обычных матчах."
    )


@router.callback_query(F.data.startswith("mastery:open:"))
async def mastery_open(callback: CallbackQuery) -> None:
    parts=(callback.data or "").split(":")
    user_card_id=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
    card_page=int(parts[3]) if len(parts)>3 and parts[3].isdigit() else 1
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    card=await get_player_card_profile(user_card_id, telegram_id=callback.from_user.id)
    if profile is None or card is None:
        await callback.answer("Карточка не найдена",show_alert=True); return
    progress=get_mastery_progress_for_user_card(profile.id,user_card_id)
    if progress is None:
        await callback.answer("Для этого игрока мастерство пока недоступно",show_alert=True); return
    path=render_mastery_image(card,progress)
    message=callback.message
    if not isinstance(message,Message):
        await callback.answer(); return
    await safe_delete_callback_message(callback)
    try:
        await callback.bot.send_photo(message.chat.id,FSInputFile(path),caption=_progress_text(progress),reply_markup=build_mastery_main_keyboard(user_card_id,card_page))
    finally:
        remove_render_cache_file(path)
    await callback.answer()


@router.callback_query(F.data.startswith("mastery:rewards:"))
async def mastery_rewards(callback: CallbackQuery) -> None:
    parts=(callback.data or "").split(":")
    user_card_id=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
    page=int(parts[3]) if len(parts)>3 and parts[3].isdigit() else 1
    card_page=int(parts[4]) if len(parts)>4 and parts[4].isdigit() else 1
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await callback.answer("Открой игру через /start",show_alert=True); return
    progress=get_mastery_progress_for_user_card(profile.id,user_card_id)
    if progress is None:
        await callback.answer("Мастерство недоступно",show_alert=True); return
    total_pages=max(1,(len(MASTERY_TIERS)+REWARDS_PER_PAGE-1)//REWARDS_PER_PAGE)
    page=min(max(1,page),total_pages)
    start=(page-1)*REWARDS_PER_PAGE
    lines=[f"<b>🎁 Мастерство · {escape(progress.player.name)}</b>",f"Очки: <b>{progress.points:,}</b>".replace(","," "),""]
    for idx,tier in enumerate(MASTERY_TIERS[start:start+REWARDS_PER_PAGE],start=start+1):
        if tier.points in progress.claimed_points: status="✅"
        elif tier.reward_type=="future": status="◇"
        elif progress.points>=tier.points: status="🎁"
        else: status="🔒"
        lines.append(f"{status} <b>{idx}.</b> {tier.points:,} — {escape(reward_label(progress.player,tier))}".replace(","," "))
    message=callback.message
    if isinstance(message,Message):
        try:
            await message.edit_text("\n".join(lines),reply_markup=build_mastery_rewards_keyboard(user_card_id,progress,page,card_page))
        except Exception:
            await safe_delete_callback_message(callback)
            await callback.bot.send_message(message.chat.id,"\n".join(lines),reply_markup=build_mastery_rewards_keyboard(user_card_id,progress,page,card_page))
    await callback.answer()


@router.callback_query(F.data.startswith("mastery:claim:"))
async def mastery_claim(callback: CallbackQuery) -> None:
    parts=(callback.data or "").split(":")
    user_card_id=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
    tier_points=int(parts[3]) if len(parts)>3 and parts[3].isdigit() else 0
    page=int(parts[4]) if len(parts)>4 and parts[4].isdigit() else 1
    card_page=int(parts[5]) if len(parts)>5 and parts[5].isdigit() else 1
    profile=await get_player_profile_by_telegram_id(callback.from_user.id)
    progress=get_mastery_progress_for_user_card(profile.id,user_card_id) if profile else None
    if progress is None:
        await callback.answer("Мастерство недоступно",show_alert=True); return
    result=claim_mastery_reward(profile.id,progress.player.player_key,tier_points)
    await callback.answer(result.message,show_alert=not result.success)
    # refresh list
    callback.data=f"mastery:rewards:{user_card_id}:{page}:{card_page}"
    await mastery_rewards(callback)


@router.callback_query(F.data.in_({"mastery:future","mastery:claimed","mastery:locked","mastery:page"}))
async def mastery_passive(callback: CallbackQuery) -> None:
    messages={"mastery:future":"Награда появится в будущем.","mastery:claimed":"Уже получено.","mastery:locked":"Порог мастерства ещё не достигнут.","mastery:page":""}
    await callback.answer(messages.get(callback.data or "", ""),show_alert=(callback.data!="mastery:page"))
