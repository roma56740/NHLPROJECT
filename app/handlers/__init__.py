from aiogram import Router

from app.handlers import admin_arenas, admin_cards, admin_divisions, admin_salaries, admin_chemistry, admin_panel, admin_rating, admin_rewards, clan_seasons, admin_security, admin_settings, admin_users, admin_wallets, broadcast, clan_wars, community, bulk_cards, creators, daily_login, promo, seasons, events, free_card, hockey_pass, lineup, matches, menu, packs, profile, quests, rating, shop, start, subscription, starter_kit, user_cards
from app.middlewares.banned import BannedPlayerMiddleware
from app.middlewares.admin_permissions import AdminPermissionMiddleware


def setup_routers() -> Router:
    router = Router()
    banned_player_middleware = BannedPlayerMiddleware()
    admin_permission_middleware = AdminPermissionMiddleware()

    router.message.middleware(banned_player_middleware)
    router.callback_query.middleware(banned_player_middleware)
    router.message.middleware(admin_permission_middleware)
    router.callback_query.middleware(admin_permission_middleware)

    router.include_router(start.router)
    router.include_router(subscription.router)
    router.include_router(admin_panel.router)
    router.include_router(admin_divisions.router)
    router.include_router(admin_salaries.router)
    router.include_router(admin_rewards.router)
    router.include_router(profile.router)
    router.include_router(user_cards.router)
    router.include_router(lineup.router)
    router.include_router(matches.router)
    router.include_router(rating.router)
    router.include_router(admin_rating.router)
    router.include_router(admin_wallets.router)
    router.include_router(admin_security.router)
    router.include_router(admin_settings.router)
    router.include_router(admin_chemistry.router)
    router.include_router(quests.router)
    router.include_router(events.router)
    router.include_router(hockey_pass.router)
    router.include_router(free_card.router)
    router.include_router(starter_kit.router)
    router.include_router(packs.router)
    router.include_router(shop.router)
    router.include_router(community.router)
    router.include_router(clan_wars.router)
    router.include_router(clan_seasons.router)
    router.include_router(admin_arenas.router)
    router.include_router(daily_login.router)
    router.include_router(promo.router)
    router.include_router(creators.router)
    router.include_router(seasons.router)
    router.include_router(bulk_cards.router)
    router.include_router(broadcast.router)
    router.include_router(admin_users.router)
    router.include_router(admin_cards.router)
    router.include_router(menu.router)
    return router
