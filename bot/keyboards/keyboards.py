from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
        ]
    ])


def activity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛋️ Сидячий", callback_data="activity:sedentary")],
        [InlineKeyboardButton(text="🚶 Лёгкая (1-3 дня/нед)", callback_data="activity:light")],
        [InlineKeyboardButton(text="🏃 Умеренная (3-5 дней/нед)", callback_data="activity:moderate")],
        [InlineKeyboardButton(text="💪 Высокая (6-7 дней/нед)", callback_data="activity:active")],
        [InlineKeyboardButton(text="🔥 Очень высокая", callback_data="activity:very_active")],
    ])


def food_confirm_keyboard(log_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Я это съел(а)", callback_data=f"food_confirm:{log_id}"),
            InlineKeyboardButton(text="❌ Нет, не ел(а)", callback_data=f"food_cancel:{log_id}"),
        ]
    ])


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Прогресс"), KeyboardButton(text="📸 Анализ фото")],
            [KeyboardButton(text="🍳 Рецепт"), KeyboardButton(text="⚙️ Профиль")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def profile_update_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Обновить профиль", callback_data="update_profile")],
    ])
