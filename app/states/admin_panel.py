from aiogram.fsm.state import State, StatesGroup


class AdminPanelStates(StatesGroup):
    add_admin = State()
    change_admin_role = State()
    remove_admin = State()
