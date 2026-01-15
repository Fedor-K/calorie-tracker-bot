from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from sqlalchemy import select

from database.db import async_session
from database.models import User
from keyboards.main import get_main_keyboard
import config

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка команды /start"""
    user_id = message.from_user.id

    async with async_session() as session:
        # Проверяем, есть ли пользователь
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            # Создаём нового пользователя
            user = User(
                id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                calorie_goal=config.DEFAULT_CALORIE_GOAL,
                water_goal=config.DEFAULT_WATER_GOAL
            )
            session.add(user)
            await session.commit()

            await message.answer(
                f"Привет, {message.from_user.first_name}! 👋\n\n"
                "Я — твой персональный трекер калорий и здоровья.\n\n"
                "🍎 **Что я умею:**\n"
                "• Анализировать фото еды и считать калории\n"
                "• Отслеживать вес, воду и активность\n"
                "• Составлять план питания\n"
                "• Напоминать о еде и воде\n\n"
                "📸 **Просто отправь фото еды** — и я посчитаю калории!\n\n"
                "Используй кнопки меню или команды:\n"
                "/stats — статистика за день\n"
                "/weight 75.5 — записать вес\n"
                "/water 250 — добавить воду\n"
                "/activity бег 30 — записать активность\n"
                "/plan — получить план питания\n"
                "/settings — настройки",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                f"С возвращением, {message.from_user.first_name}! 💪\n\n"
                "Отправь фото еды для анализа или используй меню.",
                reply_markup=get_main_keyboard()
            )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка по командам"""
    await message.answer(
        "📖 **Справка по командам:**\n\n"
        "🍽 **Еда:**\n"
        "• Отправь фото — анализ калорий\n\n"
        "💧 **Вода:**\n"
        "• /water 250 — добавить воду (мл)\n"
        "• Кнопка «Вода» — быстрое добавление\n\n"
        "⚖️ **Вес:**\n"
        "• /weight 75.5 — записать вес (кг)\n\n"
        "🏃 **Активность:**\n"
        "• /activity бег 30 — тип и минуты\n\n"
        "📊 **Статистика:**\n"
        "• /stats — сводка за день\n"
        "• /week — за неделю\n\n"
        "🍽 **План питания:**\n"
        "• /plan — сгенерировать план на день\n\n"
        "⚙️ **Настройки:**\n"
        "• /settings — цели и напоминания",
        parse_mode="Markdown"
    )
