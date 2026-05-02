from aiogram import Router, F
from aiogram.types import Message

from app.database import AsyncSessionLocal
from app.services.user_service import get_user
from bot.states import AuthStates

router = Router()


@router.message(F.text == "📸 Анализ фото")
async def analyze_hint(message: Message):
    await message.answer(
        "📸 Просто отправь мне фото блюда — я автоматически его проанализирую!\n\n"
        "<i>Совет: фотографируй так, чтобы вся еда была видна целиком.</i>",
        parse_mode="HTML",
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message):
    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

    if not user or not user.is_authenticated:
        await message.answer("🔒 Введи пароль для доступа: /start")
        return

    if not user.profile_complete:
        await message.answer("⚙️ Заполни профиль: /start")
        return

    await message.answer(
        "🤔 Не понимаю команду.\n\n"
        "Используй кнопки меню или:\n"
        "• Отправь 📸 <b>фото</b> еды для анализа\n"
        "• /progress — прогресс на сегодня\n"
        "• /recipe — рецепт из продуктов",
        parse_mode="HTML",
    )
