from aiogram.fsm.state import State, StatesGroup


class ChemistryCreateStates(StatesGroup):
    waiting_for_value = State()


class ChemistrySearchStates(StatesGroup):
    waiting_for_query = State()


class ChemistryEditStates(StatesGroup):
    waiting_for_value = State()
