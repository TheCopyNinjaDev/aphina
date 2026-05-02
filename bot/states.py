from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    waiting_for_password = State()


class ProfileStates(StatesGroup):
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_weight = State()
    waiting_for_height = State()
    waiting_for_target_weight = State()
    waiting_for_activity = State()


class RecipeStates(StatesGroup):
    waiting_for_ingredients = State()


class FoodStates(StatesGroup):
    analyzing = State()
