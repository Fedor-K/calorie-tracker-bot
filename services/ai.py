"""
AI Coach Service
Использует Claude API с tool calling для интеллектуального трекинга здоровья
"""
import json
import base64
import httpx
import logging
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo

import config

logger = logging.getLogger(__name__)

# ============================================================================
# COACH TOOLS - инструменты для AI
# ============================================================================

COACH_TOOLS = [
    {
        "name": "log_food",
        "description": "Записать приём пищи. Используй когда пользователь говорит что съел.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Что съел (название блюда)"},
                "calories": {"type": "integer", "description": "Калории"},
                "protein": {"type": "number", "description": "Белки в граммах"},
                "carbs": {"type": "number", "description": "Углеводы в граммах"},
                "fat": {"type": "number", "description": "Жиры в граммах"},
                "fiber": {"type": "number", "description": "Клетчатка в граммах"},
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Тип приёма пищи"
                }
            },
            "required": ["description", "calories"]
        }
    },
    {
        "name": "log_water",
        "description": "Записать воду. Используй когда пользователь говорит что выпил воду/чай/кофе/напиток.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_ml": {"type": "integer", "description": "Количество в мл"}
            },
            "required": ["amount_ml"]
        }
    },
    {
        "name": "log_weight",
        "description": "Записать вес пользователя.",
        "input_schema": {
            "type": "object",
            "properties": {
                "weight_kg": {"type": "number", "description": "Вес в килограммах"}
            },
            "required": ["weight_kg"]
        }
    },
    {
        "name": "log_activity",
        "description": "Записать активность/тренировку.",
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_type": {"type": "string", "description": "Тип активности (бег, ходьба, тренировка и т.д.)"},
                "duration_minutes": {"type": "integer", "description": "Длительность в минутах"},
                "calories_burned": {"type": "integer", "description": "Сожжённые калории (если известно)"}
            },
            "required": ["activity_type", "duration_minutes"]
        }
    },
    {
        "name": "get_today_stats",
        "description": "Получить статистику за сегодня. Используй когда нужно узнать сколько съедено/выпито.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_weight_history",
        "description": "Получить историю веса за последние N дней.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Количество дней", "default": 7}
            }
        }
    },
    {
        "name": "remember_fact",
        "description": "Запомнить важный факт о пользователе (привычка, предпочтение, ограничение в питании, цель).",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["preference", "habit", "restriction", "goal", "fact"],
                    "description": "Категория: preference (предпочтение), habit (привычка), restriction (ограничение), goal (цель), fact (факт)"
                },
                "content": {"type": "string", "description": "Текст факта (например: 'не ест молочку', 'вегетарианец')"}
            },
            "required": ["category", "content"]
        }
    },
    {
        "name": "update_profile",
        "description": "Обновить профиль пользователя (имя, возраст, рост, вес, цель и т.д.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "description": "Имя пользователя"},
                "age": {"type": "integer", "description": "Возраст"},
                "gender": {"type": "string", "enum": ["male", "female"], "description": "Пол"},
                "height_cm": {"type": "integer", "description": "Рост в сантиметрах"},
                "current_weight_kg": {"type": "number", "description": "Текущий вес"},
                "target_weight_kg": {"type": "number", "description": "Целевой вес"},
                "calorie_goal": {"type": "integer", "description": "Цель по калориям"},
                "water_goal": {"type": "integer", "description": "Цель по воде в мл"},
                "goal": {
                    "type": "string",
                    "enum": ["lose", "gain", "maintain", "health"],
                    "description": "Цель: lose (похудеть), gain (набрать), maintain (поддерживать), health (здоровье)"
                }
            }
        }
    },
    {
        "name": "check_profile_complete",
        "description": "Проверить, заполнен ли профиль пользователя (есть ли рост/вес для расчётов)",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_today_activities",
        "description": "Получить список активностей за сегодня. Используй чтобы узнать что уже записано.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "update_daily_activity",
        "description": "Обновить или установить дневную активность (сожжённые калории). Используй когда пользователь хочет исправить калории активности или указывает что данные неверные.",
        "input_schema": {
            "type": "object",
            "properties": {
                "calories_burned": {"type": "integer", "description": "Правильное количество сожжённых калорий"},
                "activity_type": {"type": "string", "description": "Тип активности (ходьба, бег, тренировка)"},
                "reason": {"type": "string", "description": "Почему меняем (например: 'пользователь указал на ошибку')"}
            },
            "required": ["calories_burned"]
        }
    },
    {
        "name": "clear_today_activities",
        "description": "Удалить все активности за сегодня. Используй если пользователь говорит что данные неверные и нужно сбросить.",
        "input_schema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Подтверждение удаления"}
            },
            "required": ["confirm"]
        }
    },
    {
        "name": "list_today_food",
        "description": "Показать все записи еды за сегодня с номерами. Используй когда пользователь хочет посмотреть что записано или исправить.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "delete_food_entry",
        "description": "Удалить запись еды. Используй когда пользователь говорит удалить конкретную еду (по номеру или описанию).",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_number": {"type": "integer", "description": "Номер записи из списка (1, 2, 3...)"},
                "description_match": {"type": "string", "description": "Часть описания для поиска (например 'яичница' или 'мороженое')"}
            }
        }
    },
    {
        "name": "update_food_entry",
        "description": "Изменить запись еды. Используй когда пользователь хочет исправить калории или описание конкретной еды.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_number": {"type": "integer", "description": "Номер записи из списка"},
                "description_match": {"type": "string", "description": "Часть описания для поиска"},
                "new_description": {"type": "string", "description": "Новое описание"},
                "new_calories": {"type": "integer", "description": "Новые калории"},
                "new_protein": {"type": "number", "description": "Новый белок"},
                "new_carbs": {"type": "number", "description": "Новые углеводы"},
                "new_fat": {"type": "number", "description": "Новые жиры"}
            }
        }
    },
    {
        "name": "clear_today_food",
        "description": "Удалить ВСЕ записи еды за сегодня. Используй ТОЛЬКО если пользователь явно просит сбросить всё.",
        "input_schema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Подтверждение удаления"}
            },
            "required": ["confirm"]
        }
    },
    {
        "name": "list_today_water",
        "description": "Показать все записи воды за сегодня.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "clear_today_water",
        "description": "Удалить ВСЕ записи воды за сегодня. Используй если пользователь хочет сбросить воду.",
        "input_schema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Подтверждение удаления"}
            },
            "required": ["confirm"]
        }
    },
    {
        "name": "set_today_water",
        "description": "Установить конкретное количество воды за сегодня (сбросить и записать новое значение).",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_ml": {"type": "integer", "description": "Количество воды в мл"}
            },
            "required": ["amount_ml"]
        }
    }
]


