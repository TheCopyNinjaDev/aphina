import re
import logging

from aiogram.types import Message, BufferedInputFile

from app.services.calorie_service import (
    ACTIVITY_LABELS,
    format_progress_bar,
    get_food_equivalents,
    estimate_weeks_to_goal,
)
from app.models import User, Milestone

logger = logging.getLogger(__name__)


def format_profile_summary(user: User) -> str:
    goal_word = "похудеть" if user.target_weight < user.weight else "набрать вес"
    diff = abs(user.weight - user.target_weight)
    weeks = estimate_weeks_to_goal(
        user.weight, user.target_weight,
        user.daily_calories, user.weight,
        user.height, user.age, user.gender, user.activity_level,
    )

    activity = ACTIVITY_LABELS.get(user.activity_level, user.activity_level)
    gender = "мужской" if user.gender == "male" else "женский"

    text = (
        f"✅ <b>Профиль настроен!</b>\n\n"
        f"👤 Пол: {gender}\n"
        f"🎂 Возраст: {user.age} лет\n"
        f"⚖️ Вес: {user.weight} кг → {user.target_weight} кг\n"
        f"📏 Рост: {user.height} см\n"
        f"🏃 Активность: {activity}\n\n"
        f"🎯 <b>Цель:</b> {goal_word} на {diff:.1f} кг\n"
        f"🔥 <b>Дневная норма:</b> {user.daily_calories} ккал\n"
    )
    if weeks > 0:
        text += f"📅 <b>Примерный срок:</b> {weeks} нед.\n"
    return text


def format_milestones(milestones: list[Milestone], current_weight: float, target_weight: float) -> str:
    if not milestones:
        return ""

    losing = target_weight < current_weight
    lines = ["\n🏆 <b>Твои милстоуны:</b>"]

    for i, m in enumerate(milestones, 1):
        if m.achieved:
            status = "✅"
        elif (losing and current_weight <= m.target_weight + 2) or (not losing and current_weight >= m.target_weight - 2):
            status = "🔜"
        else:
            status = "⬜"
        lines.append(f"  {status} {i}. {m.target_weight} кг")

    return "\n".join(lines)


def format_today_progress(consumed: int, total: int, logs: list) -> str:
    remaining = max(total - consumed, 0)
    percent = round(min(consumed / total * 100, 100), 1) if total else 0
    bar = format_progress_bar(consumed, total)
    color = "🟢" if percent < 70 else ("🟡" if percent < 90 else "🔴")

    text = (
        f"📊 <b>Прогресс на сегодня</b>\n\n"
        f"{color} {bar} {percent}%\n\n"
        f"🔥 Съедено: <b>{consumed}</b> / {total} ккал\n"
        f"✨ Осталось: <b>{remaining}</b> ккал\n\n"
    )

    if consumed > 0:
        text += f"📦 <b>{consumed} ккал — это примерно:</b>\n"
        text += get_food_equivalents(consumed) + "\n"

    if logs:
        text += f"\n📋 <b>Что съел сегодня:</b>\n"
        for log in logs:
            time_str = log.created_at.strftime("%H:%M")
            text += f"  • {time_str} — {log.food_description[:40]} ({log.calories} ккал)\n"

    if remaining == 0:
        text += "\n⚠️ <b>Дневная норма исчерпана!</b> Постарайся больше не есть сегодня 💪"
    elif remaining < 200:
        text += f"\n⚠️ Осталось совсем немного — {remaining} ккал. Будь аккуратен!"

    return text


def format_milestone_achievement(milestone: Milestone) -> str:
    return (
        f"🎉 <b>Поздравляю!</b>\n\n"
        f"Ты достиг(ла) отметки <b>{milestone.target_weight} кг</b>!\n"
        f"Это невероятный прогресс! Продолжай в том же духе! 💪🏆"
    )


# ---------------------------------------------------------------------------
# Shared recipe generation + sending (used by both recipe.py and food.py)
# ---------------------------------------------------------------------------

