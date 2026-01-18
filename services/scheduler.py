from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, WaterEntry, FoodEntry


def get_user_local_hour(user: User) -> int:
    """Получить текущий час в часовом поясе пользователя"""
    try:
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
    except:
        tz = ZoneInfo("Europe/Moscow")
    return datetime.now(tz).hour

scheduler = AsyncIOScheduler()


def get_water_reminder_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для напоминания о воде"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💧 Выпил 250мл", callback_data="remind_water_250"),
            InlineKeyboardButton(text="💧 Выпил 500мл", callback_data="remind_water_500"),
        ],
        [
            InlineKeyboardButton(text="⏰ Напомни позже", callback_data="remind_water_later"),
        ]
    ])


async def send_water_reminder(bot: Bot):
    """Отправить напоминания о воде (каждый час проверяем локальное время)"""
    # Часы для напоминаний о воде (по местному времени пользователя)
    water_hours = {9, 11, 13, 15, 17, 19, 21}

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.remind_water == True)
        )
        users = result.scalars().all()

        for user in users:
            # Проверяем, подходит ли час для этого пользователя
            local_hour = get_user_local_hour(user)
            if local_hour not in water_hours:
                continue

            # Получаем начало дня в часовом поясе пользователя
            try:
                tz = ZoneInfo(user.timezone or "Europe/Moscow")
            except:
                tz = ZoneInfo("Europe/Moscow")
            now_local = datetime.now(tz)
            day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start_utc = day_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            # Проверяем, сколько воды выпито сегодня
            water_result = await session.execute(
                select(func.sum(WaterEntry.amount))
                .where(WaterEntry.user_id == user.id)
                .where(WaterEntry.created_at >= day_start_utc)
            )
            total_water = water_result.scalar_one() or 0

            if total_water < user.water_goal:
                remaining = user.water_goal - total_water
                progress = int(total_water / user.water_goal * 100) if user.water_goal else 0
                try:
                    await bot.send_message(
                        user.id,
                        f"💧 **Время попить воды!**\n\n"
                        f"Выпито: {total_water} / {user.water_goal} мл ({progress}%)\n"
                        f"Осталось: {remaining} мл\n\n"
                        f"Выпил воду?",
                        reply_markup=get_water_reminder_keyboard(),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass


async def send_food_reminder(bot: Bot):
    """Отправить напоминания о еде"""
    # Часы для напоминаний о еде (по местному времени)
    food_hours = {8, 13, 19}

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.remind_food == True)
        )
        users = result.scalars().all()

        for user in users:
            local_hour = get_user_local_hour(user)
            if local_hour not in food_hours:
                continue

            # Получаем начало дня в часовом поясе пользователя
            try:
                tz = ZoneInfo(user.timezone or "Europe/Moscow")
            except:
                tz = ZoneInfo("Europe/Moscow")
            now_local = datetime.now(tz)
            day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start_utc = day_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            # Проверяем, сколько калорий съедено сегодня
            food_result = await session.execute(
                select(func.sum(FoodEntry.calories))
                .where(FoodEntry.user_id == user.id)
                .where(FoodEntry.created_at >= day_start_utc)
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
            # Отправляем в 8:00 по местному времени
            if get_user_local_hour(user) != 8:
                continue

            try:
                await bot.send_message(
                    user.id,
                    f"⚖️ Не забудь взвеситься!\n\n"
                    f"Запиши вес: /weight 75.5"
                )
            except Exception:
                pass


def get_sleep_reminder_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для напоминания о сне"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="😴 Иду спать", callback_data="sleep_going"),
            InlineKeyboardButton(text="⏰ Ещё 30 мин", callback_data="sleep_later"),
        ]
    ])


async def send_sleep_reminder(bot: Bot):
    """Отправить напоминания о подготовке ко сну"""
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        for user in users:
            # Отправляем в 22:00 по местному времени
            if get_user_local_hour(user) != 22:
                continue

            try:
                await bot.send_message(
                    user.id,
                    f"🌙 **Время готовиться ко сну!**\n\n"
                    f"Для хорошего сна:\n"
                    f"• Отложи телефон за 30 мин до сна\n"
                    f"• Проветри комнату\n"
                    f"• Выпей воды\n"
                    f"• Избегай яркого света\n\n"
                    f"Оптимально спать 7-8 часов 💤",
                    reply_markup=get_sleep_reminder_keyboard(),
                    parse_mode="Markdown"
                )
            except Exception:
                pass


async def send_daily_summary(bot: Bot):
    """Отправить вечернюю сводку"""
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        for user in users:
            # Отправляем в 21:00 по местному времени
            if get_user_local_hour(user) != 21:
                continue

            # Получаем начало дня в часовом поясе пользователя
            try:
                tz = ZoneInfo(user.timezone or "Europe/Moscow")
            except:
                tz = ZoneInfo("Europe/Moscow")
            now_local = datetime.now(tz)
            day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start_utc = day_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            # Калории
            food_result = await session.execute(
                select(func.sum(FoodEntry.calories))
                .where(FoodEntry.user_id == user.id)
                .where(FoodEntry.created_at >= day_start_utc)
            )
            total_calories = food_result.scalar_one() or 0

            # Вода
            water_result = await session.execute(
                select(func.sum(WaterEntry.amount))
                .where(WaterEntry.user_id == user.id)
                .where(WaterEntry.created_at >= day_start_utc)
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
    """Настройка планировщика

    Все задачи запускаются каждый час, а внутри функций проверяется
    локальное время каждого пользователя для отправки напоминаний.
    """

    # Напоминания о воде - каждый час проверяем локальное время пользователей
    scheduler.add_job(
        send_water_reminder,
        CronTrigger(minute=0),  # Каждый час в :00
        args=[bot],
        id="water_reminder",
        replace_existing=True
    )

    # Напоминания о еде - каждый час
    scheduler.add_job(
        send_food_reminder,
        CronTrigger(minute=0),
        args=[bot],
        id="food_reminder",
        replace_existing=True
    )

    # Напоминание о весе - каждый час
    scheduler.add_job(
        send_weight_reminder,
        CronTrigger(minute=0),
        args=[bot],
        id="weight_reminder",
        replace_existing=True
    )

    # Вечерняя сводка - каждый час в :30
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(minute=30),
        args=[bot],
        id="daily_summary",
        replace_existing=True
    )

    # Напоминание о сне - каждый час
    scheduler.add_job(
        send_sleep_reminder,
        CronTrigger(minute=0),
        args=[bot],
        id="sleep_reminder",
        replace_existing=True
    )

    scheduler.start()
    return scheduler
