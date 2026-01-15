"""
Онбординг новых пользователей
Пошаговый сбор информации при первом запуске
"""
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.db import async_session
from database.models import User
from keyboards.main import get_main_keyboard

router = Router()


class OnboardingStates(StatesGroup):
    """Состояния онбординга"""
    waiting_name = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_height = State()
    waiting_weight = State()
    waiting_target_weight = State()
    waiting_goal = State()
    waiting_activity_level = State()
    waiting_calorie_goal = State()


def get_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")
        ]
    ])


def get_goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Похудеть", callback_data="goal_lose")],
        [InlineKeyboardButton(text="💪 Набрать массу", callback_data="goal_gain")],
        [InlineKeyboardButton(text="⚖️ Поддерживать вес", callback_data="goal_maintain")],
        [InlineKeyboardButton(text="🏃 Просто следить за здоровьем", callback_data="goal_health")]
    ])


def get_activity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛋 Сидячий образ жизни", callback_data="activity_sedentary")],
        [InlineKeyboardButton(text="🚶 Лёгкая активность (1-2 раза/нед)", callback_data="activity_light")],
        [InlineKeyboardButton(text="🏃 Умеренная (3-4 раза/нед)", callback_data="activity_moderate")],
        [InlineKeyboardButton(text="🏋️ Высокая (5-6 раз/нед)", callback_data="activity_high")],
        [InlineKeyboardButton(text="🔥 Очень высокая (каждый день)", callback_data="activity_extreme")]
    ])


def get_calorie_keyboard(recommended: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ {recommended} ккал (рекомендуется)", callback_data=f"calories_{recommended}")],
        [InlineKeyboardButton(text=f"📉 {recommended - 300} ккал (для похудения)", callback_data=f"calories_{recommended - 300}")],
        [InlineKeyboardButton(text=f"📈 {recommended + 300} ккал (для набора)", callback_data=f"calories_{recommended + 300}")],
        [InlineKeyboardButton(text="✏️ Ввести своё значение", callback_data="calories_custom")]
    ])


def calculate_bmr(weight: float, height: int, age: int, gender: str) -> int:
    """Расчёт базового метаболизма по формуле Миффлина-Сан Жеора"""
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    return int(bmr)


def calculate_tdee(bmr: int, activity_level: str) -> int:
    """Расчёт суточной нормы калорий с учётом активности"""
    multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "high": 1.725,
        "extreme": 1.9
    }
    return int(bmr * multipliers.get(activity_level, 1.2))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    user_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user and user.height:  # Пользователь уже прошёл онбординг
            await message.answer(
                f"С возвращением, {user.first_name or message.from_user.first_name}! 💪\n\n"
                f"📊 Твои цели:\n"
                f"🔥 Калории: {user.calorie_goal} ккал\n"
                f"💧 Вода: {user.water_goal} мл\n"
                f"⚖️ Текущий вес: {user.current_weight or '—'} кг\n\n"
                f"Отправь фото еды для анализа или используй меню!",
                reply_markup=get_main_keyboard()
            )
            return

    # Новый пользователь - начинаем онбординг
    await state.clear()

    await message.answer(
        "👋 **Привет! Я твой персональный трекер здоровья.**\n\n"
        "Я помогу тебе:\n"
        "• 📸 Считать калории по фото еды\n"
        "• ⚖️ Отслеживать вес\n"
        "• 💧 Следить за водным балансом\n"
        "• 🏃 Учитывать активность\n"
        "• ⌚ Синхронизироваться с WHOOP/Apple Watch\n\n"
        "Давай настроим бота под тебя!\n"
        "Это займёт пару минут 🚀",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "**Как тебя зовут?**\n\n"
        "Напиши своё имя:",
        parse_mode="Markdown"
    )
    await state.set_state(OnboardingStates.waiting_name)


@router.message(OnboardingStates.waiting_name)
async def process_name(message: Message, state: FSMContext):
    """Обработка имени"""
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Введи корректное имя (2-50 символов)")
        return

    await state.update_data(name=name)
    await message.answer(
        f"Приятно познакомиться, **{name}**! 👋\n\n"
        f"Укажи свой пол:",
        parse_mode="Markdown",
        reply_markup=get_gender_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_gender)


