from aiogram.fsm.state import State, StatesGroup


class FreeCardStates(StatesGroup):
    collection = State()
