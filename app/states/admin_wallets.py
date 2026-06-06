from aiogram.fsm.state import State, StatesGroup


class AdminWalletsStates(StatesGroup):
    search = State()
    amount = State()
