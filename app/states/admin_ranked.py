from aiogram.fsm.state import State, StatesGroup


class RankedLeagueEditStates(StatesGroup):
    waiting_for_min_points = State()


class RankedCosmeticCreateStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_rarity = State()
    waiting_for_image = State()
    waiting_for_badge_text = State()


class RankedGrantStates(StatesGroup):
    waiting_for_telegram_id = State()


class RankedPackSlotStates(StatesGroup):
    waiting_for_currency_amount = State()
    waiting_for_xp_amount = State()
    waiting_for_card_id = State()


class RankedPassCreateStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_gold_price = State()
    waiting_for_platinum_price = State()
    waiting_for_upgrade_price = State()


class RankedPassRewardStates(StatesGroup):
    waiting_for_level = State()
    waiting_for_amount = State()
    waiting_for_title = State()
