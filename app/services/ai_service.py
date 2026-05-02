"""
AI service — all requests via OpenRouter, routed through rotating proxies.
"""

import base64
import io
import logging
import re

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.proxy_manager import proxy_manager, _make_openai_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Food photo analysis
# ---------------------------------------------------------------------------

def parse_portion_factor(caption: str) -> float:
    """
    Parse a portion modifier from user caption.
    Returns a float multiplier (e.g. 0.5 for "половину", 1.0 if no modifier found).
    """
    if not caption:
        return 1.0
    t = caption.lower()

    # Explicit fractions / words
    _MAP = {
        "половин": 0.5, "полов": 0.5, "1/2": 0.5,
        "треть": 1/3, "1/3": 1/3,
        "четверт": 0.25, "1/4": 0.25,
        "три четверт": 0.75, "3/4": 0.75,
        "двух трет": 2/3, "2/3": 2/3,
    }
    for key, val in _MAP.items():
        if key in t:
            return val

    # Percentage: "80%", "70 %", "30 процентов"
    m = re.search(r"(\d+)\s*(?:%|процент)", t)
    if m:
        pct = int(m.group(1))
        if 1 <= pct <= 100:
            return pct / 100

    return 1.0


async def analyze_food_image(
    image_bytes: bytes,
    daily_calories: int,
    consumed_today: int,
    portion_caption: str = "",
) -> dict:
    remaining = daily_calories - consumed_today
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        f"Ты — нутрициолог-ассистент. Проанализируй фото еды и ответь СТРОГО в этом формате "
        f"(без лишних слов, только шаблон ниже):\n\n"
        f"🍽️ Блюдо: [название]\n"
        f"🔥 Калории: [число] ккал\n"
        f"📊 БЖУ: Белки [г]г | Жиры [г]г | Углеводы [г]г\n"
        f"📝 Описание: [1-2 предложения]\n\n"
        f"Дневной бюджет пользователя: {daily_calories} ккал, уже съедено: {consumed_today} ккал, "
        f"остаток: {remaining} ккал.\n"
        f"Если калории блюда превышают остаток — добавь в ответ:\n"
        f"⚠️ Рекомендации: [конкретные советы]\n\n"
        f"НЕ повторяй цифры бюджета в ответе. Только русский язык."
    )

    def _build_result(content: str) -> dict:
        calories = _extract_calories(content)
        factor = parse_portion_factor(portion_caption)
        if factor != 1.0 and calories > 0:
            calories = round(calories * factor)
        return {
            "description": content,
            "calories": calories,
            "portion_factor": factor,
            "exceeds_budget": calories > remaining,
            "remaining_after": remaining - calories,
        }

    def _make_call(model: str):
        async def _call(client: AsyncOpenAI) -> dict:
            response = await client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }],
                max_tokens=600,
            )
            content = response.choices[0].message.content or ""
            if _is_refusal(content):
                raise RuntimeError(f"Model refused to analyze image: {content[:80]}")
            return _build_result(content)
        return _call

    try:
        return await proxy_manager.call(_make_call(settings.VISION_MODEL))
    except RuntimeError as exc:
        if "refused" in str(exc) and settings.VISION_MODEL_FALLBACK != settings.VISION_MODEL:
            logger.warning(
                f"Primary vision model refused, falling back to {settings.VISION_MODEL_FALLBACK}"
            )
            return await proxy_manager.call(_make_call(settings.VISION_MODEL_FALLBACK))
        raise


# ---------------------------------------------------------------------------
# Recipe text generation
# ---------------------------------------------------------------------------

async def generate_recipe(ingredients: list[str], user_info: dict) -> dict:
    ingredients_str = ", ".join(ingredients)
    weight = user_info.get("weight", 70)
    target = user_info.get("target_weight", 65)
    goal = (
        "похудение" if target < weight
        else "набор массы" if target > weight
        else "поддержание веса"
    )

    prompt = (
        f"Ты — шеф-повар и нутрициолог.\n\n"
        f"СТРОГОЕ ПРАВИЛО: используй ТОЛЬКО эти продукты: {ingredients_str}\n"
        f"Дополнительно разрешены только: соль, перец, вода.\n"
        f"ЗАПРЕЩЕНО добавлять любые другие ингредиенты.\n\n"
        f"Цель: {goal} | Норма: {user_info.get('daily_calories', 2000)} ккал\n\n"
        f"Формат ответа:\n"
        f"🍳 Название: [название]\n"
        f"⏱️ Время приготовления: [минуты]\n"
        f"👥 Порций: [число]\n\n"
        f"📋 Ингредиенты:\n[только из списка выше с граммовкой]\n\n"
        f"👨‍🍳 Пошаговый рецепт:\n1. ...\n\n"
        f"🔥 Калорийность на порцию: [число] ккал\n"
        f"📊 БЖУ: Белки [г]г | Жиры [г]г | Углеводы [г]г\n\n"
        f"💚 Польза: [1-2 предложения]\n\n"
        f"💡 Совет шефа: [лайфхак]\n\n"
        f"Только русский язык."
    )

    async def _call(client: AsyncOpenAI) -> dict:
        response = await client.chat.completions.create(
            model=settings.TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )
        text = response.choices[0].message.content or ""
        return {
            "text": text,
            "dish_name": _extract_dish_name(text),
            "calories_per_serving": _extract_calories(text),
        }

    return await proxy_manager.call(_call)


