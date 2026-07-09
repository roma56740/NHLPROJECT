from aiogram.fsm.state import State, StatesGroup


class FreeCardStates(StatesGroup):
    collection = State()
    add_collection = State()
    remove_collection = State()
