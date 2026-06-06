from aiogram.fsm.state import State, StatesGroup


class AdminUsersStates(StatesGroup):
    search = State()
    currency_amount = State()
    give_card_search = State()
    give_pack_search = State()
