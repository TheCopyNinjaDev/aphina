import io

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.database import AsyncSessionLocal
from app.services.user_service import get_user
from app.services.ai_service import transcribe_voice
from bot.states import RecipeStates
from bot.utils import generate_and_send_recipe

router = Router()


@router.message(Command("recipe"))
@router.message(F.text == "🍳 Рецепт")
async def recipe_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

    if not user or not user.is_authenticated:
        await message.answer("🔒 Сначала авторизуйся — /start")
        return
    if not user.profile_complete:
        await message.answer("⚙️ Сначала заполни профиль — /start")
        return

    await message.answer(
        "🥕 Напиши или надиктуй что есть в холодильнике:\n\n"
        "<i>Например: курица, рис, помидоры, лук</i>",
        parse_mode="HTML",
    )
    await state.set_state(RecipeStates.waiting_for_ingredients)


@router.message(RecipeStates.waiting_for_ingredients, F.voice)
async def process_ingredients_voice(message: Message, state: FSMContext, bot: Bot):
    status_msg = await message.answer("🎙️ Распознаю голосовое сообщение...")

    file = await bot.get_file(message.voice.file_id)
    buf = io.BytesIO()
    await bot.download_file(file.file_path, buf)

    transcribed = await transcribe_voice(buf.getvalue())
    if not transcribed:
        await status_msg.edit_text(
            "❌ Не удалось распознать голос. Попробуй написать текстом или повтори."
        )
        return

    await status_msg.edit_text(f"✅ Распознано: <i>{transcribed}</i>", parse_mode="HTML")
    await _process_raw_ingredients(message, state, transcribed)


@router.message(RecipeStates.waiting_for_ingredients, F.text)
async def process_ingredients_text(message: Message, state: FSMContext):
    await _process_raw_ingredients(message, state, message.text)


async def _process_raw_ingredients(message: Message, state: FSMContext, raw: str):
    # Accept comma-separated or "и"-separated lists
    ingredients = [
        i.strip()
        for i in raw.replace(" и ", ",").replace(";", ",").split(",")
        if i.strip() and len(i.strip()) >= 2
    ]

    if len(ingredients) < 2:
        await message.answer(
            "⚠️ Укажи хотя бы 2 ингредиента через запятую:\n"
            "<i>огурцы, помидоры</i>\n\n"
            "Или надиктуй голосовым 🎙️",
            parse_mode="HTML",
        )
        return

    await state.clear()

    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

    await generate_and_send_recipe(message, user, ingredients)