# ============================================================================
# SYSTEM PROMPT для AI коуча
# ============================================================================

def get_system_prompt(user_context: dict, memories_text: str) -> str:
    """Генерирует системный промпт для AI коуча"""

    goal_text = {
        "lose": "похудение",
        "gain": "набор мышечной массы",
        "maintain": "поддержание веса",
        "health": "здоровый образ жизни"
    }.get(user_context.get("goal", "health"), "здоровье")

    # Формируем список еды за сегодня
    meals_today = user_context.get("meals_today", [])
    meals_text = "\n".join([f"  - {m}" for m in meals_today]) if meals_today else "  Ничего не записано"

    # Формируем список активностей за сегодня
    activities_today = user_context.get("activities_today", [])
    activities_text = "\n".join([f"  - {a}" for a in activities_today]) if activities_today else "  Ничего не записано"

    profile_complete = user_context.get("profile_complete", False)

    system = f"""Ты — персональный AI-коуч по здоровью и питанию.

ТВОЯ ФИЛОСОФИЯ (ОЧЕНЬ ВАЖНО!):
Цель — НЕ заставить человека силой воли сбросить вес, чтобы потом набрать обратно.
Цель — бережно помочь выработать правильные привычки, чтобы вес ушёл НАВСЕГДА.

Принципы:
- Маленькие шаги > резкие перемены
- Замена привычек > запреты (греческий йогурт вместо сметаны, а не "нельзя сметану")
- Понимание "почему" > слепое следование правилам
- Гибкость > жёсткие диеты (съел пиццу — не трагедия, завтра продолжим)
- Долгосрочное мышление > быстрые результаты

ТВОИ ВОЗМОЖНОСТИ:
- Записывать еду, воду, вес, активность через инструменты
- Отвечать на вопросы о питании и здоровье
- Запоминать предпочтения и ограничения пользователя
- Предлагать ЗОЖ-альтернативы вместо запретов

ПРАВИЛА ОБЩЕНИЯ:
1. Пиши кратко и по делу (2-4 предложения обычно достаточно)
2. Используй эмодзи умеренно
3. Будь поддерживающим, не осуждай за "срывы" — это часть пути
4. Предлагай альтернативы, а не запрещай (вместо "не ешь сладкое" → "попробуй тёмный шоколад или фрукты")
5. Учитывай контекст: что уже съедено, память о пользователе
6. Если пользователь сообщает о еде — ВСЕГДА используй инструмент log_food
7. Если пользователь говорит о воде/напитке — используй log_water
8. Если узнаёшь новый факт о пользователе (ограничение, предпочтение) — используй remember_fact
9. Хвали за хорошие выборы, мягко предлагай улучшения для не очень хороших
10. Отвечай на русском языке

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:
- Имя: {user_context.get('name', 'Пользователь')}
- Страна: {user_context.get('country', 'Россия')}
- Возраст: {user_context.get('age') or '?'} лет
- Пол: {'мужской' if user_context.get('gender') == 'male' else 'женский' if user_context.get('gender') == 'female' else '?'}
- Рост: {user_context.get('height') or '?'} см
- Текущий вес: {user_context.get('weight') or '?'} кг
- Целевой вес: {user_context.get('target_weight') or '?'} кг
- Цель: {goal_text}
- Профиль заполнен: {'да' if profile_complete else 'нет (нужно собрать данные)'}

ДНЕВНЫЕ ЦЕЛИ:
- Калории: {user_context.get('calorie_goal', 2000)} ккал
- Вода: {user_context.get('water_goal', 2000)} мл
- Белок: {user_context.get('protein_goal', 100)} г

СЕГОДНЯ:
- Съедено калорий: {user_context.get('calories_today') or 0} ккал
- Сожжено калорий: {user_context.get('calories_burned_today') or 0} ккал
- Нетто калорий: {(user_context.get('calories_today') or 0) - (user_context.get('calories_burned_today') or 0)} ккал
- Выпито воды: {user_context.get('water_today', 0)} мл
- Белка: {user_context.get('protein_today', 0)} г
- Что ел:
{meals_text}
- Активности:
{activities_text}

ВАЖНО ПРО АКТИВНОСТИ:
- Если пользователь спрашивает почему калории не так или хочет исправить — используй update_daily_activity
- Не создавай новые записи активности если уже есть запись за сегодня — обновляй существующую
- Фото часов обновляет дневную активность автоматически
"""

    if memories_text:
        system += f"""
ПАМЯТЬ О ПОЛЬЗОВАТЕЛЕ:
{memories_text}
"""

    if not profile_complete:
        system += """
ВАЖНО: Профиль пользователя не заполнен. В начале разговора постарайся естественно узнать:
- Имя (если не знаешь)
- Рост и вес (для расчёта калорий)
- Цель (похудеть/набрать/поддерживать)
Не спрашивай всё сразу, веди естественный диалог.
"""

    return system


