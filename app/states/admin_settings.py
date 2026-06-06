from aiogram.fsm.state import State, StatesGroup


class AdminSettingsStates(StatesGroup):
    waiting_for_value = State()
