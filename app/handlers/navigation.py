"""Переходы из единого фото-меню.

Главный экран больше не использует ReplyKeyboard. Каждая кнопка прикреплена к
сообщению с баннером. Перед передачей управления существующему разделу баннер
заменяется коротким текстовым сообщением, чтобы старые обработчики могли безопасно
использовать edit_text и не требовали массовой переделки всех игровых флоу.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.keyboards.main_menu import ADMIN_TARGET_CALLBACKS
from app.keyboards.reply import ADMIN_MAIN_TEXTS, USER_MAIN_TEXTS
from app.services.admin_permissions import get_permission_for_callback, has_admin_permission
from app.utils.messages import safe_delete_message
from app.utils.users import is_admin


router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "nav:auto_back")
async def universal_inline_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Универсальный выход из любого экрана, где не было собственной навигации."""
    from app.handlers.menu import show_home_callback

    await state.clear()
    await show_home_callback(callback)
    await callback.answer()


LEGACY_REPLY_TEXTS = USER_MAIN_TEXTS | ADMIN_MAIN_TEXTS | {
    "🏒 Играть",
    "🧩 Состав",
    "🃏 Карты",
    "🎁 Паки",
    "🏆 Ranked Mode",
    "🏰 THE STRONGHOLD",
    "⚔️ CLAN WAR 2.0",
    "🕶 Чёрный рынок",
    "🛒 Магазин",
    "🎨 Косметика",
    "👤 Профиль",
}


@router.message(F.text.in_(LEGACY_REPLY_TEXTS))
async def migrate_legacy_reply_keyboard(message: Message, state: FSMContext) -> None:
    """Одноразово переводит пользователей со старой нижней клавиатуры на фото-меню."""
    if message.from_user is None:
        return
    from app.handlers.menu import send_home_photo

    await state.clear()
    await safe_delete_message(message)
    await send_home_photo(message, message.from_user.id, remove_reply_keyboard=True)


def _copy_callback(callback: CallbackQuery, *, message: Message, data: str) -> CallbackQuery:
    update = {"message": message, "data": data}
    model_copy = getattr(callback, "model_copy", None)
    if callable(model_copy):
        return model_copy(update=update)
    # Совместимость с pydantic v1/старыми сборками aiogram.
    return callback.copy(update=update)


async def _handoff(callback: CallbackQuery, target_data: str) -> CallbackQuery | None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return None

    chat_id = message.chat.id
    await safe_delete_message(message)
    placeholder = await callback.bot.send_message(chat_id=chat_id, text="⏳ Открываю раздел…")
    return _copy_callback(callback, message=placeholder, data=target_data)


async def _fail_open(callback: CallbackQuery, error: Exception) -> None:
    logger.exception("Failed to open inline menu target %s", callback.data, exc_info=error)
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(
                "⚠️ Не удалось открыть раздел. Вернись в главное меню и попробуй снова.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")]]
                ),
            )
        except Exception:
            pass
    try:
        await callback.answer("Не удалось открыть раздел", show_alert=True)
    except Exception:
        pass


