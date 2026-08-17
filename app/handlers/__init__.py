from aiogram import Router

from app.handlers import navigation, cosmetics, admin_bulk_upload, admin_black_market, admin_cards, admin_divisions, admin_salaries, admin_chemistry, admin_maintenance, admin_panel, admin_ranked, admin_rating, admin_render, admin_rewards, admin_stronghold, admin_war2, admin_security, admin_settings, admin_users, admin_wallets, black_market, broadcast, community, bulk_cards, creators, creator_tournaments, daily_login, diagnostics, promo, ranked, seasons, events, dna_event, free_card, hockey_pass, lineup, matches, menu, packs, profile, quests, rating, shop, start, stronghold, subscription, starter_kit, user_cards, war2, admin_arenas, clan_seasons, clan_wars
from app.middlewares.banned import BannedPlayerMiddleware
from app.middlewares.admin_permissions import AdminPermissionMiddleware
from app.middlewares.last_active import LastActiveMiddleware
from app.middlewares.maintenance import MaintenanceModeMiddleware


def setup_routers() -> Router:
    router = Router()
    maintenance_middleware = MaintenanceModeMiddleware()
    banned_player_middleware = BannedPlayerMiddleware()
    admin_permission_middleware = AdminPermissionMiddleware()
    last_active_middleware = LastActiveMiddleware()

    # ГЛОБАЛЬНЫЙ ТЕХНИЧЕСКИЙ ПЕРЕРЫВ регистрируется ПЕРВЫМ — раньше банов,
    # прав администратора и last-active — чтобы обычные пользователи блокировались
    # до выполнения любого другого middleware/хендлера (ТЗ "GLOBAL MAINTENANCE
    # MIDDLEWARE": "ранний приоритет").
    router.message.middleware(maintenance_middleware)
    router.callback_query.middleware(maintenance_middleware)

    router.message.middleware(banned_player_middleware)
    router.callback_query.middleware(banned_player_middleware)
    router.message.middleware(admin_permission_middleware)
    router.callback_query.middleware(admin_permission_middleware)
    router.message.middleware(last_active_middleware)
    router.callback_query.middleware(last_active_middleware)

    router.include_router(start.router)
    router.include_router(subscription.router)
    router.include_router(navigation.router)
    router.include_router(cosmetics.router)
    router.include_router(admin_panel.router)
    router.include_router(admin_bulk_upload.router)
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
    router.include_router(admin_render.router)
    router.include_router(admin_maintenance.router)
    router.include_router(admin_chemistry.router)
    router.include_router(quests.router)
    router.include_router(events.router)
    router.include_router(dna_event.router)
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
    router.include_router(admin_stronghold.router)
    router.include_router(stronghold.router)
    router.include_router(admin_black_market.router)
    router.include_router(black_market.router)
    router.include_router(war2.router)
    router.include_router(admin_war2.router)
    router.include_router(ranked.router)
    router.include_router(admin_ranked.router)
    router.include_router(diagnostics.router)
    router.include_router(menu.router)

    # Keep the creator tournament text-capture router last.
    # Its StateFilter(None) handler checks persistent pending score input and
    # otherwise returns, but Aiogram still treats the message as handled.
    # Putting it last prevents it from swallowing reply-keyboard buttons such
    # as THE STRONGHOLD, Ranked Mode, WAR2, and Home.
    router.include_router(creator_tournaments.router)
    return router