async def generate_and_send_recipe(message: Message, user: User, ingredients: list[str]) -> None:
    """Generate recipe text + illustration and send to user."""
    from app.services.ai_service import generate_recipe, generate_recipe_image

    user_info = {
        "weight": user.weight,
        "target_weight": user.target_weight,
        "daily_calories": user.daily_calories,
        "gender": user.gender,
        "age": user.age,
    }

    status_msg = await message.answer("👨‍🍳 Подбираю рецепт специально для тебя...")

    try:
        recipe = await generate_recipe(ingredients, user_info)
        await status_msg.edit_text("🎨 Рисую иллюстрацию рецепта...")

        image_bytes = await generate_recipe_image(recipe["dish_name"], ingredients)

        await status_msg.delete()

        if image_bytes:
            await message.answer_photo(
                photo=BufferedInputFile(image_bytes, filename="recipe.jpg"),
                caption=f"🍳 <b>{recipe['dish_name']}</b>",
                parse_mode="HTML",
            )
        else:
            logger.warning("Image generation returned None — sending recipe without photo")

        recipe_text = recipe["text"]
        for chunk in _split_text(recipe_text, 4000):
            await message.answer(chunk, parse_mode="HTML")

        if recipe["calories_per_serving"]:
            await message.answer(
                f"💡 Порция содержит примерно <b>{recipe['calories_per_serving']} ккал</b>.\n"
                "Когда поешь — отправь фото, и я запишу в трекер! 📸",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Recipe generation error: {e}")
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:120]}\nПопробуй ещё раз.")
        except Exception:
            await message.answer(f"❌ Ошибка при генерации рецепта: {str(e)[:120]}")


def _split_text(text: str, max_len: int) -> list[str]:
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


# ---------------------------------------------------------------------------
# Voice intent detection
# ---------------------------------------------------------------------------

_FOOD_LOG_WORDS = {
    "съел", "съела", "поел", "поела", "ел", "ела", "выпил", "выпила",
    "перекусил", "перекусила", "завтракал", "завтракала", "обедал", "обедала",
    "ужинал", "ужинала", "покушал", "покушала", "скушал", "скушала",
}

_RECIPE_PHRASES = [
    "у меня есть", "есть у меня", "в холодильнике", "из холодильника",
    "что приготовить", "что можно приготовить", "имеется", "имею",
    "есть:", "продукты:", "ингредиенты:",
    "есть ",  # "есть яйца, сыр" — starts with "есть " followed by food
]


def detect_voice_intent(text: str) -> tuple[str, list[str]]:
    """
    Detect intent from transcribed voice text.

    Returns:
        ("recipe", [ingredients])  — user wants a recipe from listed ingredients
        ("food_log", [])           — user describing food they ate
        ("unknown", [])            — unclear
    """
    text_lower = text.lower()

    # Explicit food log words → log intent
    words = set(re.findall(r"\b\w+\b", text_lower))
    if words & _FOOD_LOG_WORDS:
        return "food_log", []

    # Recipe phrases → recipe intent
    if any(phrase in text_lower for phrase in _RECIPE_PHRASES):
        ingredients = _extract_ingredients_from_speech(text)
        return "recipe", ingredients

    return "unknown", []


def _extract_ingredients_from_speech(text: str) -> list[str]:
    """Extract ingredient words from natural speech like 'у меня есть огурцы и помидоры'."""
    clean = text

    # Remove filler phrases that are never ingredients
    _FILLER = [
        r"у меня есть", r"есть у меня", r"в холодильнике", r"из холодильника",
        r"что приготовить", r"что можно приготовить", r"имеется",
        r"продукты\s*:", r"ингредиенты\s*:", r"у меня", r"\bесть\b", r"\bимею\b",
    ]
    for pattern in _FILLER:
        clean = re.sub(pattern, " ", clean, flags=re.IGNORECASE)

    # Split by comma, semicolon, "и", "а также", "плюс", "ещё"
    parts = re.split(r"[,;]|\bи\b|\bа также\b|\bплюс\b|\bещё\b|\bеще\b", clean, flags=re.IGNORECASE)

    _SKIP_WORDS = {"меня", "него", "нее", "них", "это", "то"}
    ingredients = []
    for part in parts:
        item = part.strip().strip(".").strip()
        words = set(item.lower().split())
        if len(item) >= 3 and not (words & _SKIP_WORDS) and not item.lower() in _SKIP_WORDS:
            ingredients.append(item)

    return ingredients