# ---------------------------------------------------------------------------
# Recipe image — DALL-E 3 via OpenRouter
# ---------------------------------------------------------------------------

async def generate_recipe_image(dish_name: str, ingredients: list[str]) -> bytes | None:
    """
    Generate a recipe illustration using DALL-E 3 through OpenRouter.
    Uses raw httpx (not OpenAI SDK) because OpenRouter returns plain JSON,
    not an ImagesResponse object — the SDK fails to deserialize it.
    Returns raw image bytes or None on failure.
    """
    ingredients_str = ", ".join(ingredients[:6])

    image_prompt = (
        f"Цветной иллюстрированный мини-журнал в смешанной технике на 3 страницы. "
        f"Рецепт: {dish_name}. Ингредиенты: {ingredients_str}. "
        f"Включи пошаговые визуальные элементы приготовления, диаграммы и пояснения, "
        f"красивую подачу готового блюда, нарисованные ингредиенты. "
        f"Добавь раздел о пользе для здоровья и экологическом воздействии блюда. "
        f"Стиль: яркая акварель с элементами инфографики, разворот кулинарного журнала. "
        f"Декоративные элементы: травы, специи, кухонная утварь. Без текста на изображении."
    )

    _headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "HTTP-Referer": settings.APP_URL,
        "X-Title": settings.APP_NAME,
        "Content-Type": "application/json",
    }
    _payload = {
        "model": settings.IMAGE_MODEL,
        "prompt": image_prompt,
        "size": "1024x1024",
        "quality": "standard",
        "n": 1,
    }

    async def _call(http: httpx.AsyncClient) -> bytes:
        resp = await http.post(
            f"{settings.OPENROUTER_BASE_URL}/images/generations",
            headers=_headers,
            json=_payload,
        )
        resp.raise_for_status()
        data = resp.json()

        # OpenRouter returns {"data": [{"url": "..."}]}
        image_url = data["data"][0]["url"]
        logger.info(f"DALL-E image URL received, downloading: {image_url[:60]}...")

        img_resp = await http.get(image_url, timeout=30.0)
        img_resp.raise_for_status()
        return img_resp.content

    try:
        return await proxy_manager.call_http(_call)
    except Exception as e:
        logger.error(f"Image generation failed after all retries: {e}")
        return None


# ---------------------------------------------------------------------------
# Voice transcription — Gemini via OpenRouter (supports audio data-URL)
# ---------------------------------------------------------------------------

async def transcribe_voice(audio_bytes: bytes) -> str:
    """
    Transcribe a Telegram voice message (OGG/Opus).
    Uses Gemini Flash via OpenRouter — accepts audio as base64 data-URL.
    """
    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

    async def _call(client: AsyncOpenAI) -> str:
        response = await client.chat.completions.create(
            model=settings.TRANSCRIPTION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Транскрибируй это голосовое сообщение на русском языке. "
                            "Напиши только текст без пояснений и комментариев."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:audio/ogg;base64,{b64_audio}"},
                    },
                ],
            }],
            max_tokens=300,
        )
        return (response.choices[0].message.content or "").strip()

    try:
        return await proxy_manager.call(_call)
    except Exception as e:
        logger.error(f"Voice transcription failed after all retries: {e}")
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REFUSAL_PHRASES = (
    "i'm sorry, i can't",
    "i cannot",
    "i can't do that",
    "i can't help with that",
    "i can't assist with this",
    "i can't assist with that",
    "i'm unable to",
    "не могу анализировать",
    "не могу обработать",
    "не могу помочь",
    "извините, я не могу",
    "sorry, i can't",
    "unable to analyze",
    "unable to process",
)


def _is_refusal(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in _REFUSAL_PHRASES)


def _extract_calories(text: str) -> int:
    # Only search in the structured part — stop before any budget/context echoes
    # (lines that contain "бюджет", "норма", "съедено", "остаток", "осталось")
    lines = text.splitlines()
    analysis_lines = []
    for line in lines:
        ll = line.lower()
        if any(kw in ll for kw in ("бюджет", "норма", "съедено", "остаток", "осталось", "дневн")):
            break
        analysis_lines.append(line)
    search_text = "\n".join(analysis_lines) if analysis_lines else text

    patterns = [
        r"[Кк]алорийность[^\d]*(\d+)",
        r"[Кк]алори[ий][^\d]*(\d+)",
        r"(\d+)\s*[–—-]\s*\d+\s*ккал",   # ranges like "400-500 ккал" → take first
        r"(\d+)\s*ккал",
        r"[Cc]alories?[^\d]*(\d+)",
        r"(\d+)\s*cal(?:ories)?",
        r"🔥[^\d]*(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, search_text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 5000:
                return val
    return 0


def _extract_dish_name(text: str) -> str:
    m = re.search(r"[Нн]азвание[:\s]+(.+)", text)
    if m:
        return m.group(1).strip().rstrip(".")
    return "Блюдо"
