from aiogram.fsm.state import State, StatesGroup


class ProfileSettingsStates(StatesGroup):
    waiting_for_nickname = State()
    waiting_for_team_name = State()
    waiting_for_team_country = State()
    waiting_for_team_logo = State()