# ============================================================================
# Главная функция обработки сообщений
# ============================================================================

async def process_message(
    user_id: int,
    message: str,
    user_context: dict,
    memories_text: str = "",
    conversation: list[dict] = None
) -> dict:
    """
    Обработать сообщение пользователя через AI с инструментами

    Args:
        user_id: ID пользователя
        message: Текст сообщения
        user_context: Контекст пользователя (профиль, статистика)
        memories_text: Текст с памятью о пользователе
        conversation: История диалога [{"role": "user/assistant", "content": "..."}]

    Returns:
        {
            "response": "текст ответа пользователю",
            "tool_calls": [{"name": "...", "input": {...}, "result": {...}}, ...]
        }
    """
    if conversation is None:
        conversation = []

    system_prompt = get_system_prompt(user_context, memories_text)

    # Формируем сообщения для API
    messages = conversation.copy()
    messages.append({"role": "user", "content": message})

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": messages,
        "tools": COACH_TOOLS
    }

    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    tool_calls = []
    final_response = ""

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Первый вызов API
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers
        )
        if response.status_code != 200:
            error_text = response.text
            logger.error(f"[AI] API Error {response.status_code}: {error_text}")
            raise Exception(f"API Error: {error_text}")
        result = response.json()

        # Обрабатываем ответ и возможные tool_use
        while True:
            stop_reason = result.get("stop_reason")
            content_blocks = result.get("content", [])

            # Собираем текстовые блоки
            text_parts = []
            tool_use_blocks = []

            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_use_blocks.append(block)

            # Если есть текст — добавляем к ответу
            if text_parts:
                final_response += "".join(text_parts)

            # Если нет tool_use — выходим
            if stop_reason != "tool_use" or not tool_use_blocks:
                break

            # Обрабатываем tool_use
            tool_results = []
            for tool_block in tool_use_blocks:
                tool_name = tool_block.get("name")
                tool_id = tool_block.get("id")
                tool_input = tool_block.get("input", {})

                logger.info(f"[AI] Tool call: {tool_name} | input: {tool_input}")

                # Выполняем инструмент (фактическое выполнение будет в coach.py)
                # Здесь только сохраняем информацию о вызове
                tool_calls.append({
                    "name": tool_name,
                    "input": tool_input,
                    "id": tool_id
                })

                # Формируем результат для Claude (будет заполнен в coach.py)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"status": "pending"})
                })

            # Если есть tool calls — выходим из цикла, результаты обработает coach.py
            break

    return {
        "response": final_response.strip(),
        "tool_calls": tool_calls
    }


