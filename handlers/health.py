"""
Обработчик данных из Apple Health через Shortcuts
Пользователь отправляет текст в формате:
/health шаги 8500
/health пульс 72
/health сон 7.5
/health калории 450
"""
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from database.db import async_session
from database.models import User, ActivityEntry

router = Router()

# Примерные калории на шаг (зависит от веса, но в среднем 0.04-0.05 ккал)
CALORIES_PER_STEP = 0.045


@router.message(F.text.lower().startswith("/health"))
async def cmd_health(message: Message):
    """Обработка данных из Apple Health"""
    user_id = message.from_user.id
    text = message.text.replace("/health", "").strip().lower()

    if not text:
        await message.answer(
            "📱 **Импорт из Apple Health**\n\n"
            "Отправь данные в формате:\n"
            "`/health шаги 8500`\n"
            "`/health пульс 72`\n"
            "`/health сон 7.5`\n"
            "`/health активные_калории 450`\n\n"
            "Или настрой автоматическую отправку через Shortcuts!",
            parse_mode="Markdown"
        )
        return

    parts = text.split()
    if len(parts) < 2:
        await message.answer("❌ Формат: `/health тип значение`", parse_mode="Markdown")
        return

    data_type = parts[0]
    try:
        value = float(parts[1].replace(",", "."))
    except ValueError:
        await message.answer("❌ Значение должно быть числом")
        return

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)
            await session.flush()

        response = ""

        if data_type in ["шаги", "steps"]:
            steps = int(value)
            calories = int(steps * CALORIES_PER_STEP)

            entry = ActivityEntry(
                user_id=user_id,
                activity_type="шаги (Apple Watch)",
                duration=0,
                calories_burned=calories,
                note=f"{steps} шагов"
            )
            session.add(entry)
            response = f"👟 **{steps:,}** шагов записано!\n🔥 ~{calories} ккал сожжено"

        elif data_type in ["пульс", "heart", "hr"]:
            hr = int(value)
            # Сохраняем как заметку в последнюю запись активности или создаём новую
            response = f"❤️ Пульс: **{hr}** уд/мин"
            # Можно добавить отдельную таблицу для пульса если нужно

        elif data_type in ["сон", "sleep"]:
            hours = value
            response = f"😴 Сон: **{hours}** часов"
            if hours < 6:
                response += "\n⚠️ Маловато! Рекомендуется 7-9 часов"
            elif hours >= 7:
                response += "\n✅ Отличный сон!"

        elif data_type in ["активные_калории", "active_calories", "калории_активность"]:
            calories = int(value)
            entry = ActivityEntry(
                user_id=user_id,
                activity_type="активность (Apple Watch)",
                duration=0,
                calories_burned=calories,
                note="из Apple Health"
            )
            session.add(entry)
            response = f"🔥 **{calories}** активных калорий записано!"

        elif data_type in ["тренировка", "workout"]:
            # Формат: /health тренировка бег 30 250
            # тип, минуты, калории
            if len(parts) >= 4:
                workout_type = parts[1]
                duration = int(parts[2])
                calories = int(parts[3])
            else:
                workout_type = "тренировка"
                duration = int(value)
                calories = 0

            entry = ActivityEntry(
                user_id=user_id,
                activity_type=f"{workout_type} (Apple Watch)",
                duration=duration,
                calories_burned=calories,
                note="из Apple Health"
            )
            session.add(entry)
            response = f"🏋️ **{workout_type.capitalize()}** записана!\n⏱ {duration} мин, 🔥 {calories} ккал"

        else:
            await message.answer(
                f"❌ Неизвестный тип данных: {data_type}\n\n"
                "Доступные: шаги, пульс, сон, активные_калории, тренировка"
            )
            return

        await session.commit()

    await message.answer(response, parse_mode="Markdown")


@router.message(F.text.lower().startswith("/sync"))
async def cmd_sync(message: Message):
    """Массовый импорт данных из Apple Health"""
    user_id = message.from_user.id
    text = message.text.replace("/sync", "").strip()

    if not text:
        await message.answer(
            "📱 **Синхронизация с Apple Health**\n\n"
            "Отправь данные в формате JSON:\n"
            "```\n/sync\n"
            "шаги:8500\n"
            "калории:450\n"
            "сон:7.5\n"
            "```",
            parse_mode="Markdown"
        )
        return

    results = []
    lines = text.strip().split("\n")

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)
            await session.flush()

        for line in lines:
            if ":" not in line:
                continue

            key, val = line.split(":", 1)
            key = key.strip().lower()
            try:
                value = float(val.strip().replace(",", "."))
            except Exception:
                continue

            if key in ["шаги", "steps"]:
                steps = int(value)
                calories = int(steps * CALORIES_PER_STEP)
                entry = ActivityEntry(
                    user_id=user_id,
                    activity_type="шаги (Apple Watch)",
                    duration=0,
                    calories_burned=calories,
                    note=f"{steps} шагов"
                )
                session.add(entry)
                results.append(f"👟 {steps:,} шагов (+{calories} ккал)")

            elif key in ["калории", "active_calories"]:
                calories = int(value)
                entry = ActivityEntry(
                    user_id=user_id,
                    activity_type="активность (Apple Watch)",
                    duration=0,
                    calories_burned=calories
                )
                session.add(entry)
                results.append(f"🔥 {calories} активных ккал")

            elif key in ["сон", "sleep"]:
                results.append(f"😴 {value} ч сна")

        await session.commit()

    if results:
        await message.answer(
            "✅ **Данные синхронизированы:**\n\n" + "\n".join(results),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Не удалось распознать данные")
