from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.user_service import get_or_create_user, get_user
from bot.states import AuthStates, ProfileStates
from bot.keyboards.keyboards import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as db:
        user = await get_or_create_user(
            db,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

    if user.is_authenticated and user.profile_complete:
        await message.answer(
            f"👋 С возвращением, <b>{message.from_user.first_name}</b>!\n\n"
            "Используй меню для трекинга питания.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    if user.is_authenticated and not user.profile_complete:
        await message.answer(
            "👋 Привет! Тебе ещё нужно заполнить профиль.\n\n"
            "Напиши свой возраст (в годах):",
            parse_mode="HTML",
        )
        await state.set_state(ProfileStates.waiting_for_age)
        return

    name = message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Привет, <b>{name}</b>!\n\n"
        "Я — <b>Aphina</b>, твой личный трекер калорий с AI.\n\n"
        "🔐 Для доступа введи пароль:",
        parse_mode="HTML",
    )
    await state.set_state(AuthStates.waiting_for_password)


@router.message(AuthStates.waiting_for_password)
async def check_password(message: Message, state: FSMContext):
    if message.text != settings.BOT_PASSWORD:
        await message.answer("❌ Неверный пароль. Попробуй ещё раз:")
        return

    async with AsyncSessionLocal() as db:
        user = await get_or_create_user(db, message.from_user.id)
        user.is_authenticated = True
        await db.commit()

    await state.clear()
    await message.answer(
        "✅ <b>Доступ получен!</b>\n\n"
        "Давай настроим твой профиль для точного расчёта калорий.\n\n"
        "📅 Сколько тебе лет?",
        parse_mode="HTML",
    )
    await state.set_state(ProfileStates.waiting_for_age)