@router.callback_query(OnboardingStates.waiting_gender, F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка пола"""
    gender = callback.data.replace("gender_", "")
    await state.update_data(gender=gender)

    await callback.message.edit_text(
        "📅 **Сколько тебе лет?**\n\n"
        "Напиши свой возраст:",
        parse_mode="Markdown"
    )
    await state.set_state(OnboardingStates.waiting_age)
    await callback.answer()


@router.message(OnboardingStates.waiting_age)
async def process_age(message: Message, state: FSMContext):
    """Обработка возраста"""
    try:
        age = int(message.text)
        if age < 10 or age > 120:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный возраст (10-120)")
        return

    await state.update_data(age=age)
    await message.answer(
        "📏 **Какой у тебя рост?**\n\n"
        "Напиши в сантиметрах (например: 175):",
        parse_mode="Markdown"
    )
    await state.set_state(OnboardingStates.waiting_height)


@router.message(OnboardingStates.waiting_height)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    try:
        height = int(message.text)
        if height < 100 or height > 250:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный рост (100-250 см)")
        return

    await state.update_data(height=height)
    await message.answer(
        "⚖️ **Какой у тебя текущий вес?**\n\n"
        "Напиши в килограммах (например: 75.5):",
        parse_mode="Markdown"
    )
    await state.set_state(OnboardingStates.waiting_weight)


@router.message(OnboardingStates.waiting_weight)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 30 or weight > 300:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный вес (30-300 кг)")
        return

    await state.update_data(weight=weight)
    await message.answer(
        "🎯 **Какой у тебя целевой вес?**\n\n"
        "Напиши желаемый вес в кг\n"
        "или отправь 0 если хочешь просто поддерживать текущий:",
        parse_mode="Markdown"
    )
    await state.set_state(OnboardingStates.waiting_target_weight)


@router.message(OnboardingStates.waiting_target_weight)
async def process_target_weight(message: Message, state: FSMContext):
    """Обработка целевого веса"""
    try:
        target = float(message.text.replace(",", "."))
        if target != 0 and (target < 30 or target > 300):
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный вес (30-300 кг) или 0")
        return

    data = await state.get_data()
    if target == 0:
        target = data["weight"]

    await state.update_data(target_weight=target)
    await message.answer(
        "🎯 **Какая у тебя главная цель?**",
        parse_mode="Markdown",
        reply_markup=get_goal_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_goal)


@router.callback_query(OnboardingStates.waiting_goal, F.data.startswith("goal_"))
async def process_goal(callback: CallbackQuery, state: FSMContext):
    """Обработка цели"""
    goal = callback.data.replace("goal_", "")
    await state.update_data(goal=goal)

    await callback.message.edit_text(
        "🏃 **Какой у тебя уровень физической активности?**",
        parse_mode="Markdown",
        reply_markup=get_activity_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_activity_level)
    await callback.answer()


@router.callback_query(OnboardingStates.waiting_activity_level, F.data.startswith("activity_"))
async def process_activity(callback: CallbackQuery, state: FSMContext):
    """Обработка уровня активности и расчёт калорий"""
    activity = callback.data.replace("activity_", "")
    await state.update_data(activity_level=activity)

    data = await state.get_data()

    # Рассчитываем рекомендуемые калории
    bmr = calculate_bmr(data["weight"], data["height"], data["age"], data["gender"])
    tdee = calculate_tdee(bmr, activity)

    # Корректируем под цель
    goal = data.get("goal", "maintain")
    if goal == "lose":
        recommended = tdee - 500  # Дефицит для похудения
    elif goal == "gain":
        recommended = tdee + 300  # Профицит для набора
    else:
        recommended = tdee

    await state.update_data(recommended_calories=recommended)

    await callback.message.edit_text(
        f"📊 **Расчёт твоей нормы калорий:**\n\n"
        f"🔥 Базовый метаболизм: {bmr} ккал\n"
        f"📈 С учётом активности: {tdee} ккал\n\n"
        f"Рекомендуемая норма для твоей цели:\n"
        f"**{recommended} ккал/день**\n\n"
        f"Выбери или введи своё значение:",
        parse_mode="Markdown",
        reply_markup=get_calorie_keyboard(recommended)
    )
    await state.set_state(OnboardingStates.waiting_calorie_goal)
    await callback.answer()


@router.callback_query(OnboardingStates.waiting_calorie_goal, F.data.startswith("calories_"))
async def process_calorie_choice(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора калорий"""
    choice = callback.data.replace("calories_", "")

    if choice == "custom":
        await callback.message.edit_text(
            "✏️ **Введи свою цель по калориям:**\n\n"
            "Напиши число (например: 1800):",
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    calorie_goal = int(choice)
    await finish_onboarding(callback.message, state, calorie_goal, callback.from_user.id)
    await callback.answer()


@router.message(OnboardingStates.waiting_calorie_goal)
async def process_custom_calories(message: Message, state: FSMContext):
    """Обработка ручного ввода калорий"""
    try:
        calorie_goal = int(message.text)
        if calorie_goal < 800 or calorie_goal > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректное значение (800-10000 ккал)")
        return

    await finish_onboarding(message, state, calorie_goal, message.from_user.id)


async def finish_onboarding(message: Message, state: FSMContext, calorie_goal: int, user_id: int):
    """Завершение онбординга и сохранение данных"""
    data = await state.get_data()

    # Рассчитываем норму воды (30-35 мл на кг веса)
    water_goal = int(data["weight"] * 33)
    water_goal = (water_goal // 100) * 100  # Округляем до 100

    # Рассчитываем норму белка
    protein_goal = int(data["weight"] * 1.6)  # 1.6г на кг для активных

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)

        user.first_name = data["name"]
        user.height = data["height"]
        user.current_weight = data["weight"]
        user.target_weight = data.get("target_weight", data["weight"])
        user.calorie_goal = calorie_goal
        user.water_goal = water_goal
        user.protein_goal = protein_goal

        await session.commit()

    await state.clear()

    # Определяем цель текстом
    goal_text = {
        "lose": "похудение",
        "gain": "набор массы",
        "maintain": "поддержание веса",
        "health": "здоровый образ жизни"
    }.get(data.get("goal", "health"), "здоровье")

    await message.answer(
        f"🎉 **Отлично, {data['name']}! Всё настроено!**\n\n"
        f"📊 **Твой профиль:**\n"
        f"├ Рост: {data['height']} см\n"
        f"├ Вес: {data['weight']} кг\n"
        f"├ Цель: {goal_text}\n"
        f"└ Целевой вес: {data.get('target_weight', data['weight'])} кг\n\n"
        f"🎯 **Дневные нормы:**\n"
        f"├ 🔥 Калории: {calorie_goal} ккал\n"
        f"├ 💧 Вода: {water_goal} мл\n"
        f"└ 🥩 Белок: {protein_goal} г\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📸 **Отправь фото еды** — я посчитаю калории!\n\n"
        f"Или подключи трекер:\n"
        f"/whoop — подключить WHOOP\n"
        f"/health — импорт из Apple Health",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
