from aiogram.fsm.state import State, StatesGroup


class HockeyPassAdminStates(StatesGroup):
    create_title = State()
    create_description = State()
    create_end_at = State()
    create_price_amount = State()
    edit_text = State()
    edit_price_amount = State()
    reward_level = State()
    reward_amount = State()
    reward_title = State()
    reward_edit_value = State()
    reward_search_pack = State()
    reward_search_card = State()
