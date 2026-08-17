from aiogram.fsm.state import State, StatesGroup


class War2CosmeticCreateStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_rarity = State()
    waiting_for_image = State()
    waiting_for_badge_text = State()


class War2GrantStates(StatesGroup):
    waiting_for_telegram_id = State()
