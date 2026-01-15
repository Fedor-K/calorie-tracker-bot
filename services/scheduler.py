from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, WaterEntry, FoodEntry

scheduler = AsyncIOScheduler()


async def send_water_reminder(bot: Bot):
    """Отправить напоминания о воде"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.remind_water == True)
        )
        users = result.scalars().all()

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        for user in users:
            # Проверяем, сколько воды выпито сегодня
            water_result = await session.execute(
                select(func.sum(WaterEntry.amount))
                .where(WaterEntry.user_id == user.id)
                .where(WaterEntry.created_at >= today_start)
            )
            total_water = water_result.scalar_one() or 0

            if total_water < user.water_goal:
                remaining = user.water_goal - total_water
                try:
                    await bot.send_message(
                        user.id,
                        f"💧 Напоминание о воде!\n\n"
                        f"Выпито: {total_water} мл\n"
                        f"Осталось: {remaining} мл до цели"
                    )
                except Exception:
                    pass  # Пользователь заблокировал бота


async def send_food_reminder(bot: Bot):
    """Отправить напоминания о еде"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.remind_food == True)
        )
        users = result.scalars().all()

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        for user in users:
            # Проверяем, сколько калорий съедено сегодня
            food_result = await session.execute(
                select(func.sum(FoodEntry.calories))
                .where(FoodEntry.user_id == user.id)
                .where(FoodEntry.created_at >= today_start)
            )
            total_calories = food_result.scalar_one() or 0

            # Отправляем, если съедено меньше 30% от цели
            if total_calories < user.calorie_goal * 0.3:
                try:
                    await bot.send_message(
                        user.id,
                        f"🍽 Время поесть!\n\n"
                        f"Сегодня: {total_calories} / {user.calorie_goal} ккал\n\n"
                        f"Отправь фото еды для подсчёта калорий"
                    )
                except Exception:
                    pass


async def send_weight_reminder(bot: Bot):
    """Отправить напоминания о взвешивании"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.remind_weight == True)
        )
        users = result.scalars().all()

        for user in users:
            try:
                await bot.send_message(
                    user.id,
                    f"⚖️ Не забудь взвеситься!\n\n"
                    f"Запиши вес: /weight 75.5"
                )
            except Exception:
                pass


async def send_daily_summary(bot: Bot):
    """Отправить вечернюю сводку"""
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        for user in users:
            # Калории
            food_result = await session.execute(
                select(func.sum(FoodEntry.calories))
                .where(FoodEntry.user_id == user.id)
                .where(FoodEntry.created_at >= today_start)
            )
            total_calories = food_result.scalar_one() or 0

            # Вода
            water_result = await session.execute(
                select(func.sum(WaterEntry.amount))
                .where(WaterEntry.user_id == user.id)
                .where(WaterEntry.created_at >= today_start)
            )
            total_water = water_result.scalar_one() or 0

            # Только если есть данные
            if total_calories > 0 or total_water > 0:
                calorie_pct = int(total_calories / user.calorie_goal * 100) if user.calorie_goal else 0
                water_pct = int(total_water / user.water_goal * 100) if user.water_goal else 0

                try:
                    await bot.send_message(
                        user.id,
                        f"📊 **Итоги дня**\n\n"
                        f"🔥 Калории: {total_calories} / {user.calorie_goal} ({calorie_pct}%)\n"
                        f"💧 Вода: {total_water} / {user.water_goal} мл ({water_pct}%)\n\n"
                        f"Хорошего вечера! 🌙",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass


def setup_scheduler(bot: Bot):
    """Настройка планировщика"""

    # Напоминания о воде каждые 2 часа с 9 до 21
    scheduler.add_job(
        send_water_reminder,
        CronTrigger(hour="9,11,13,15,17,19,21", minute=0),
        args=[bot],
        id="water_reminder",
        replace_existing=True
    )

    # Напоминания о еде в 8:00, 13:00, 19:00
    scheduler.add_job(
        send_food_reminder,
        CronTrigger(hour="8,13,19", minute=0),
        args=[bot],
        id="food_reminder",
        replace_existing=True
    )

    # Напоминание о весе в 8:00
    scheduler.add_job(
        send_weight_reminder,
        CronTrigger(hour=8, minute=0),
        args=[bot],
        id="weight_reminder",
        replace_existing=True
    )

    # Вечерняя сводка в 21:30
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=21, minute=30),
        args=[bot],
        id="daily_summary",
        replace_existing=True
    )

    scheduler.start()
    return scheduler
