from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, ActivityEntry
from services.ai import estimate_activity_calories

router = Router()


class ActivityStates(StatesGroup):
    waiting_for_activity = State()


@router.message(F.text == "🏃 Активность")
async def handle_activity_button(message: Message, state: FSMContext):
    """Кнопка активности"""
    user_id = message.from_user.id

    # Получаем статистику за сегодня
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session() as session:
        result = await session.execute(
            select(
                func.sum(ActivityEntry.duration),
                func.sum(ActivityEntry.calories_burned)
            )
            .where(ActivityEntry.user_id == user_id)
            .where(ActivityEntry.created_at >= today_start)
        )
        total_duration, total_calories = result.one()

        # Последние активности
        entries_result = await session.execute(
            select(ActivityEntry)
            .where(ActivityEntry.user_id == user_id)
            .order_by(ActivityEntry.created_at.desc())
            .limit(5)
        )
        entries = entries_result.scalars().all()

    response = "🏃 **Активность**\n\n"

    if total_duration:
        response += f"Сегодня: {total_duration} мин, ~{total_calories or 0} ккал\n\n"

    if entries:
        response += "📊 Последние записи:\n"
        for e in entries:
            response += f"  • {e.activity_type}: {e.duration} мин ({e.calories_burned} ккал)\n"
        response += "\n"

    response += (
        "Добавить активность:\n"
        "`/activity бег 30`\n"
        "или просто напиши: `тренировка 45`"
    )

    await message.answer(response, parse_mode="Markdown")
    await state.set_state(ActivityStates.waiting_for_activity)


@router.message(F.text.lower().startswith("/activity"))
async def cmd_activity(message: Message):
    """Команда /activity [тип] [минуты]"""
    text = message.text.replace("/activity", "").strip()
    await process_activity(message, text)


@router.message(ActivityStates.waiting_for_activity)
async def process_activity_input(message: Message, state: FSMContext):
    """Обработка ввода активности"""
    # Пропускаем, если это команда или кнопка меню
    if message.text.startswith("/") or message.text in [
        "📊 Статистика", "💧 Вода", "⚖️ Вес", "🏃 Активность",
        "🍽 План питания", "⚙️ Настройки"
    ]:
        await state.clear()
        return

    await process_activity(message, message.text)
    await state.clear()


async def process_activity(message: Message, text: str):
    """Обработка и сохранение активности"""
    if not text:
        await message.answer(
            "🏃 Укажи активность и время:\n"
            "Пример: `/activity бег 30`",
            parse_mode="Markdown"
        )
        return

    # Парсим текст
    parts = text.strip().split()

    # Ищем число (минуты)
    duration = None
    activity_parts = []

    for part in parts:
        try:
            num = int(part)
            if 1 <= num <= 1000:
                duration = num
        except ValueError:
            activity_parts.append(part)

    if not duration:
        await message.answer(
            "❌ Укажи длительность в минутах.\n"
            "Пример: `бег 30`",
            parse_mode="Markdown"
        )
        return

    activity_type = " ".join(activity_parts) if activity_parts else "тренировка"

    # Показываем что обрабатываем
    processing_msg = await message.answer("🔄 Рассчитываю калории...")

    try:
        user_id = message.from_user.id

        # Получаем вес пользователя для расчёта
        async with async_session() as session:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            weight = user.current_weight if user and user.current_weight else 70

        # Оцениваем калории через AI
        result = await estimate_activity_calories(activity_type, duration, weight)
        calories = result.get("calories_burned", 0)

        # Сохраняем в базу
        async with async_session() as session:
            if not user:
                user = User(id=user_id)
                session.add(user)
                await session.flush()

            entry = ActivityEntry(
                user_id=user_id,
                activity_type=activity_type,
                duration=duration,
                calories_burned=calories
            )
            session.add(entry)
            await session.commit()

        await processing_msg.delete()

        intensity_emoji = {
            "low": "🚶",
            "medium": "🏃",
            "high": "🔥"
        }.get(result.get("intensity", "medium"), "🏃")

        await message.answer(
            f"{intensity_emoji} **{activity_type.capitalize()}**\n\n"
            f"⏱ Длительность: {duration} мин\n"
            f"🔥 Сожжено: ~{calories} ккал\n"
            + (f"\n💡 {result.get('notes', '')}" if result.get('notes') else ""),
            parse_mode="Markdown"
        )

    except Exception as e:
        await processing_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
