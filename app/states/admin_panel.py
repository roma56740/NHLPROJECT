from aiogram.fsm.state import State, StatesGroup


class AdminPanelStates(StatesGroup):
    add_admin = State()
    remove_admin = State()
