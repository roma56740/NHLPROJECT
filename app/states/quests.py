from aiogram.fsm.state import State, StatesGroup


class QuestAdminStates(StatesGroup):
    search = State()
    create_title = State()
    create_description = State()
    create_target_value = State()
    create_bp_reward = State()
    create_coins_reward = State()
    edit_value = State()
