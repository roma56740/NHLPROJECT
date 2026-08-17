from aiogram.fsm.state import State, StatesGroup


class AdminRenderStates(StatesGroup):
    waiting_for_asset = State()
    waiting_for_text = State()
