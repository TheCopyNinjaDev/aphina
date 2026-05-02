import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from app.database import AsyncSessionLocal
from app.services.user_service import (
    get_user, add_food_log, confirm_food_log,
    get_today_consumed, check_milestones,
)
from app.services.ai_service import analyze_food_image, transcribe_voice
from bot.keyboards.keyboards import food_confirm_keyboard
from bot.utils import format_milestone_achievement, generate_and_send_recipe, detect_voice_intent

router = Router()

_auth_check_msg = "🔒 Сначала авторизуйся — /start"
_profile_check_msg = "⚙️ Сначала заполни профиль — /start"


@router.message(F.photo)
async def handle_food_photo(message: Message, bot: Bot):
    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

    if not user or not user.is_authenticated:
        await message.answer(_auth_check_msg)
        return
    if not user.profile_complete:
        await message.answer(_profile_check_msg)
        return

    status_msg = await message.answer("🔍 Анализирую фото...")

    try:
        # Get the largest photo
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, buf)
        image_bytes = buf.getvalue()

        async with AsyncSessionLocal() as db:
            consumed_today = await get_today_consumed(db, user.id)

        caption = message.caption or ""
        result = await analyze_food_image(
            image_bytes,
            daily_calories=user.daily_calories,
            consumed_today=consumed_today,
            portion_caption=caption,
        )

        if result["calories"] == 0:
            desc = result.get("description", "").strip()
            if desc:
                await status_msg.edit_text(
                    f"🤔 Не смог извлечь число калорий из ответа. Вот что сказал AI:\n\n"
                    f"{desc}\n\n"
                    f"Введи калории вручную (просто числом) или отправь другое фото.",
                    parse_mode=None,
                )
            else:
                await status_msg.edit_text(
                    "🤔 Не смог определить калорийность. Попробуй сфотографировать чётче."
                )
            return

        # Save as unconfirmed log
        async with AsyncSessionLocal() as db:
            log = await add_food_log(
                db,
                user_id=user.id,
                food_description=_extract_first_line(result["description"]),
                calories=result["calories"],
                photo_file_id=photo.file_id,
                confirmed=False,
            )

        remaining = user.daily_calories - consumed_today
        status_icon = "⚠️" if result["exceeds_budget"] else "✅"
        factor = result.get("portion_factor", 1.0)
        portion_note = f"\n🍽️ <i>Учтена порция: {round(factor * 100)}%</i>" if factor != 1.0 else ""

        text = (
            f"{status_icon} <b>Результат анализа:</b>\n\n"
            f"{result['description']}"
            f"{portion_note}\n\n"
            f"📊 Дневной бюджет: {consumed_today} + {result['calories']} = "
            f"<b>{consumed_today + result['calories']}</b> / {user.daily_calories} ккал"
        )

        await status_msg.delete()
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=food_confirm_keyboard(log.id),
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при анализе: {str(e)[:100]}")


@router.callback_query(F.data.startswith("food_confirm:"))
async def confirm_eating(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        log = await confirm_food_log(db, log_id)
        if not log:
            await callback.answer("❌ Запись не найдена")
            return

        user = await get_user(db, callback.from_user.id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        consumed_today = await get_today_consumed(db, user.id)
        milestones_achieved = await check_milestones(db, user)

    remaining = max(user.daily_calories - consumed_today, 0)
    percent = round(consumed_today / user.daily_calories * 100, 1) if user.daily_calories else 0

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ <b>Записано!</b> +{log.calories} ккал\n\n"
        f"🔥 Итого сегодня: <b>{consumed_today}</b> / {user.daily_calories} ккал ({percent}%)\n"
        f"✨ Осталось: <b>{remaining}</b> ккал",
        parse_mode="HTML",
    )

    for milestone in milestones_achieved:
        await callback.message.answer(
            format_milestone_achievement(milestone),
            parse_mode="HTML",
        )

    await callback.answer("Записано! ✅")


@router.callback_query(F.data.startswith("food_cancel:"))
async def cancel_eating(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, delete
        from app.models import FoodLog
        await db.execute(delete(FoodLog).where(FoodLog.id == log_id))
        await db.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("👍 Понял, не записываю.")
    await callback.answer()


@router.message(F.voice)
async def handle_voice_food(message: Message, bot: Bot):
    """
    Transcribe voice then route by intent:
      - recipe intent  → extract ingredients and generate recipe immediately
      - food log intent → ask user to send a photo for auto-analysis
      - unknown        → show transcription and let user choose
    """
    async with AsyncSessionLocal() as db:
        user = await get_user(db, message.from_user.id)

    if not user or not user.is_authenticated:
        await message.answer(_auth_check_msg)
        return
    if not user.profile_complete:
        await message.answer(_profile_check_msg)
        return

    status_msg = await message.answer("🎙️ Распознаю голосовое сообщение...")

    file = await bot.get_file(message.voice.file_id)
    buf = io.BytesIO()
    await bot.download_file(file.file_path, buf)
    audio_bytes = buf.getvalue()

    transcribed = await transcribe_voice(audio_bytes)
    if not transcribed:
        await status_msg.edit_text(
            "❌ Не удалось распознать голос. Попробуй написать или отправь фото еды."
        )
        return

    await status_msg.edit_text(
        f"✅ Распознано: <i>{transcribed}</i>",
        parse_mode="HTML",
    )

    intent, ingredients = detect_voice_intent(transcribed)

    if intent == "recipe":
        if len(ingredients) < 1:
            # Transcribed text itself might be a comma-separated list
            ingredients = [i.strip() for i in transcribed.replace(" и ", ",").split(",") if i.strip()]

        if len(ingredients) >= 2:
            await generate_and_send_recipe(message, user, ingredients)
        else:
            await message.answer(
                "🥕 Хочешь рецепт? Напиши продукты через запятую:\n"
                "<i>Например: огурцы, помидоры</i>",
                parse_mode="HTML",
            )

    elif intent == "food_log":
        await message.answer(
            "📸 Отправь фото блюда — я автоматически посчитаю калории и запишу!"
        )

    else:
        # Unknown intent — show options
        await message.answer(
            "Что делаем?\n\n"
            "📸 Отправь <b>фото</b> — запишу в трекер\n"
            "🍳 Нажми <b>Рецепт</b> — придумаю блюдо из продуктов",
            parse_mode="HTML",
        )


def _extract_first_line(text: str) -> str:
    for line in text.split("\n"):
        line = line.strip()
        if line and "блюдо" in line.lower():
            # Remove emoji and label prefix
            import re
            clean = re.sub(r"^[^\w]*[Бб]людо[:\s]*", "", line).strip()
            return clean[:100] if clean else line[:100]
    return text[:80].split("\n")[0]