async def _open_profile(callback: CallbackQuery, state: FSMContext) -> None:
    from app.handlers.profile import build_profile_keyboard, build_profile_text, get_profile_for_callback

    await state.clear()
    profile = await get_profile_for_callback(callback)
    if profile is None:
        return
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(build_profile_text(profile), reply_markup=build_profile_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("menu:open:"))
async def open_inline_menu_target(callback: CallbackQuery, state: FSMContext) -> None:
    key = (callback.data or "").removeprefix("menu:open:")

    if key.startswith("admin_"):
        if not is_admin(callback.from_user.id):
            await callback.answer("Раздел доступен только администрации.", show_alert=True)
            return
        permission_target = ADMIN_TARGET_CALLBACKS.get(callback.data or "")
        permission = get_permission_for_callback(permission_target)
        if permission is not None and not has_admin_permission(callback.from_user.id, permission):
            await callback.answer("Нет доступа к этому разделу.", show_alert=True)
            return

    target_data_by_key = {
        "matches": "matches:main",
        "lineup": "lineup:main",
        "cards": "user_cards:main",
        "packs": "packs:main",
        "ranked": "ranked:main",
        "stronghold": "stg:main",
        "war2": "war2:main",
        "dna": "dna:main",
        "black_market": "bm:main",
        "shop": "shop:main",
        "cosmetics": "cosmetics:main",
        "quests": "quests:main",
        "hockey_pass": "hpass:main",
        "daily": "daily:main",
        "free_card": "free_card:user",
        "rating": "rating:main",
        "events": "events:user_list:1",
        "community": "community:main",
        "creators": "creator:intro",
        "profile": "profile:open",
        "admin_cards": "admin_cards:main",
        "admin_packs": "admin_packs:main",
        "admin_users": "admin_users:main",
        "admin_wallets": "admin_wallets:main",
        "admin_ranked": "admin_ranked:main",
        "admin_stronghold": "admin_stronghold:main",
        "admin_war2": "admin_war2:main",
        "admin_black_market": "bm_admin:main",
        "admin_cosmetics": "admin_cosmetics:main",
        "admin_maintenance": "admin_maintenance:main",
        "admin_match_locks": "admin_security:match_locks:1",
        "admin_panel": "admin_panel:main",
        "admin_pack_videos": "admin_packs:videos:1",
        "admin_render": "admin_render:main",
        "admin_starter_kit": "starter_kit:main",
        "admin_divisions": "admin_divisions:main",
        "admin_chemistry": "chemistry:main",
        "admin_stronghold_schedule": "admin_stronghold:schedule",
        "admin_ranked_bots": "admin_ranked:bot_diag",
        "admin_events": "admin_events:main",
        "admin_rating": "admin_rating:main",
        "admin_clans": "admin_clans:list:1",
        "admin_arenas": "admin_arenas:main",
        "admin_trades": "admin_trades:list:1",
        "admin_security": "admin_security:main",
        "admin_creators": "admin_creators:main",
        "admin_salaries": "admin_salaries:main",
        "admin_rewards": "admin_rewards:main",
        "admin_quests": "admin_quests:main",
        "admin_hockey_pass": "admin_hpass:main",
        "admin_daily": "admin_daily:main",
        "admin_promo": "admin_promo:main",
        "admin_free_card": "free_card:admin",
        "admin_settings": "admin_settings:main",
        "admin_seasons": "season:main",
        "admin_broadcast": "broadcast:main",
        "admin_bulk": "admin_bulk:hub",
    }
    target_data = target_data_by_key.get(key)
    if target_data is None:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    forwarded = await _handoff(callback, target_data)
    if forwarded is None:
        return

    try:
        if key == "matches":
            from app.handlers import matches
            await matches.matches_main(forwarded, state)
        elif key == "lineup":
            from app.handlers import lineup
            await lineup.lineup_main(forwarded, state)
        elif key == "cards":
            from app.handlers import user_cards
            await user_cards.user_cards_main(forwarded, state)
        elif key == "packs":
            from app.handlers import packs
            await packs.packs_main(forwarded, state)
        elif key == "ranked":
            from app.handlers import ranked
            await ranked.ranked_main(forwarded)
        elif key == "stronghold":
            from app.handlers import stronghold
            await stronghold.stronghold_main_callback(forwarded, state)
        elif key == "war2":
            from app.handlers import war2
            await war2.war2_main(forwarded)
        elif key == "dna":
            from app.handlers import dna_event
            await dna_event.dna_main(forwarded)
        elif key == "black_market":
            from app.handlers import black_market
            await black_market.black_market_main_callback(forwarded, state)
        elif key == "shop":
            from app.handlers import shop
            await shop.shop_main_callback(forwarded)
        elif key == "cosmetics":
            from app.handlers import cosmetics
            await cosmetics.cosmetics_main(forwarded, state)
        elif key == "quests":
            from app.handlers import quests
            await quests.quests_main(forwarded, state)
        elif key == "hockey_pass":
            from app.handlers import hockey_pass
            await hockey_pass.user_hpass_main(forwarded, state)
        elif key == "daily":
            from app.handlers import daily_login
            await daily_login.daily_main(forwarded, state)
        elif key == "free_card":
            from app.handlers import free_card
            await free_card.free_card_user_callback(forwarded, state)
        elif key == "rating":
            from app.handlers import rating
            await rating.rating_main(forwarded, state)
        elif key == "events":
            from app.handlers import events
            await events.user_events_list(forwarded)
        elif key == "community":
            from app.handlers import community
            await community.community_main(forwarded, state)
        elif key == "creators":
            from app.handlers import creators
            await creators.creator_intro(forwarded, state)
        elif key == "profile":
            await _open_profile(forwarded, state)
        elif key == "admin_cards":
            from app.handlers import admin_cards
            await admin_cards.admin_cards_main(forwarded, state)
        elif key == "admin_packs":
            from app.handlers import packs
            await packs.admin_packs_main(forwarded, state)
        elif key == "admin_users":
            from app.handlers import admin_users
            await admin_users.admin_users_main(forwarded, state)
        elif key == "admin_wallets":
            from app.handlers import admin_wallets
            await admin_wallets.admin_wallets_main(forwarded, state)
        elif key == "admin_ranked":
            from app.handlers import admin_ranked
            await admin_ranked.admin_ranked_main(forwarded)
        elif key == "admin_stronghold":
            from app.handlers import admin_stronghold
            await admin_stronghold.admin_stronghold_main(forwarded, state)
        elif key == "admin_war2":
            from app.handlers import admin_war2
            await admin_war2.admin_war2_main(forwarded)
        elif key == "admin_black_market":
            from app.handlers import admin_black_market
            await admin_black_market.admin_dashboard_callback(forwarded, state)
        elif key == "admin_cosmetics":
            from app.handlers import admin_ranked
            await admin_ranked.admin_global_cosmetics_main(forwarded)
        elif key == "admin_maintenance":
            from app.handlers import admin_maintenance
            await admin_maintenance.admin_maintenance_main(forwarded, state)
        elif key == "admin_match_locks":
            from app.handlers import admin_security
            await admin_security.admin_security_match_locks(forwarded, state)
        elif key == "admin_panel":
            from app.handlers import admin_panel
            await admin_panel.admin_panel_main_callback(forwarded, state)
        elif key == "admin_pack_videos":
            from app.handlers import packs
            await packs.admin_pack_videos_page(forwarded, state)
        elif key == "admin_render":
            from app.handlers import admin_render
            await admin_render.admin_render_main(forwarded, state)
        elif key == "admin_starter_kit":
            from app.handlers import starter_kit
            await starter_kit.starter_kit_main(forwarded, state)
        elif key == "admin_divisions":
            from app.handlers import admin_divisions
            await admin_divisions.admin_divisions_main(forwarded, state)
        elif key == "admin_chemistry":
            from app.handlers import admin_chemistry
            await admin_chemistry.chemistry_main(forwarded, state)
        elif key == "admin_stronghold_schedule":
            from app.handlers import admin_stronghold
            await admin_stronghold.admin_stronghold_schedule(forwarded, state)
        elif key == "admin_ranked_bots":
            from app.handlers import admin_ranked
            await admin_ranked.admin_ranked_bot_diagnostics(forwarded)
        elif key == "admin_events":
            from app.handlers import events
            await events.admin_events_main(forwarded, state)
        elif key == "admin_rating":
            from app.handlers import admin_rating
            await admin_rating.admin_rating_main(forwarded)
        elif key == "admin_clans":
            from app.handlers import community
            await community.admin_clans_list(forwarded, state)
        elif key == "admin_arenas":
            from app.handlers import admin_arenas
            await admin_arenas.admin_arenas_main(forwarded, state)
        elif key == "admin_trades":
            from app.handlers import community
            await community.admin_trades_list(forwarded, state)
        elif key == "admin_security":
            from app.handlers import admin_security
            await admin_security.admin_security_main(forwarded, state)
        elif key == "admin_creators":
            from app.handlers import creators
            await creators.admin_creators_main(forwarded, state)
        elif key == "admin_salaries":
            from app.handlers import admin_salaries
            await admin_salaries.salaries_main(forwarded, state)
        elif key == "admin_rewards":
            from app.handlers import admin_rewards
            await admin_rewards.admin_rewards_main(forwarded, state)
        elif key == "admin_quests":
            from app.handlers import quests
            await quests.admin_quests_main(forwarded, state)
        elif key == "admin_hockey_pass":
            from app.handlers import hockey_pass
            await hockey_pass.admin_hpass_main(forwarded, state)
        elif key == "admin_daily":
            from app.handlers import daily_login
            await daily_login.admin_daily_main(forwarded, state)
        elif key == "admin_promo":
            from app.handlers import promo
            await promo.admin_promo_main(forwarded, state)
        elif key == "admin_free_card":
            from app.handlers import free_card
            await free_card.free_card_admin_callback(forwarded, state)
        elif key == "admin_settings":
            from app.handlers import admin_settings
            await admin_settings.admin_settings_main(forwarded, state)
        elif key == "admin_seasons":
            from app.handlers import seasons
            await seasons.season_main(forwarded, state)
        elif key == "admin_broadcast":
            from app.handlers import broadcast
            await broadcast.broadcast_main(forwarded, state)
        elif key == "admin_bulk":
            from app.handlers import admin_bulk_upload
            await admin_bulk_upload.bulk_hub(forwarded, state)

        # Несколько старых экранов не закрывают callback-spinner при успешном
        # открытии. Для них отвечаем здесь; повторный answer в ошибочной ветке
        # безопасно игнорируется.
        if key in {
            "ranked",
            "war2",
            "admin_ranked",
            "admin_war2",
            "admin_cosmetics",
            "admin_ranked_bots",
        }:
            try:
                await forwarded.answer()
            except Exception:
                pass
    except Exception as error:
        await _fail_open(forwarded, error)
