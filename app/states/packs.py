from aiogram.fsm.state import State, StatesGroup


class AdminPackStates(StatesGroup):
    search = State()
    waiting_for_image = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_cards_count = State()
    waiting_for_edit_image = State()
    waiting_for_edit_animation = State()
    waiting_for_edit_text = State()
    waiting_for_edit_price = State()
    waiting_for_edit_count = State()
    waiting_for_edit_odds = State()
    waiting_for_card_search = State()