async def process_message_with_tool_results(
    user_id: int,
    original_message: str,
    user_context: dict,
    memories_text: str,
    conversation: list[dict],
    assistant_content: list[dict],
    tool_results: list[dict]
) -> str:
    """
    Продолжить обработку после выполнения инструментов

    Args:
        assistant_content: Контент от ассистента (включая tool_use блоки)
        tool_results: Результаты выполнения инструментов

    Returns:
        Финальный текстовый ответ
    """
    system_prompt = get_system_prompt(user_context, memories_text)

    # Формируем сообщения с результатами инструментов
    messages = conversation.copy()
    messages.append({"role": "user", "content": original_message})
    messages.append({"role": "assistant", "content": assistant_content})
    messages.append({"role": "user", "content": tool_results})

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": messages,
        "tools": COACH_TOOLS
    }

    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    # Собираем текстовый ответ
    content_blocks = result.get("content", [])
    text_parts = []

    for block in content_blocks:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    return "".join(text_parts).strip()


# ============================================================================
# Анализ фото (еда или фитнес-трекер)
# ============================================================================

PHOTO_ANALYSIS_PROMPT = """Проанализируй фото. Это может быть ЕДА или СКРИНШОТ ФИТНЕС-ТРЕКЕРА (Apple Watch, Mi Band, Samsung Health и т.д.)

ВАЖНО: Отвечай ТОЛЬКО валидным JSON без markdown.

СНАЧАЛА определи тип фото и верни соответствующий JSON:

===== ЕСЛИ ЭТО ЕДА =====
{
    "type": "food",
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
    "health_notes": "краткий комментарий о полезности блюда",
    "health_score": число от 1 до 10,
    "healthy_alternatives": ["альтернатива 1", "альтернатива 2"]
}

===== ЕСЛИ ЭТО ФИТНЕС-ТРЕКЕР / УМНЫЕ ЧАСЫ =====
{
    "type": "fitness",
    "device": "Apple Watch" | "Mi Band" | "Samsung" | "Garmin" | "другое",
    "activity_data": {
        "steps": число шагов (если видно),
        "calories_burned": сожжённые калории (если видно),
        "active_minutes": минуты активности (если видно),
        "distance_km": дистанция в км (если видно),
        "heart_rate": пульс (если видно),
        "floors": этажи (если видно),
        "workout_type": "тип тренировки если видно (бег, ходьба и т.д.)",
        "workout_duration_min": длительность тренировки в минутах (если видно)
    },
    "summary": "Краткое описание что видно на экране"
}

===== ЕСЛИ ЭТО ЧТО-ТО ДРУГОЕ =====
{
    "type": "other",
    "description": "Описание что на фото"
}

ВАЖНО:
- Для еды: если health_score < 6, предложи ЗОЖ-альтернативы
- Для фитнеса: извлеки ВСЕ числовые данные что видишь на экране
- Числа пиши без единиц измерения (просто числа)
- Для еды: оценивай порции реалистично по размеру на фото"""


