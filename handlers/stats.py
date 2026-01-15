from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, FoodEntry, WaterEntry, WeightEntry, ActivityEntry

router = Router()


@router.message(F.text == "📊 Статистика")
async def handle_stats_button(message: Message):
    """Кнопка статистики"""
    await show_daily_stats(message)


@router.message(F.text.lower().startswith("/stats"))
async def cmd_stats(message: Message):
    """Команда /stats"""
    await show_daily_stats(message)


@router.message(F.text.lower().startswith("/week"))
async def cmd_week_stats(message: Message):
    """Статистика за неделю"""
    await show_weekly_stats(message)


async def show_daily_stats(message: Message):
    """Показать статистику за день"""
    user_id = message.from_user.id
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала добавь данные: отправь фото еды, запиши вес или воду.")
            return

        # Калории за сегодня
        calories_result = await session.execute(
            select(
                func.sum(FoodEntry.calories),
                func.sum(FoodEntry.protein),
                func.sum(FoodEntry.carbs),
                func.sum(FoodEntry.fat)
            )
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= today_start)
        )
        calories, protein, carbs, fat = calories_result.one()
        calories = calories or 0
        protein = protein or 0
        carbs = carbs or 0
        fat = fat or 0

        # Вода за сегодня
        water_result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= today_start)
        )
        water = water_result.scalar_one() or 0

        # Активность за сегодня
        activity_result = await session.execute(
            select(
                func.sum(ActivityEntry.duration),
                func.sum(ActivityEntry.calories_burned)
            )
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= today_start)
        )
        activity_duration, activity_calories = activity_result.one()
        activity_duration = activity_duration or 0
        activity_calories = activity_calories or 0

        # Количество приёмов пищи
        meals_result = await session.execute(
            select(func.count(FoodEntry.id))
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= today_start)
        )
        meals_count = meals_result.scalar_one() or 0

    # Прогресс-бары
    calorie_goal = user.calorie_goal
    water_goal = user.water_goal

    calorie_progress = min(100, int(calories / calorie_goal * 100)) if calorie_goal else 0
    water_progress = min(100, int(water / water_goal * 100)) if water_goal else 0

    calorie_bar = "█" * (calorie_progress // 10) + "░" * (10 - calorie_progress // 10)
    water_bar = "█" * (water_progress // 10) + "░" * (10 - water_progress // 10)

    # Нетто калории
    net_calories = calories - activity_calories

    response = (
        f"📊 **Статистика за сегодня**\n\n"
        f"🔥 **Калории**\n"
        f"[{calorie_bar}] {calorie_progress}%\n"
        f"Съедено: **{calories}** / {calorie_goal} ккал\n"
        f"Сожжено: -{activity_calories} ккал\n"
        f"Нетто: **{net_calories}** ккал\n\n"
        f"🥗 **БЖУ**\n"
        f"🥩 Белки: {protein:.0f} г\n"
        f"🍞 Углеводы: {carbs:.0f} г\n"
        f"🧈 Жиры: {fat:.0f} г\n\n"
        f"💧 **Вода**\n"
        f"[{water_bar}] {water_progress}%\n"
        f"Выпито: **{water}** / {water_goal} мл\n\n"
        f"🏃 **Активность**\n"
        f"Время: {activity_duration} мин\n\n"
        f"🍽 Приёмов пищи: {meals_count}"
    )

    # Добавляем информацию о весе
    if user.current_weight:
        response += f"\n⚖️ Текущий вес: {user.current_weight} кг"

    await message.answer(response, parse_mode="Markdown")


async def show_weekly_stats(message: Message):
    """Показать статистику за неделю"""
    user_id = message.from_user.id
    week_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала добавь данные.")
            return

        # Калории за неделю
        calories_result = await session.execute(
            select(func.sum(FoodEntry.calories))
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= week_start)
        )
        total_calories = calories_result.scalar_one() or 0

        # Вода за неделю
        water_result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= week_start)
        )
        total_water = water_result.scalar_one() or 0

        # Активность за неделю
        activity_result = await session.execute(
            select(func.sum(ActivityEntry.calories_burned))
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= week_start)
        )
        total_activity = activity_result.scalar_one() or 0

        # Изменение веса
        weight_result = await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .where(WeightEntry.created_at >= week_start)
            .order_by(WeightEntry.created_at)
        )
        weights = weight_result.scalars().all()

    avg_calories = int(total_calories / 7) if total_calories else 0
    avg_water = int(total_water / 7) if total_water else 0

    response = (
        f"📊 **Статистика за неделю**\n\n"
        f"🔥 Калорий всего: {total_calories} ккал\n"
        f"   В среднем: {avg_calories} ккал/день\n\n"
        f"💧 Воды всего: {total_water / 1000:.1f} л\n"
        f"   В среднем: {avg_water} мл/день\n\n"
        f"🏃 Сожжено: {total_activity} ккал\n"
    )

    if len(weights) >= 2:
        weight_diff = weights[-1].weight - weights[0].weight
        if weight_diff > 0:
            response += f"\n⚖️ Вес: +{weight_diff:.1f} кг за неделю"
        elif weight_diff < 0:
            response += f"\n⚖️ Вес: {weight_diff:.1f} кг за неделю"
        else:
            response += "\n⚖️ Вес не изменился"

    await message.answer(response, parse_mode="Markdown")
