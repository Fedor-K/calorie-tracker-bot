from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, FoodEntry, WaterEntry, WeightEntry, ActivityEntry

router = Router()


def get_day_bounds(timezone: str = "Europe/Moscow", days_ago: int = 0):
    """Получить начало и конец дня в UTC с учётом часового пояса пользователя"""
    try:
        tz = ZoneInfo(timezone)
    except:
        tz = ZoneInfo("Europe/Moscow")

    # Текущее время в часовом поясе пользователя
    now_local = datetime.now(tz)
    # Начало нужного дня в локальном времени
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    day_end_local = day_start_local + timedelta(days=1)

    # Конвертируем в UTC для запросов к БД
    day_start_utc = day_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    day_end_utc = day_end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    return day_start_utc, day_end_utc, day_start_local.date()


@router.message(F.text == "📊 Статистика")
async def handle_stats_button(message: Message):
    """Кнопка статистики"""
    await show_daily_stats(message)


@router.message(F.text.lower().startswith("/stats"))
async def cmd_stats(message: Message):
    """Команда /stats или /stats N (где N - дней назад)"""
    text = message.text.strip()
    parts = text.split()
    days_ago = 0
    if len(parts) > 1:
        try:
            days_ago = int(parts[1])
        except:
            pass
    await show_daily_stats(message, days_ago=days_ago)


@router.message(F.text.lower().startswith("/week"))
async def cmd_week_stats(message: Message):
    """Статистика за неделю"""
    await show_weekly_stats(message)


@router.message(F.text.lower().startswith("/history"))
async def cmd_history(message: Message):
    """История за последние 7 дней"""
    await show_history(message)


async def show_daily_stats(message: Message, days_ago: int = 0):
    """Показать статистику за день"""
    user_id = message.from_user.id

    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала добавь данные: отправь фото еды, запиши вес или воду.")
            return

        # Получаем границы дня с учётом часового пояса
        day_start, day_end, date_label = get_day_bounds(user.timezone, days_ago)

        # Калории за день
        calories_result = await session.execute(
            select(
                func.sum(FoodEntry.calories),
                func.sum(FoodEntry.protein),
                func.sum(FoodEntry.carbs),
                func.sum(FoodEntry.fat)
            )
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start)
            .where(FoodEntry.created_at < day_end)
        )
        calories, protein, carbs, fat = calories_result.one()
        calories = calories or 0
        protein = protein or 0
        carbs = carbs or 0
        fat = fat or 0

        # Вода за день
        water_result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start)
            .where(WaterEntry.created_at < day_end)
        )
        water = water_result.scalar_one() or 0

        # Активность за день
        activity_result = await session.execute(
            select(
                func.sum(ActivityEntry.duration),
                func.sum(ActivityEntry.calories_burned)
            )
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= day_start)
            .where(ActivityEntry.created_at < day_end)
        )
        activity_duration, activity_calories = activity_result.one()
        activity_duration = activity_duration or 0
        activity_calories = activity_calories or 0

        # Количество приёмов пищи
        meals_result = await session.execute(
            select(func.count(FoodEntry.id))
            .where(FoodEntry.user_id == user_id)
            .where(FoodEntry.created_at >= day_start)
            .where(FoodEntry.created_at < day_end)
        )
        meals_count = meals_result.scalar_one() or 0

    # Прогресс-бары
    calorie_goal = user.calorie_goal
    water_goal = user.water_goal

    calorie_progress = min(100, int(calories / calorie_goal * 100)) if calorie_goal else 0
    water_progress = min(100, int(water / water_goal * 100)) if water_goal else 0

    calorie_bar = "█" * (calorie_progress // 10) + "░" * (10 - calorie_progress // 10)
    water_bar = "█" * (water_progress // 10) + "░" * (10 - water_progress // 10)

    # Цели БЖУ
    protein_goal = user.protein_goal or 100
    # Углеводы: ~50% калорий / 4 ккал на грамм
    carbs_goal = int(calorie_goal * 0.5 / 4)
    # Жиры: ~25% калорий / 9 ккал на грамм
    fat_goal = int(calorie_goal * 0.25 / 9)

    # Нетто калории
    net_calories = calories - activity_calories

    # Заголовок в зависимости от дня
    if days_ago == 0:
        title = "📊 **Статистика за сегодня**"
    elif days_ago == 1:
        title = "📊 **Статистика за вчера**"
    else:
        title = f"📊 **Статистика за {date_label.strftime('%d.%m.%Y')}**"

    response = (
        f"{title}\n\n"
        f"🔥 **Калории**\n"
        f"[{calorie_bar}] {calorie_progress}%\n"
        f"Съедено: **{calories}** / {calorie_goal} ккал\n"
        f"Сожжено: -{activity_calories} ккал\n"
        f"Нетто: **{net_calories}** ккал\n\n"
        f"🥗 **БЖУ**\n"
        f"🥩 Белки: {protein:.0f} / {protein_goal} г\n"
        f"🍞 Углеводы: {carbs:.0f} / {carbs_goal} г\n"
        f"🧈 Жиры: {fat:.0f} / {fat_goal} г\n\n"
        f"💧 **Вода**\n"
        f"[{water_bar}] {water_progress}%\n"
        f"Выпито: **{water}** / {water_goal} мл\n\n"
        f"🏃 **Активность**\n"
        f"Сожжено: {activity_calories} ккал\n\n"
        f"🍽 Приёмов пищи: {meals_count}"
    )

    # Добавляем информацию о весе
    if user.current_weight:
        response += f"\n⚖️ Текущий вес: {user.current_weight} кг"

    # Подсказка о командах
    if days_ago == 0:
        response += "\n\n_/stats 1 — вчера, /history — неделя_"

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


async def show_history(message: Message):
    """Показать краткую историю за 7 дней"""
    user_id = message.from_user.id

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала добавь данные.")
            return

        response = "📅 **История за 7 дней**\n\n"

        for days_ago in range(7):
            day_start, day_end, date_label = get_day_bounds(user.timezone, days_ago)

            # Калории
            cal_result = await session.execute(
                select(func.sum(FoodEntry.calories))
                .where(FoodEntry.user_id == user_id)
                .where(FoodEntry.created_at >= day_start)
                .where(FoodEntry.created_at < day_end)
            )
            calories = cal_result.scalar_one() or 0

            # Вода
            water_result = await session.execute(
                select(func.sum(WaterEntry.amount))
                .where(WaterEntry.user_id == user_id)
                .where(WaterEntry.created_at >= day_start)
                .where(WaterEntry.created_at < day_end)
            )
            water = water_result.scalar_one() or 0

            # Форматирование
            if days_ago == 0:
                day_name = "Сегодня"
            elif days_ago == 1:
                day_name = "Вчера"
            else:
                day_name = date_label.strftime("%d.%m")

            # Индикатор выполнения цели
            cal_icon = "✅" if calories >= user.calorie_goal * 0.8 else "⚪"
            water_icon = "💧" if water >= user.water_goal * 0.8 else "⚪"

            response += f"**{day_name}**: {cal_icon} {calories} ккал | {water_icon} {water} мл\n"

        response += f"\n🎯 Цель: {user.calorie_goal} ккал, {user.water_goal} мл"
        response += "\n\n_/stats N — подробности за N дней назад_"

    await message.answer(response, parse_mode="Markdown")
