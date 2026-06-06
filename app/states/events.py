from aiogram.fsm.state import State, StatesGroup


class EventAdminStates(StatesGroup):
    search = State()
    create_image = State()
    create_title = State()
    create_description = State()
    create_target_value = State()
    create_reward_amount = State()
    create_end_at = State()
    edit_text = State()
    edit_number = State()
    edit_end_at = State()
    edit_image = State()
    choose_pack_search = State()
    choose_card_search = State()
