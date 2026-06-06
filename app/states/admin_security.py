from aiogram.fsm.state import State, StatesGroup


class AdminSecurityStates(StatesGroup):
    waiting_for_user_search = State()
    waiting_for_lock_reason = State()
