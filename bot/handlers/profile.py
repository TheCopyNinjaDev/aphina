from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database import AsyncSessionLocal
from app.services.user_service import update_user_profile, get_user
from bot.states import ProfileStates
from bot.keyboards.keyboards import (
    gender_keyboard, activity_keyboard, main_menu_keyboard, profile_update_keyboard
)
from bot.utils import format_profile_summary, format_milestones

router = Router()


@router.message(ProfileStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if not 10 <= age <= 120:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи корректный возраст (число от 10 до 120):")
        return

    await state.update_data(age=age)
    await message.answer(
        "👤 Выбери пол:",
        reply_markup=gender_keyboard(),
    )
    await state.set_state(ProfileStates.waiting_for_gender)


@router.callback_query(ProfileStates.waiting_for_gender, F.data.startswith("gender:"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    await callback.message.edit_text(
        f"{'👨' if gender == 'male' else '👩'} Пол выбран!\n\n"
        "⚖️ Введи свой текущий вес (кг), например: <code>75</code>",
        parse_mode="HTML",
    )
    await state.set_state(ProfileStates.waiting_for_weight)


@router.message(ProfileStates.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.strip().replace(",", "."))
        if not 30 <= weight <= 300:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи корректный вес (число от 30 до 300 кг):")
        return

    await state.update_data(weight=weight)
    await message.answer(
        "📏 Введи свой рост (см), например: <code>175</code>",
        parse_mode="HTML",
    )
    await state.set_state(ProfileStates.waiting_for_height)


@router.message(ProfileStates.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.strip().replace(",", "."))
        if not 100 <= height <= 250:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи корректный рост (число от 100 до 250 см):")
        return

    await state.update_data(height=height)
    data = await state.get_data()
    current_weight = data["weight"]

    await message.answer(
        f"🎯 Введи желаемый вес (кг), например: <code>{current_weight - 5:.0f}</code>\n\n"
        f"Текущий вес: {current_weight} кг",
        parse_mode="HTML",
    )
    await state.set_state(ProfileStates.waiting_for_target_weight)


@router.message(ProfileStates.waiting_for_target_weight)
async def process_target_weight(message: Message, state: FSMContext):
    try:
        target = float(message.text.strip().replace(",", "."))
        if not 30 <= target <= 300:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи корректный желаемый вес:")
        return

    await state.update_data(target_weight=target)
    await message.answer(
        "🏃 Выбери уровень физической активности:",
        reply_markup=activity_keyboard(),
    )
    await state.set_state(ProfileStates.waiting_for_activity)


@router.callback_query(ProfileStates.waiting_for_activity, F.data.startswith("activity:"))
async def process_activity(callback: CallbackQuery, state: FSMContext):
    activity = callback.data.split(":")[1]
    await state.update_data(activity_level=activity)
    data = await state.get_data()

    await callback.message.edit_text("⏳ Считаю твою норму калорий...")

    async with AsyncSessionLocal() as db:
        user = await update_user_profile(
            db,
            telegram_id=callback.from_user.id,
            age=data["age"],
            gender=data["gender"],
            weight=data["weight"],
            height=data["height"],
            target_weight=data["target_weight"],
            activity_level=activity,
        )

        milestones_text = format_milestones(
            user.milestones,
            user.weight,
            user.target_weight,
        )

    summary = format_profile_summary(user) + milestones_text

    await callback.message.answer(
        summary,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    if len(user.milestones) > 0:
        await callback.message.answer(
            "🚀 Отлично! Теперь отправь мне фото своей еды — и я скажу, сколько в ней калорий!\n\n"
            "Или используй /progress чтобы увидеть прогресс на сегодня.",
            parse_mode="HTML",
        )

    await state.clear()


@router.message(F.text == "⚙️ Профиль")
async def show_profile(message: Message):
    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

    if not user or not user.profile_complete:
        await message.answer("Сначала заполни профиль командой /start")
        return

    milestones_text = format_milestones(user.milestones, user.weight, user.target_weight)
    text = format_profile_summary(user) + milestones_text

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=profile_update_keyboard(),
    )


@router.callback_query(F.data == "update_profile")
async def update_profile_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 Введи свой текущий возраст (лет):",
    )
    await state.set_state(ProfileStates.waiting_for_age)
    await callback.answer()
