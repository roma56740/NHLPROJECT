from aiogram.fsm.state import State, StatesGroup


class DailyEditStates(StatesGroup):
    waiting_for_coins = State()
    waiting_for_rubles = State()
