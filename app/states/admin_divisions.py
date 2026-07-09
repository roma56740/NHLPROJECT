from aiogram.fsm.state import State, StatesGroup


class AdminDivisionsStates(StatesGroup):
    waiting_for_division_name = State()
    waiting_for_division_image = State()
    waiting_for_asset_image = State()
