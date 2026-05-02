from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.database import AsyncSessionLocal
from app.models import FoodLog
from app.services.user_service import get_user, get_today_consumed, get_today_logs
from bot.keyboards.keyboards import food_log_manage_keyboard
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

    manage_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить запись", callback_data="manage_logs")]
    ]) if logs else None

    await message.answer(text, parse_mode="HTML", reply_markup=manage_btn)


@router.callback_query(F.data == "manage_logs")
async def manage_logs(callback: CallbackQuery):
    async with AsyncSessionLocal() as db:
        user = await get_user(db, callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        logs = await get_today_logs(db, user.id)

    if not logs:
        await callback.answer("Нет записей за сегодня")
        return

    await callback.message.answer(
        "Нажми на запись, чтобы удалить её:",
        reply_markup=food_log_manage_keyboard(logs),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_log:"))
async def delete_log(callback: CallbackQuery):
    payload = callback.data.split(":")[1]

    if payload == "close":
        await callback.message.delete()
        await callback.answer()
        return

    log_id = int(payload)

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, delete
        result = await db.execute(select(FoodLog).where(FoodLog.id == log_id))
        log = result.scalar_one_or_none()
        if not log:
            await callback.answer("Запись не найдена")
            return

        deleted_calories = log.calories
        deleted_desc = log.food_description[:30]
        await db.execute(delete(FoodLog).where(FoodLog.id == log_id))
        await db.commit()

        user = await get_user(db, callback.from_user.id)
        consumed = await get_today_consumed(db, user.id)
        logs = await get_today_logs(db, user.id)

    await callback.answer(f"Удалено: {deleted_desc} ({deleted_calories} ккал)")

    if logs:
        await callback.message.edit_reply_markup(reply_markup=food_log_manage_keyboard(logs))
    else:
        await callback.message.delete()
        await callback.message.answer("✅ Все записи удалены.")
        return

    # Send updated progress summary
    text = format_today_progress(consumed, user.daily_calories, logs)
    manage_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить запись", callback_data="manage_logs")]
    ])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=manage_btn)
