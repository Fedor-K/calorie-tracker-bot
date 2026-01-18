"""
Coach Service - Оркестрация AI коуча
Выполняет инструменты и управляет диалогом
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, delete

from database.db import async_session
from database.models import (
    User, FoodEntry, WaterEntry, WeightEntry, ActivityEntry
)
from services.memory import (
    save_message, get_recent_messages, save_memory, get_memories_as_text
)
from services.ai import (
    process_message, process_message_with_tool_results,
    estimate_activity_calories
)

logger = logging.getLogger(__name__)


# ============================================================================
# Получение контекста пользователя
# ============================================================================

async def get_user_context(user_id: int) -> dict:
    """
    Собирает полный контекст пользователя для AI
    """
    async with async_session() as session:
        # Получаем пользователя
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {
                "profile_complete": False,
                "name": None,
                "calorie_goal": 2000,
                "water_goal": 2000,
                "protein_goal": 100
            }

        # Определяем часовой пояс
        try:
            tz = ZoneInfo(user.timezone or "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # Еда за сегодня
        food_result = await session.execute(
            select(FoodEntry)
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start_utc)
        )
        foods = food_result.scalars().all()

        calories_today = sum(f.calories or 0 for f in foods)
        protein_today = sum(f.protein or 0 for f in foods)
        carbs_today = sum(f.carbs or 0 for f in foods)
        fat_today = sum(f.fat or 0 for f in foods)
        meals_today = [f.description for f in foods if f.description]

        # Вода за сегодня
        water_result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )
        water_today = water_result.scalar_one() or 0

        # Активности за сегодня
        activity_result = await session.execute(
            select(ActivityEntry)
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= day_start_utc)
        )
        activities = activity_result.scalars().all()
        calories_burned_today = sum(a.calories_burned or 0 for a in activities)
        activities_today = [f"{a.activity_type}: {a.calories_burned} ккал" for a in activities]

        # Профиль заполнен если есть рост и вес
        profile_complete = bool(user.height and user.current_weight)

        return {
            "profile_complete": profile_complete,
            "name": user.first_name,
            "country": user.country,
            "age": user.age,
            "gender": user.gender,
            "goal": user.goal,
            "height": user.height,
            "weight": user.current_weight,
            "target_weight": user.target_weight,
            "calorie_goal": user.calorie_goal,
            "water_goal": user.water_goal,
            "protein_goal": user.protein_goal,
            "calories_today": calories_today,
            "protein_today": protein_today,
            "carbs_today": carbs_today,
            "fat_today": fat_today,
            "water_today": water_today,
            "meals_today": meals_today,
            "calories_burned_today": calories_burned_today,
            "activities_today": activities_today,
            "timezone": user.timezone
        }


# ============================================================================
# Выполнение инструментов
# ============================================================================

async def execute_tool(user_id: int, tool_name: str, tool_input: dict) -> dict:
    """
    Выполняет инструмент и возвращает результат

    Returns:
        {"success": bool, "data": dict, "message": str}
    """
    try:
        if tool_name == "log_food":
            return await _log_food(user_id, tool_input)

        elif tool_name == "log_water":
            return await _log_water(user_id, tool_input)

        elif tool_name == "log_weight":
            return await _log_weight(user_id, tool_input)

        elif tool_name == "log_activity":
            return await _log_activity(user_id, tool_input)

        elif tool_name == "get_today_stats":
            return await _get_today_stats(user_id)

        elif tool_name == "get_weight_history":
            return await _get_weight_history(user_id, tool_input)

        elif tool_name == "remember_fact":
            return await _remember_fact(user_id, tool_input)

        elif tool_name == "update_profile":
            return await _update_profile(user_id, tool_input)

        elif tool_name == "check_profile_complete":
            return await _check_profile_complete(user_id)

        elif tool_name == "get_today_activities":
            return await _get_today_activities(user_id)

        elif tool_name == "update_daily_activity":
            return await _update_daily_activity(user_id, tool_input)

        elif tool_name == "clear_today_activities":
            return await _clear_today_activities(user_id, tool_input)

        elif tool_name == "list_today_food":
            return await _list_today_food(user_id)

        elif tool_name == "delete_food_entry":
            return await _delete_food_entry(user_id, tool_input)

        elif tool_name == "update_food_entry":
            return await _update_food_entry(user_id, tool_input)

        elif tool_name == "clear_today_food":
            return await _clear_today_food(user_id, tool_input)

        elif tool_name == "list_today_water":
            return await _list_today_water(user_id)

        elif tool_name == "clear_today_water":
            return await _clear_today_water(user_id, tool_input)

        elif tool_name == "set_today_water":
            return await _set_today_water(user_id, tool_input)

        else:
            return {"success": False, "message": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Tool execution error: {tool_name} | {e}")
        return {"success": False, "message": str(e)}


async def _log_food(user_id: int, data: dict) -> dict:
    """Записать приём пищи"""
    async with async_session() as session:
        food_entry = FoodEntry(
            user_id=user_id,
            description=data.get("description", "Еда"),
            meal_type=data.get("meal_type"),
            calories=data.get("calories", 0),
            protein=data.get("protein", 0),
            carbs=data.get("carbs", 0),
            fat=data.get("fat", 0),
            fiber=data.get("fiber", 0)
        )
        session.add(food_entry)
        await session.commit()

    return {
        "success": True,
        "data": {
            "description": data.get("description"),
            "calories": data.get("calories", 0),
            "protein": data.get("protein", 0),
            "carbs": data.get("carbs", 0),
            "fat": data.get("fat", 0)
        },
        "message": f"Записано: {data.get('description')} ({data.get('calories', 0)} ккал)"
    }


async def _log_water(user_id: int, data: dict) -> dict:
    """Записать воду"""
    amount = data.get("amount_ml", 250)

    async with async_session() as session:
        entry = WaterEntry(user_id=user_id, amount=amount)
        session.add(entry)
        await session.commit()

        # Получаем общее количество за сегодня
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        total_result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )
        total = total_result.scalar_one() or 0
        goal = user.water_goal if user else 2000

    return {
        "success": True,
        "data": {"amount_ml": amount, "total_today": total, "goal": goal},
        "message": f"+{amount} мл воды. Всего: {total}/{goal} мл"
    }


async def _log_weight(user_id: int, data: dict) -> dict:
    """Записать вес"""
    weight = data.get("weight_kg")

    async with async_session() as session:
        # Сохраняем в историю
        entry = WeightEntry(user_id=user_id, weight=weight)
        session.add(entry)

        # Обновляем текущий вес в профиле
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.current_weight = weight
        await session.commit()

    return {
        "success": True,
        "data": {"weight_kg": weight},
        "message": f"Вес записан: {weight} кг"
    }


async def _log_activity(user_id: int, data: dict) -> dict:
    """Записать активность"""
    activity_type = data.get("activity_type", "тренировка")
    duration = data.get("duration_minutes", 30)
    calories_burned = data.get("calories_burned")

    # Если калории не указаны — рассчитываем
    if calories_burned is None:
        async with async_session() as session:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            weight = user.current_weight if user else 70

        activity_result = await estimate_activity_calories(activity_type, duration, weight)
        calories_burned = activity_result.get("calories_burned", 0)

    async with async_session() as session:
        entry = ActivityEntry(
            user_id=user_id,
            activity_type=activity_type,
            duration=duration,
            calories_burned=calories_burned
        )
        session.add(entry)
        await session.commit()

    return {
        "success": True,
        "data": {
            "activity_type": activity_type,
            "duration_minutes": duration,
            "calories_burned": calories_burned
        },
        "message": f"Активность записана: {activity_type} {duration} мин (-{calories_burned} ккал)"
    }


async def _get_today_stats(user_id: int) -> dict:
    """Получить статистику за сегодня"""
    context = await get_user_context(user_id)

    return {
        "success": True,
        "data": {
            "calories": context.get("calories_today", 0),
            "calorie_goal": context.get("calorie_goal", 2000),
            "protein": context.get("protein_today", 0),
            "carbs": context.get("carbs_today", 0),
            "fat": context.get("fat_today", 0),
            "water": context.get("water_today", 0),
            "water_goal": context.get("water_goal", 2000),
            "meals": context.get("meals_today", [])
        },
        "message": f"Калории: {context.get('calories_today', 0)}/{context.get('calorie_goal', 2000)}, Вода: {context.get('water_today', 0)}/{context.get('water_goal', 2000)} мл"
    }


async def _get_weight_history(user_id: int, data: dict) -> dict:
    """Получить историю веса"""
    days = data.get("days", 7)
    cutoff = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        result = await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .where(WeightEntry.created_at >= cutoff)
            .order_by(WeightEntry.created_at.desc())
        )
        entries = result.scalars().all()

    history = [
        {"date": e.created_at.strftime("%d.%m"), "weight": e.weight}
        for e in entries
    ]

    if len(history) >= 2:
        change = history[0]["weight"] - history[-1]["weight"]
        trend = "снизился" if change < 0 else "вырос" if change > 0 else "не изменился"
    else:
        change = 0
        trend = "недостаточно данных"

    return {
        "success": True,
        "data": {"history": history, "change": change, "trend": trend},
        "message": f"История за {days} дней: {len(history)} записей, вес {trend}"
    }


async def _remember_fact(user_id: int, data: dict) -> dict:
    """Запомнить факт о пользователе"""
    category = data.get("category", "fact")
    content = data.get("content", "")

    await save_memory(user_id, category, content)

    return {
        "success": True,
        "data": {"category": category, "content": content},
        "message": f"Запомнил: {content}"
    }


async def _update_profile(user_id: int, data: dict) -> dict:
    """Обновить профиль пользователя"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)

        updated_fields = []

        if "first_name" in data:
            user.first_name = data["first_name"]
            updated_fields.append("имя")

        if "age" in data:
            user.age = data["age"]
            updated_fields.append("возраст")

        if "gender" in data:
            user.gender = data["gender"]
            updated_fields.append("пол")

        if "height_cm" in data:
            user.height = data["height_cm"]
            updated_fields.append("рост")

        if "current_weight_kg" in data:
            user.current_weight = data["current_weight_kg"]
            updated_fields.append("вес")

        if "target_weight_kg" in data:
            user.target_weight = data["target_weight_kg"]
            updated_fields.append("целевой вес")

        if "calorie_goal" in data:
            user.calorie_goal = data["calorie_goal"]
            updated_fields.append("цель калорий")

        if "water_goal" in data:
            user.water_goal = data["water_goal"]
            updated_fields.append("цель воды")

        if "goal" in data:
            user.goal = data["goal"]
            updated_fields.append("цель")

        # Автоматически рассчитываем нормы если есть данные
        if user.height and user.current_weight and not data.get("calorie_goal"):
            # Mifflin-St Jeor с умеренной активностью
            if user.gender == "male":
                bmr = 10 * user.current_weight + 6.25 * user.height - 5 * (user.age or 30) + 5
            else:
                bmr = 10 * user.current_weight + 6.25 * user.height - 5 * (user.age or 30) - 161

            tdee = int(bmr * 1.55)  # Умеренная активность

            if user.goal == "lose":
                user.calorie_goal = tdee - 500
            elif user.goal == "gain":
                user.calorie_goal = tdee + 300
            else:
                user.calorie_goal = tdee

            # Вода: 33мл на кг
            user.water_goal = int(user.current_weight * 33 // 100 * 100)

            # Белок: 1.6г на кг
            user.protein_goal = int(user.current_weight * 1.6)

        await session.commit()

    return {
        "success": True,
        "data": data,
        "message": f"Обновлено: {', '.join(updated_fields)}" if updated_fields else "Профиль обновлён"
    }


async def _check_profile_complete(user_id: int) -> dict:
    """Проверить заполненность профиля"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {
                "success": True,
                "data": {
                    "complete": False,
                    "missing": ["имя", "рост", "вес", "цель"]
                },
                "message": "Профиль не заполнен"
            }

        missing = []
        if not user.first_name:
            missing.append("имя")
        if not user.height:
            missing.append("рост")
        if not user.current_weight:
            missing.append("вес")
        if not user.goal:
            missing.append("цель")

        complete = len(missing) == 0

        return {
            "success": True,
            "data": {"complete": complete, "missing": missing},
            "message": "Профиль заполнен" if complete else f"Не хватает: {', '.join(missing)}"
        }


async def _get_today_activities(user_id: int) -> dict:
    """Получить список активностей за сегодня"""
    async with async_session() as session:
        # Получаем пользователя для timezone
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        result = await session.execute(
            select(ActivityEntry)
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= day_start_utc)
            .order_by(ActivityEntry.created_at)
        )
        activities = result.scalars().all()

        total_calories = sum(a.calories_burned or 0 for a in activities)
        activities_list = [
            f"{a.activity_type}: {a.calories_burned} ккал"
            for a in activities
        ]

        return {
            "success": True,
            "data": {
                "count": len(activities),
                "total_calories": total_calories,
                "activities": activities_list
            },
            "message": f"Сегодня записано {len(activities)} активностей, всего сожжено {total_calories} ккал"
        }


async def _update_daily_activity(user_id: int, data: dict) -> dict:
    """Обновить или создать дневную активность"""
    calories_burned = data.get("calories_burned", 0)
    activity_type = data.get("activity_type", "дневная активность")
    reason = data.get("reason", "обновление по запросу")

    async with async_session() as session:
        # Получаем пользователя для timezone
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # Удаляем все активности за сегодня
        await session.execute(
            delete(ActivityEntry)
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= day_start_utc)
        )

        # Создаём одну правильную запись
        new_entry = ActivityEntry(
            user_id=user_id,
            activity_type=activity_type,
            duration=0,
            calories_burned=calories_burned
        )
        session.add(new_entry)
        await session.commit()

        logger.info(f"[ACTIVITY] user={user_id} | Updated to {calories_burned} ккал | reason: {reason}")

        return {
            "success": True,
            "data": {
                "calories_burned": calories_burned,
                "activity_type": activity_type
            },
            "message": f"Активность обновлена: {activity_type} = {calories_burned} ккал"
        }


async def _clear_today_activities(user_id: int, data: dict) -> dict:
    """Удалить все активности за сегодня"""
    if not data.get("confirm"):
        return {"success": False, "message": "Требуется подтверждение (confirm: true)"}

    async with async_session() as session:
        # Получаем пользователя для timezone
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # Считаем сколько удалим
        count_result = await session.execute(
            select(func.count(ActivityEntry.id))
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= day_start_utc)
        )
        count = count_result.scalar_one() or 0

        # Удаляем
        await session.execute(
            delete(ActivityEntry)
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= day_start_utc)
        )
        await session.commit()

        logger.info(f"[ACTIVITY] user={user_id} | Cleared {count} activities")

        return {
            "success": True,
            "data": {"deleted_count": count},
            "message": f"Удалено {count} активностей за сегодня"
        }


async def _list_today_food(user_id: int) -> dict:
    """Показать все записи еды за сегодня"""
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        result = await session.execute(
            select(FoodEntry)
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start_utc)
            .order_by(FoodEntry.created_at)
        )
        entries = result.scalars().all()

        if not entries:
            return {
                "success": True,
                "data": {"entries": [], "total_calories": 0},
                "message": "Записей еды за сегодня нет"
            }

        entries_list = []
        total_calories = 0
        for i, entry in enumerate(entries, 1):
            entries_list.append({
                "number": i,
                "id": entry.id,
                "description": entry.description,
                "calories": entry.calories,
                "protein": entry.protein,
                "carbs": entry.carbs,
                "fat": entry.fat,
                "time": entry.created_at.strftime("%H:%M")
            })
            total_calories += entry.calories or 0

        return {
            "success": True,
            "data": {"entries": entries_list, "total_calories": total_calories},
            "message": f"Найдено {len(entries)} записей, всего {total_calories} ккал"
        }


async def _delete_food_entry(user_id: int, data: dict) -> dict:
    """Удалить запись еды"""
    entry_number = data.get("entry_number")
    description_match = data.get("description_match", "").lower()

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        result = await session.execute(
            select(FoodEntry)
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start_utc)
            .order_by(FoodEntry.created_at)
        )
        entries = result.scalars().all()

        entry_to_delete = None

        if entry_number and 1 <= entry_number <= len(entries):
            entry_to_delete = entries[entry_number - 1]
        elif description_match:
            for entry in entries:
                if description_match in (entry.description or "").lower():
                    entry_to_delete = entry
                    break

        if not entry_to_delete:
            return {
                "success": False,
                "message": f"Запись не найдена. Всего записей: {len(entries)}"
            }

        description = entry_to_delete.description
        calories = entry_to_delete.calories

        await session.delete(entry_to_delete)
        await session.commit()

        logger.info(f"[FOOD] user={user_id} | Deleted: {description} ({calories} ккал)")

        return {
            "success": True,
            "data": {"deleted": description, "calories": calories},
            "message": f"Удалено: {description} ({calories} ккал)"
        }


async def _update_food_entry(user_id: int, data: dict) -> dict:
    """Изменить запись еды"""
    entry_number = data.get("entry_number")
    description_match = data.get("description_match", "").lower()

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        result = await session.execute(
            select(FoodEntry)
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start_utc)
            .order_by(FoodEntry.created_at)
        )
        entries = result.scalars().all()

        entry_to_update = None

        if entry_number and 1 <= entry_number <= len(entries):
            entry_to_update = entries[entry_number - 1]
        elif description_match:
            for entry in entries:
                if description_match in (entry.description or "").lower():
                    entry_to_update = entry
                    break

        if not entry_to_update:
            return {
                "success": False,
                "message": f"Запись не найдена. Всего записей: {len(entries)}"
            }

        old_desc = entry_to_update.description
        old_cal = entry_to_update.calories

        # Обновляем только переданные поля
        if data.get("new_description"):
            entry_to_update.description = data["new_description"]
        if data.get("new_calories") is not None:
            entry_to_update.calories = data["new_calories"]
        if data.get("new_protein") is not None:
            entry_to_update.protein = data["new_protein"]
        if data.get("new_carbs") is not None:
            entry_to_update.carbs = data["new_carbs"]
        if data.get("new_fat") is not None:
            entry_to_update.fat = data["new_fat"]

        await session.commit()

        logger.info(f"[FOOD] user={user_id} | Updated: {old_desc} -> {entry_to_update.description}")

        return {
            "success": True,
            "data": {
                "old": {"description": old_desc, "calories": old_cal},
                "new": {"description": entry_to_update.description, "calories": entry_to_update.calories}
            },
            "message": f"Обновлено: {entry_to_update.description} ({entry_to_update.calories} ккал)"
        }


async def _clear_today_food(user_id: int, data: dict) -> dict:
    """Удалить все записи еды за сегодня"""
    if not data.get("confirm"):
        return {"success": False, "message": "Требуется подтверждение (confirm: true)"}

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        count_result = await session.execute(
            select(func.count(FoodEntry.id))
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start_utc)
        )
        count = count_result.scalar_one() or 0

        await session.execute(
            delete(FoodEntry)
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start_utc)
        )
        await session.commit()

        logger.info(f"[FOOD] user={user_id} | Cleared {count} food entries")

        return {
            "success": True,
            "data": {"deleted_count": count},
            "message": f"Удалено {count} записей еды за сегодня"
        }


async def _list_today_water(user_id: int) -> dict:
    """Показать все записи воды за сегодня"""
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        result = await session.execute(
            select(WaterEntry)
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
            .order_by(WaterEntry.created_at)
        )
        entries = result.scalars().all()

        total = sum(e.amount or 0 for e in entries)
        entries_list = [
            {"time": e.created_at.strftime("%H:%M"), "amount": e.amount}
            for e in entries
        ]

        return {
            "success": True,
            "data": {"entries": entries_list, "total": total},
            "message": f"Вода за сегодня: {total} мл ({len(entries)} записей)"
        }


async def _clear_today_water(user_id: int, data: dict) -> dict:
    """Удалить все записи воды за сегодня"""
    if not data.get("confirm"):
        return {"success": False, "message": "Требуется подтверждение (confirm: true)"}

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        count_result = await session.execute(
            select(func.count(WaterEntry.id))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )
        count = count_result.scalar_one() or 0

        await session.execute(
            delete(WaterEntry)
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )
        await session.commit()

        logger.info(f"[WATER] user={user_id} | Cleared {count} water entries")

        return {
            "success": True,
            "data": {"deleted_count": count},
            "message": f"Удалено {count} записей воды за сегодня"
        }


async def _set_today_water(user_id: int, data: dict) -> dict:
    """Установить конкретное количество воды за сегодня"""
    amount = data.get("amount_ml", 0)

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # Удаляем все записи за сегодня
        await session.execute(
            delete(WaterEntry)
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )

        # Создаём одну запись с нужным количеством
        if amount > 0:
            entry = WaterEntry(user_id=user_id, amount=amount)
            session.add(entry)

        await session.commit()

        logger.info(f"[WATER] user={user_id} | Set water to {amount} ml")

        return {
            "success": True,
            "data": {"water": amount},
            "message": f"Вода за сегодня: {amount} мл"
        }


# ============================================================================
# Главная функция обработки сообщения
# ============================================================================

async def handle_message(user_id: int, message_text: str) -> str:
    """
    Обработать сообщение пользователя через AI коуча

    Args:
        user_id: ID пользователя в Telegram
        message_text: Текст сообщения

    Returns:
        Текст ответа пользователю
    """
    logger.info(f"[COACH] user={user_id} | message: {message_text[:100]}")

    # 1. Загружаем контекст
    user_context = await get_user_context(user_id)
    memories_text = await get_memories_as_text(user_id)
    conversation = await get_recent_messages(user_id, limit=10)

    # 2. Отправляем в AI
    result = await process_message(
        user_id=user_id,
        message=message_text,
        user_context=user_context,
        memories_text=memories_text,
        conversation=conversation
    )

    response_text = result.get("response", "")
    tool_calls = result.get("tool_calls", [])

    # 3. Выполняем инструменты если есть
    tool_results_data = []
    for tool in tool_calls:
        tool_name = tool["name"]
        tool_input = tool["input"]
        tool_id = tool["id"]

        exec_result = await execute_tool(user_id, tool_name, tool_input)
        logger.info(f"[COACH] Tool result: {tool_name} | {exec_result.get('message', '')}")

        tool_results_data.append({
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": json.dumps(exec_result, ensure_ascii=False)
        })

    # 4. Если были инструменты — получаем финальный ответ
    if tool_calls:
        # Формируем assistant_content для продолжения
        assistant_content = []
        if response_text:
            assistant_content.append({"type": "text", "text": response_text})
        for tool in tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tool["id"],
                "name": tool["name"],
                "input": tool["input"]
            })

        # Обновляем контекст после выполнения инструментов
        user_context = await get_user_context(user_id)

        final_response = await process_message_with_tool_results(
            user_id=user_id,
            original_message=message_text,
            user_context=user_context,
            memories_text=memories_text,
            conversation=conversation,
            assistant_content=assistant_content,
            tool_results=tool_results_data
        )
        response_text = final_response

        # Если AI вернул пустой ответ после инструментов - генерируем fallback
        if not response_text or not response_text.strip():
            tool_messages = [r.get("content", "") for r in tool_results_data]
            try:
                # Пытаемся извлечь message из tool results
                fallback_parts = []
                for tm in tool_messages:
                    parsed = json.loads(tm)
                    if parsed.get("message"):
                        fallback_parts.append(parsed["message"])
                if fallback_parts:
                    response_text = "✅ Готово!\n\n" + "\n".join(f"• {p}" for p in fallback_parts)
                else:
                    response_text = "✅ Готово!"
            except Exception:
                response_text = "✅ Готово!"

    # Финальная проверка на пустой ответ
    if not response_text or not response_text.strip():
        response_text = "Готово! Чем ещё могу помочь?"

    # 5. Сохраняем сообщения в историю
    await save_message(user_id, "user", message_text)
    await save_message(user_id, "assistant", response_text)

    logger.info(f"[COACH] user={user_id} | response: {response_text[:100]}...")

    return response_text


async def format_food_analysis(
    user_id: int,
    food_data: dict,
    user_context: Optional[dict] = None,
    saved: bool = False
) -> str:
    """
    Формирует красивый ответ для фото еды БЕЗ сохранения

    Args:
        user_id: ID пользователя
        food_data: Результат анализа от AI
        user_context: Контекст (опционально, загрузится автоматически)
        saved: Показывать что уже сохранено

    Returns:
        Форматированный текст ответа
    """
    if user_context is None:
        user_context = await get_user_context(user_id)

    total = food_data.get("total", {})
    description = food_data.get("description", "Анализ еды")

    # Формируем ответ
    if saved:
        response = f"✅ **Записано!**\n\n"
    else:
        response = f"📸 **Анализ фото**\n\n"
    response += f"🍽 **{description}**\n\n"

    response += "📊 **КБЖУ:**\n"
    response += f"├ 🔥 Калории: {total.get('calories', 0)} ккал\n"
    response += f"├ 🥩 Белки: {total.get('protein', 0)} г\n"
    response += f"├ 🍞 Углеводы: {total.get('carbs', 0)} г\n"
    response += f"└ 🧈 Жиры: {total.get('fat', 0)} г\n"

    if total.get("fiber"):
        response += f"    🥬 Клетчатка: {total.get('fiber')} г\n"

    # Микроэлементы если есть
    micro = food_data.get("micronutrients", {})
    if micro:
        response += "\n🧪 **Микроэлементы:**\n"
        if micro.get("sodium_mg"):
            response += f"├ Натрий: ~{micro.get('sodium_mg')} мг\n"
        if micro.get("iron_mg"):
            response += f"├ Железо: ~{micro.get('iron_mg')} мг\n"
        if micro.get("vitamin_info"):
            response += f"└ {micro.get('vitamin_info')}\n"

    # Осталось на сегодня
    calories_left = user_context.get("calorie_goal", 2000) - user_context.get("calories_today", 0)
    protein_left = user_context.get("protein_goal", 100) - user_context.get("protein_today", 0)
    water_left = user_context.get("water_goal", 2000) - user_context.get("water_today", 0)

    response += f"\n📈 **Осталось на сегодня:**\n"
    response += f"├ Калории: {max(0, calories_left)} / {user_context.get('calorie_goal', 2000)} ккал\n"
    response += f"├ Белок: {max(0, protein_left)} / {user_context.get('protein_goal', 100)} г\n"
    response += f"└ Вода: {max(0, water_left)} / {user_context.get('water_goal', 2000)} мл\n"

    # Комментарий
    if food_data.get("health_notes"):
        response += f"\n💬 **Анализ:**\n{food_data.get('health_notes')}"

    # ЗОЖ-альтернативы если блюдо не очень полезное
    health_score = food_data.get("health_score", 5)
    alternatives = food_data.get("healthy_alternatives", [])

    if alternatives and health_score < 7:
        response += f"\n\n🥗 **ЗОЖ-альтернативы:**\n"
        for alt in alternatives[:3]:  # максимум 3
            response += f"• {alt}\n"

    return response


async def save_food_entry(user_id: int, food_data: dict) -> bool:
    """
    Сохраняет еду в базу данных

    Args:
        user_id: ID пользователя
        food_data: Данные о еде от AI

    Returns:
        True если успешно сохранено
    """
    total = food_data.get("total", {})
    description = food_data.get("description", "Еда")

    async with async_session() as session:
        food_entry = FoodEntry(
            user_id=user_id,
            description=description,
            meal_type=food_data.get("meal_type"),
            calories=total.get("calories", 0),
            protein=total.get("protein", 0),
            carbs=total.get("carbs", 0),
            fat=total.get("fat", 0),
            fiber=total.get("fiber", 0),
            ai_raw_response=json.dumps(food_data, ensure_ascii=False)
        )
        session.add(food_entry)
        await session.commit()

    return True


async def handle_photo_message(
    user_id: int,
    food_data: dict,
    user_context: Optional[dict] = None
) -> str:
    """
    Обрабатывает фото еды: сохраняет и возвращает ответ

    Для нового потока с подтверждением используйте:
    - format_food_analysis() - только форматирование
    - save_food_entry() - только сохранение
    """
    # Сохраняем
    await save_food_entry(user_id, food_data)

    # Обновляем контекст и форматируем
    user_context = await get_user_context(user_id)
    return await format_food_analysis(user_id, food_data, user_context, saved=True)


async def handle_fitness_photo(user_id: int, fitness_data: dict) -> str:
    """
    Обрабатывает фото фитнес-трекера и сохраняет активность

    Args:
        user_id: ID пользователя
        fitness_data: Данные с фитнес-трекера

    Returns:
        Форматированный текст ответа
    """
    # Логируем что AI вернул
    logger.info(f"[FITNESS] user={user_id} | AI response: {fitness_data}")

    device = fitness_data.get("device", "фитнес-трекер")
    activity = fitness_data.get("activity_data", {})
    summary = fitness_data.get("summary", "")

    response = f"⌚ **Данные с {device}**\n\n"

    # Показываем все найденные данные
    if activity.get("steps"):
        response += f"👣 Шаги: {activity['steps']:,}\n"

    if activity.get("calories_burned"):
        response += f"🔥 Сожжено: {activity['calories_burned']} ккал\n"

    if activity.get("active_minutes"):
        response += f"⏱ Активность: {activity['active_minutes']} мин\n"

    if activity.get("distance_km"):
        response += f"📍 Дистанция: {activity['distance_km']} км\n"

    if activity.get("heart_rate"):
        response += f"❤️ Пульс: {activity['heart_rate']} уд/мин\n"

    if activity.get("floors"):
        response += f"🏢 Этажи: {activity['floors']}\n"

    # Определяем что сохранять
    workout_type = activity.get("workout_type")
    workout_duration = activity.get("workout_duration_min") or activity.get("active_minutes")
    calories_burned = activity.get("calories_burned")
    steps = activity.get("steps")
    distance_km = activity.get("distance_km")
    floors = activity.get("floors")

    # Если калории не указаны — рассчитываем по шагам/дистанции/этажам
    if not calories_burned and (steps or distance_km or floors):
        estimated_calories = 0

        # ~0.04 ккал на шаг (среднее)
        if steps:
            estimated_calories += int(steps * 0.04)

        # +10 ккал за каждый этаж
        if floors:
            estimated_calories += int(floors * 10)

        # Если есть дистанция но нет шагов — ~50 ккал/км
        if distance_km and not steps:
            estimated_calories += int(distance_km * 50)

        if estimated_calories > 0:
            calories_burned = estimated_calories
            response += f"\n📊 *Расчёт: ~{calories_burned} ккал*\n"

    # Определяем тип активности и сохраняем/обновляем
    if calories_burned and calories_burned > 0:
        if workout_type:
            activity_name = workout_type
        elif steps and steps > 8000:
            activity_name = "активный день"
        elif steps and steps > 5000:
            activity_name = "ходьба"
        else:
            activity_name = "дневная активность"

        # Ищем существующую запись "дневная активность" за сегодня и ОБНОВЛЯЕМ
        async with async_session() as session:
            # Получаем пользователя для timezone
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            try:
                tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
            except Exception:
                tz = ZoneInfo("Europe/Moscow")

            now_local = datetime.now(tz)
            day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            # Ищем запись "дневная активность" или "активный день" или "ходьба" за сегодня
            existing_result = await session.execute(
                select(ActivityEntry)
                .where(ActivityEntry.user_id == user_id)
                .where(ActivityEntry.created_at >= day_start_utc)
                .where(ActivityEntry.activity_type.in_(["дневная активность", "активный день", "ходьба"]))
                .order_by(ActivityEntry.created_at.desc())
                .limit(1)
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # Обновляем существующую запись
                old_calories = existing.calories_burned
                existing.activity_type = activity_name
                existing.calories_burned = calories_burned
                existing.duration = workout_duration or 0
                await session.commit()

                response += f"\n🔄 **Обновлено: {activity_name}**"
                response += f"\n🔥 Было: {old_calories} ккал → Стало: {calories_burned} ккал"
                if steps:
                    response += f" ({steps:,} шагов)"
            else:
                # Создаём новую запись
                activity_entry = ActivityEntry(
                    user_id=user_id,
                    activity_type=activity_name,
                    duration=workout_duration or 0,
                    calories_burned=calories_burned
                )
                session.add(activity_entry)
                await session.commit()

                response += f"\n✅ **Записано: {activity_name}**"
                response += f"\n🔥 Сожжено: -{calories_burned} ккал"
                if steps:
                    response += f" ({steps:,} шагов)"
    else:
        response += f"\n\n💡 Не удалось определить активность."
        response += f"\nОтправь скриншот с кольцами активности или шагами."

    if summary:
        response += f"\n\n📝 {summary}"

    return response
