import json
import base64
import httpx
from typing import Optional
import config

FOOD_ANALYSIS_PROMPT = """Ты — эксперт-диетолог. Проанализируй фото еды и верни JSON с информацией.

ВАЖНО: Отвечай ТОЛЬКО валидным JSON без markdown и пояснений.

Формат ответа:
{
    "description": "Краткое описание блюда на русском",
    "items": [
        {
            "name": "название продукта",
            "portion": "примерная порция (г или мл)",
            "calories": число,
            "protein": число,
            "carbs": число,
            "fat": число
        }
    ],
    "total": {
        "calories": общее число ккал,
        "protein": общий белок в граммах,
        "carbs": общие углеводы в граммах,
        "fat": общие жиры в граммах,
        "fiber": клетчатка в граммах
    },
    "meal_type": "breakfast" | "lunch" | "dinner" | "snack",
    "health_notes": "краткий комментарий о полезности блюда"
}

Оценивай порции реалистично по размеру на фото. Если не уверен — давай средние значения."""


async def analyze_food_image(image_data: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Анализирует фото еды через Z.AI Vision API

    Args:
        image_data: Бинарные данные изображения
        mime_type: MIME тип изображения

    Returns:
        Словарь с информацией о еде и калориях
    """
    base64_image = base64.b64encode(image_data).decode("utf-8")

    payload = {
        "model": config.ZAI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.3
    }

    headers = {
        "Authorization": f"Bearer {config.ZAI_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            config.ZAI_API_URL,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    # Извлекаем текст ответа
    content = result["choices"][0]["message"]["content"]

    # Парсим JSON из ответа
    try:
        # Убираем возможные markdown блоки
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        return json.loads(content)
    except json.JSONDecodeError:
        # Если не удалось распарсить, возвращаем базовую структуру
        return {
            "description": content[:200],
            "total": {
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
                "fiber": 0
            },
            "meal_type": "snack",
            "health_notes": "Не удалось точно определить состав",
            "raw_response": content
        }


async def estimate_activity_calories(activity: str, duration_minutes: int, weight_kg: float = 70) -> dict:
    """
    Оценивает сожжённые калории для активности
    """
    prompt = f"""Оцени сожжённые калории для активности.

Активность: {activity}
Длительность: {duration_minutes} минут
Вес человека: {weight_kg} кг

Ответь ТОЛЬКО JSON:
{{
    "activity_type": "название активности",
    "calories_burned": число ккал,
    "intensity": "low" | "medium" | "high",
    "notes": "краткий комментарий"
}}"""

    payload = {
        "model": config.ZAI_MODEL.replace("-Flash", ""),  # Используем не-vision модель
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.3
    }

    headers = {
        "Authorization": f"Bearer {config.ZAI_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            config.ZAI_API_URL,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    content = result["choices"][0]["message"]["content"]

    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content.strip())
    except:
        # Фолбэк на примерные расчёты
        met_values = {
            "ходьба": 3.5, "бег": 8.0, "плавание": 6.0,
            "велосипед": 5.0, "тренировка": 5.0, "йога": 2.5
        }
        activity_lower = activity.lower()
        met = 4.0  # default
        for key, value in met_values.items():
            if key in activity_lower:
                met = value
                break

        calories = int(met * weight_kg * (duration_minutes / 60))
        return {
            "activity_type": activity,
            "calories_burned": calories,
            "intensity": "medium",
            "notes": "Примерный расчёт"
        }


async def generate_meal_plan(
    calorie_goal: int,
    preferences: Optional[str] = None,
    restrictions: Optional[str] = None
) -> str:
    """
    Генерирует план питания на день
    """
    prompt = f"""Составь план питания на день.

Цель по калориям: {calorie_goal} ккал
Предпочтения: {preferences or 'нет особых'}
Ограничения: {restrictions or 'нет'}

Составь сбалансированный план с завтраком, обедом, ужином и перекусами.
Укажи примерные калории и БЖУ для каждого приёма пищи.
Пиши на русском языке, кратко и по делу."""

    payload = {
        "model": config.ZAI_MODEL.replace("-Flash", "").replace("V", ""),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.7
    }

    headers = {
        "Authorization": f"Bearer {config.ZAI_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            config.ZAI_API_URL,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    return result["choices"][0]["message"]["content"]