ALBUM_ANALYSIS_PROMPT = """Ты получил НЕСКОЛЬКО фото (альбом). Это один приём пищи из нескольких блюд/продуктов.

КРИТИЧЕСКИ ВАЖНО:
- Тебе отправлено {photo_count} фото
- Ты ОБЯЗАН создать МИНИМУМ {photo_count} элементов в items (по одному на каждое фото)
- Каждое фото = ОТДЕЛЬНЫЙ item, даже если блюда похожи
- НЕ объединяй фото в один item

Отвечай ТОЛЬКО валидным JSON без markdown:

{{
    "type": "food",
    "description": "Общее название (например: Обед: суп, салат и хлеб)",
    "items": [
        {{
            "photo_number": 1,
            "name": "название с фото 1",
            "portion": "порция",
            "calories": число,
            "protein": число,
            "carbs": число,
            "fat": число
        }},
        {{
            "photo_number": 2,
            "name": "название с фото 2",
            "portion": "порция",
            "calories": число,
            "protein": число,
            "carbs": число,
            "fat": число
        }}
    ],
    "total": {{
        "calories": СУММА,
        "protein": СУММА,
        "carbs": СУММА,
        "fat": СУММА,
        "fiber": СУММА
    }},
    "meal_type": "breakfast" | "lunch" | "dinner" | "snack",
    "health_notes": "комментарий",
    "health_score": 1-10
}}

ПОМНИ: items должен содержать РОВНО {photo_count} элементов!"""


async def analyze_food_images_batch(images_data: list[tuple[bytes, str]]) -> dict:
    """
    Анализирует НЕСКОЛЬКО фото как один приём пищи (альбом)

    Args:
        images_data: Список кортежей (image_bytes, mime_type)

    Returns:
        Объединённый анализ всех фото
    """
    if len(images_data) == 1:
        # Одно фото - используем обычный анализ
        return await analyze_food_image(images_data[0][0], images_data[0][1])

    photo_count = len(images_data)
    logger.info(f"[AI] Analyzing album with {photo_count} photos")

    # Формируем контент с несколькими изображениями
    content = []
    for i, (image_bytes, mime_type) in enumerate(images_data, 1):
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        content.append({
            "type": "text",
            "text": f"--- ФОТО {i} из {photo_count} ---"
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64_image
            }
        })

    # Форматируем промпт с количеством фото
    prompt_text = ALBUM_ANALYSIS_PROMPT.format(photo_count=photo_count)
    content.append({
        "type": "text",
        "text": prompt_text
    })

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": content}]
    }

    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    content_text = result["content"][0]["text"]

    try:
        content_text = content_text.strip()
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.startswith("```"):
            content_text = content_text[3:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]
        content_text = content_text.strip()

        result = json.loads(content_text)
        items_count = len(result.get("items", []))
        logger.info(f"[AI] Album result: {items_count} items from {photo_count} photos")

        # Если AI вернул меньше items чем фото - логируем предупреждение
        if items_count < photo_count:
            logger.warning(f"[AI] Fewer items ({items_count}) than photos ({photo_count})!")

        return result
    except json.JSONDecodeError:
        logger.error(f"[AI] Failed to parse album response: {content_text[:200]}")
        return {
            "type": "food",
            "description": f"Приём пищи ({photo_count} фото)",
            "total": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0},
            "meal_type": "snack",
            "health_notes": "Не удалось точно определить состав",
            "raw_response": content_text
        }


