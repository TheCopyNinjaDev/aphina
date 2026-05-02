from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.database import AsyncSessionLocal
from app.services.user_service import get_user, get_today_consumed, get_today_logs
from bot.utils import format_today_progress

router = Router()


@router.message(Command("progress"))
@router.message(F.text == "📊 Прогресс")
async def show_progress(message: Message):
    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

        if not user or not user.is_authenticated:
            await message.answer("🔒 Сначала авторизуйся — /start")
            return
        if not user.profile_complete:
            await message.answer("⚙️ Сначала заполни профиль — /start")
            return

        consumed = await get_today_consumed(db, user.id)
        logs = await get_today_logs(db, user.id)

    text = format_today_progress(consumed, user.daily_calories, logs)
    await message.answer(text, parse_mode="HTML")
