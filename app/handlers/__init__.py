from aiogram import Router

from app.handlers import admin_cards, admin_chemistry, admin_panel, admin_rating, admin_security, admin_settings, admin_users, admin_wallets, broadcast, community, events, hockey_pass, lineup, matches, menu, packs, profile, quests, rating, shop, start, user_cards
from app.middlewares.banned import BannedPlayerMiddleware


def setup_routers() -> Router:
    router = Router()
    banned_player_middleware = BannedPlayerMiddleware()

    router.message.middleware(banned_player_middleware)
    router.callback_query.middleware(banned_player_middleware)

    router.include_router(start.router)
    router.include_router(admin_panel.router)
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
    router.include_router(packs.router)
    router.include_router(shop.router)
    router.include_router(community.router)
    router.include_router(broadcast.router)
    router.include_router(admin_users.router)
    router.include_router(admin_cards.router)
    router.include_router(menu.router)
    return router