async def analyze_food_image(image_data: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Анализирует фото через Claude Vision API
    Может распознавать еду И фитнес-трекеры

    Args:
        image_data: Бинарные данные изображения
        mime_type: MIME тип изображения

    Returns:
        Словарь с информацией (type: food/fitness/other)
    """
    base64_image = base64.b64encode(image_data).decode("utf-8")

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": base64_image
                        }
                    },
                    {
                        "type": "text",
                        "text": PHOTO_ANALYSIS_PROMPT
                    }
                ]
            }
        ]
    }

    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    content = result["content"][0]["text"]

    try:
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


async def correct_food_analysis(original_data: dict, correction_text: str) -> dict:
    """
    Корректирует анализ еды на основе уточнения пользователя

    Args:
        original_data: Оригинальные данные анализа
        correction_text: Текст уточнения от пользователя

    Returns:
        Скорректированный словарь с информацией о еде
    """
    prompt = f"""Пользователь отправил фото еды, я его проанализировал.
Теперь пользователь даёт уточнение. Скорректируй данные.

ОРИГИНАЛЬНЫЙ АНАЛИЗ:
{json.dumps(original_data, ensure_ascii=False, indent=2)}

УТОЧНЕНИЕ ПОЛЬЗОВАТЕЛЯ: {correction_text}

Верни ОБНОВЛЁННЫЙ JSON с учётом уточнения. Формат такой же:
{{
    "type": "food",
    "description": "обновлённое описание",
    "total": {{
        "calories": число,
        "protein": число,
        "carbs": число,
        "fat": число,
        "fiber": число
    }},
    "meal_type": "breakfast/lunch/dinner/snack",
    "health_notes": "обновлённый комментарий"
}}

ВАЖНО:
- Если пользователь говорит что чего-то нет (например "без сметаны") - убери это из расчёта
- Если пользователь уточняет напиток - добавь его калории
- Пересчитай КБЖУ с учётом изменений
- Сохрани остальные данные из оригинала если они не затронуты

Ответь ТОЛЬКО JSON, без markdown."""

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}]
    }

    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    content = result["content"][0]["text"]

    try:
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        corrected = json.loads(content)
        # Сохраняем тип
        corrected["type"] = "food"
        return corrected

    except json.JSONDecodeError:
        logger.error(f"[AI] Failed to parse corrected food: {content[:200]}")
        # Возвращаем оригинал если не удалось распарсить
        return original_data


# ============================================================================
# Вспомогательные функции для Z.AI (fallback)
# ============================================================================

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

    # Сначала пытаемся через Claude
    try:
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}]
        }

        headers = {
            "x-api-key": config.CLAUDE_API_KEY,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

        content = result["content"][0]["text"]
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content.strip())

    except Exception:
        # Фолбэк на расчёт по MET
        met_values = {
            "ходьба": 3.5, "бег": 8.0, "плавание": 6.0,
            "велосипед": 5.0, "тренировка": 5.0, "йога": 2.5,
            "фитнес": 5.5, "танцы": 4.5
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
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}]
    }

    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

    return result["content"][0]["text"]
