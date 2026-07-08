from aiogram.fsm.state import State, StatesGroup


class AdminCardsStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_name = State()
    waiting_for_overall = State()
    waiting_for_team = State()
    waiting_for_country = State()
    waiting_for_salary = State()
    waiting_for_collection = State()
    waiting_for_search = State()
    waiting_for_edit_value = State()
    waiting_for_edit_image = State()
