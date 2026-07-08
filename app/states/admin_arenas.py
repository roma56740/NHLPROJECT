from aiogram.fsm.state import State, StatesGroup


class ArenaCreateStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_wins = State()
    waiting_for_income_amount = State()
    waiting_for_capture_amount = State()


class ArenaEditStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_wins = State()
    waiting_for_income_amount = State()
    waiting_for_capture_amount = State()
