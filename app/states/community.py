from aiogram.fsm.state import State, StatesGroup


class CommunityStates(StatesGroup):
    search_players = State()
    trade_search_offer_card = State()
    trade_currency_amount = State()
    trade_search_wanted_card = State()
    clan_create_name = State()
    clan_create_description = State()
    clan_search = State()
    admin_clan_search = State()
