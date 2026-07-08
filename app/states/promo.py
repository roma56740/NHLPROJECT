from aiogram.fsm.state import State, StatesGroup


class PromoRedeemStates(StatesGroup):
    waiting_for_code = State()


class PromoCreateStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_coins = State()
    waiting_for_rubles = State()
    waiting_for_max = State()


class PromoEditStates(StatesGroup):
    waiting_for_value = State()
