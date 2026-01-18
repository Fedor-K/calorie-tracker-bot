"""
Chat Handler - Главный обработчик текстовых сообщений
Все текстовые сообщения идут через AI коуча
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Filter
from sqlalchemy import select

from database.db import async_session
from database.models import User
from services.coach import handle_message, get_user_context
from services.ai import generate_meal_plan
from services.memory import get_memories
from keyboards.main import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()

# Кнопки меню, которые обрабатываются отдельно
MENU_BUTTONS = {
    "📊 статистика",
    "💧 вода",
    "💧+250мл",
    "⚙️ настройки"
}


class ChatTextFilter(Filter):
    """Фильтр для текстовых сообщений, идущих в AI"""
    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        text = message.text.strip()
        # Пропускаем команды
        if text.startswith("/"):
            return False
        # Пропускаем кнопки меню
        if text.lower() in MENU_BUTTONS:
            return False
        return True


@router.message(F.text == "🍽 План питания")
async def handle_meal_plan_button(message: Message):
    """Кнопка плана питания"""
    user_id = message.from_user.id

    processing_msg = await message.answer("🍽 Составляю план питания...")

    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            calorie_goal = user.calorie_goal if user else 2000

        # Получаем ограничения из памяти
        memories = await get_memories(user_id, category="restriction")
        restrictions = ", ".join([m["content"] for m in memories]) if memories else None

        # Получаем предпочтения
        preferences_mem = await get_memories(user_id, category="preference")
        preferences = ", ".join([m["content"] for m in preferences_mem]) if preferences_mem else None

        plan = await generate_meal_plan(calorie_goal, preferences, restrictions)

        await processing_msg.delete()
        await message.answer(
            f"🍽 **План питания на день**\n"
            f"🎯 Цель: {calorie_goal} ккал\n\n"
            f"{plan}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"[PLAN] Error: {e}")
        await processing_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


@router.message(F.text.lower().startswith("/plan"))
async def cmd_plan(message: Message):
    """Команда /plan"""
    await handle_meal_plan_button(message)


@router.message(F.text.lower().startswith("/help"))
async def cmd_help(message: Message):
    """Команда /help"""
    await message.answer(
        "🤖 **AI Коуч по здоровью**\n\n"
        "Просто пиши мне что угодно:\n"
        "• Что ты съел — запишу калории\n"
        "• Что выпил — запишу воду\n"
        "• Свой вес — запишу в историю\n"
        "• Про тренировку — запишу активность\n"
        "• Любой вопрос о питании и здоровье\n\n"
        "📸 **Фото еды** — анализ калорий и БЖУ\n\n"
        "**Кнопки:**\n"
        "📊 Статистика — прогресс за день\n"
        "💧 Вода — быстро добавить воду\n"
        "🍽 План питания — меню на день\n"
        "⚙️ Настройки — изменить цели\n\n"
        "**Команды:**\n"
        "/stats — статистика за сегодня\n"
        "/stats 1 — статистика за вчера\n"
        "/history — история за неделю\n"
        "/plan — план питания\n"
        "/weight 75.5 — записать вес\n"
        "/water 250 — записать воду\n\n"
        "💡 Я запоминаю твои предпочтения и ограничения!",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


@router.message(ChatTextFilter())
async def handle_text_message(message: Message, state: FSMContext):
    """
    Главный обработчик текстовых сообщений
    Все сообщения идут через AI коуча
    """
    text = message.text.strip()
    user_id = message.from_user.id

    logger.info(f"[CHAT] user={user_id} | message: {text[:100]}")

    # Проверяем состояние FSM
    current_state = await state.get_state()
    if current_state is not None:
        # Если пользователь в состоянии настроек и отправляет не число - сбрасываем состояние
        if "Settings" in current_state or "waiting" in current_state.lower():
            # Пробуем понять, это ввод числа или обычное сообщение
            is_number_input = text.replace(",", ".").replace("-", "").replace(".", "", 1).isdigit()
            if not is_number_input:
                logger.info(f"[CHAT] user={user_id} | Clearing stuck settings state: {current_state}")
                await state.clear()
                # Продолжаем обработку как обычного сообщения
            else:
                # Это похоже на ввод числа - пусть обрабатывает settings handler
                logger.info(f"[CHAT] user={user_id} | Skip: number input in state {current_state}")
                return
        else:
            # Другие состояния (онбординг и т.д.) - пропускаем
            logger.info(f"[CHAT] user={user_id} | Skip: user in state {current_state}")
            return

    # Проверяем существование пользователя
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        # Если пользователь новый — создаём запись
        if not user:
            user = User(
                id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            session.add(user)
            await session.commit()

    # Отправляем индикатор обработки
    processing_msg = await message.answer("💭 Думаю...")

    try:
        # Обрабатываем через AI коуча
        response = await handle_message(user_id, text)

        # Удаляем индикатор и отправляем ответ
        await processing_msg.delete()
        await message.answer(
            response,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"[CHAT] user={user_id} | Error: {e}")
        try:
            await processing_msg.edit_text(
                f"❌ Произошла ошибка. Попробуй ещё раз.\n\n"
                f"Если ошибка повторяется, напиши /help"
            )
        except Exception:
            await message.answer(
                f"❌ Произошла ошибка. Попробуй ещё раз."
            )
