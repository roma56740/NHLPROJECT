from aiogram.fsm.state import State, StatesGroup


class AdminSalaryStates(StatesGroup):
    waiting_for_collection_salary = State()
    waiting_for_zero_salary = State()
    waiting_for_ovr_range = State()
