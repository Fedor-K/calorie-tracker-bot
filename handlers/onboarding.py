"""
Онбординг новых пользователей
Пошаговый сбор информации при первом запуске
"""
import logging
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

logger = logging.getLogger(__name__)
router = Router()


class OnboardingStates(StatesGroup):
    """Состояния онбординга"""
    waiting_name = State()
    waiting_country = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_height = State()
    waiting_weight = State()
    waiting_target_weight = State()
    waiting_goal = State()
    waiting_activity_level = State()
    waiting_calorie_goal = State()


# Страны с часовыми поясами
COUNTRIES = {
    "ru": ("🇷🇺 Россия", "Europe/Moscow"),
    "by": ("🇧🇾 Беларусь", "Europe/Minsk"),
    "kz": ("🇰🇿 Казахстан", "Asia/Almaty"),
    "uz": ("🇺🇿 Узбекистан", "Asia/Tashkent"),
    "ge": ("🇬🇪 Грузия", "Asia/Tbilisi"),
    "az": ("🇦🇿 Азербайджан", "Asia/Baku"),
    "am": ("🇦🇲 Армения", "Asia/Yerevan"),
    "md": ("🇲🇩 Молдова", "Europe/Chisinau"),
    "de": ("🇩🇪 Германия", "Europe/Berlin"),
    "us": ("🇺🇸 США", "America/New_York"),
    "other": ("🌍 Другая", "UTC"),
}


def get_country_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for code, (name, _) in COUNTRIES.items():
        row.append(InlineKeyboardButton(text=name, callback_data=f"country_{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


def calculate_ideal_weight(height: int, gender: str, age: int) -> tuple[float, float, float]:
    """
    Расчёт идеального веса по нескольким формулам
    Возвращает: (идеальный, минимум нормы, максимум нормы)
    """
    height_m = height / 100

    # По ИМТ (норма 18.5-24.9, идеал ~22)
    ideal_bmi = 22 if gender == "male" else 21.5
    ideal = ideal_bmi * (height_m ** 2)

    # Диапазон нормы по ИМТ
    min_normal = 18.5 * (height_m ** 2)
    max_normal = 24.9 * (height_m ** 2)

    # Корректировка по возрасту (после 40 лет +0.5-1 кг за каждые 10 лет)
    if age > 40:
        age_adjustment = (age - 40) / 10 * 0.7
        ideal += age_adjustment
        max_normal += age_adjustment

    return round(ideal, 1), round(min_normal, 1), round(max_normal, 1)


def get_target_weight_keyboard(current: float, ideal: float, min_w: float, max_w: float) -> InlineKeyboardMarkup:
    """Клавиатура выбора целевого веса"""
    buttons = []

    # Если текущий вес сильно выше идеального - показываем реалистичные цели
    if current > ideal + 10:
        # Первая цель: -10% от текущего веса (реалистично)
        first_target = round(current * 0.9, 1)
        buttons.append([InlineKeyboardButton(
            text=f"🎯 {first_target} кг (первая цель: -10%)",
            callback_data=f"target_{first_target}"
        )])

        # Вторая цель: -20% от текущего
        second_target = round(current * 0.8, 1)
        buttons.append([InlineKeyboardButton(
            text=f"💪 {second_target} кг (цель: -20%)",
            callback_data=f"target_{second_target}"
        )])

        # Максимум нормы (верхняя граница здорового ИМТ)
        if max_w < current * 0.8:
            buttons.append([InlineKeyboardButton(
                text=f"✨ {max_w} кг (верхняя граница нормы)",
                callback_data=f"target_{max_w}"
            )])
    elif current > ideal + 5:
        # Умеренный лишний вес - показываем идеал и промежуточную цель
        mid_target = round((current + ideal) / 2, 1)
        buttons.append([InlineKeyboardButton(
            text=f"🎯 {mid_target} кг (промежуточная цель)",
            callback_data=f"target_{mid_target}"
        )])
        buttons.append([InlineKeyboardButton(
            text=f"✨ {ideal} кг (идеальный вес)",
            callback_data=f"target_{ideal}"
        )])
    elif current < ideal - 3:
        # Недовес - предлагаем набрать
        buttons.append([InlineKeyboardButton(
            text=f"💪 {ideal} кг (набрать до идеала)",
            callback_data=f"target_{ideal}"
        )])
    else:
        # Вес близок к идеальному
        buttons.append([InlineKeyboardButton(
            text=f"✨ {ideal} кг (идеальный вес)",
            callback_data=f"target_{ideal}"
        )])

    # Оставить текущий
    buttons.append([InlineKeyboardButton(
        text=f"⚖️ {current} кг (поддерживать текущий)",
        callback_data=f"target_{current}"
    )])

    # Своё значение
    buttons.append([InlineKeyboardButton(
        text="✏️ Ввести своё значение",
        callback_data="target_custom"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
                f"Пиши что съел, отправляй фото или задавай вопросы — я помогу! 🤖",
                reply_markup=get_main_keyboard()
            )
            return

    # Новый пользователь - начинаем онбординг
    await state.clear()

    await message.answer(
        "👋 **Привет! Я твой персональный AI-коуч по здоровью.**\n\n"
        "Я помогу тебе:\n"
        "• 💬 Просто пиши что съел — я посчитаю калории\n"
        "• 📸 Отправляй фото еды — распознаю и запишу\n"
        "• 💧 Отслеживать воду, вес, активность\n"
        "• 🧠 Отвечу на любые вопросы о питании\n"
        "• 📝 Запомню твои предпочтения и ограничения\n\n"
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
    logger.info(f"[ONBOARDING] process_name: user={message.from_user.id}, name={name}")

    if len(name) < 2 or len(name) > 50:
        await message.answer("Введи корректное имя (2-50 символов)")
        return

    await state.update_data(name=name)

    logger.info(f"[ONBOARDING] Showing country keyboard for user={message.from_user.id}")
    await message.answer(
        f"Приятно познакомиться, **{name}**! 👋\n\n"
        f"🌍 В какой стране ты живёшь?\n"
        f"_Это нужно для рекомендаций по питанию и магазинам_",
        parse_mode="Markdown",
        reply_markup=get_country_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_country)
    logger.info(f"[ONBOARDING] State set to waiting_country for user={message.from_user.id}")


@router.callback_query(OnboardingStates.waiting_country, F.data.startswith("country_"))
async def process_country(callback: CallbackQuery, state: FSMContext):
    """Обработка страны"""
    country_code = callback.data.replace("country_", "")
    country_name, timezone = COUNTRIES.get(country_code, ("Другая", "UTC"))

    await state.update_data(country=country_name.split(" ", 1)[1], timezone=timezone)

    await callback.message.edit_text(
        "Укажи свой пол:",
        reply_markup=get_gender_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_gender)
    await callback.answer()


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

    # Получаем данные для расчёта идеального веса
    data = await state.get_data()
    height = data["height"]
    age = data["age"]
    gender = data["gender"]

    # Рассчитываем идеальный вес
    ideal, min_normal, max_normal = calculate_ideal_weight(height, gender, age)

    # Определяем статус текущего веса
    if weight < min_normal:
        status = "ниже нормы"
        emoji = "⚠️"
    elif weight > max_normal:
        status = "выше нормы"
        emoji = "⚠️"
    else:
        status = "в норме"
        emoji = "✅"

    # Разница с идеалом
    diff = weight - ideal
    if diff > 0:
        diff_text = f"на {abs(diff):.1f} кг выше идеального"
    elif diff < 0:
        diff_text = f"на {abs(diff):.1f} кг ниже идеального"
    else:
        diff_text = "идеальный вес!"

    await message.answer(
        f"📊 **Анализ твоего веса:**\n\n"
        f"Твой вес: **{weight} кг** {emoji} ({status})\n"
        f"Идеальный вес для тебя: **{ideal} кг**\n"
        f"Нормальный диапазон: {min_normal}–{max_normal} кг\n\n"
        f"📍 Ты {diff_text}\n\n"
        f"🎯 **Выбери целевой вес:**",
        parse_mode="Markdown",
        reply_markup=get_target_weight_keyboard(weight, ideal, min_normal, max_normal)
    )
    await state.set_state(OnboardingStates.waiting_target_weight)


@router.callback_query(OnboardingStates.waiting_target_weight, F.data.startswith("target_"))
async def process_target_choice(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора целевого веса по кнопке"""
    choice = callback.data.replace("target_", "")

    if choice == "custom":
        await callback.message.edit_text(
            "✏️ **Введи свой целевой вес:**\n\n"
            "Напиши в килограммах (например: 65.5):",
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    target = float(choice)
    await state.update_data(target_weight=target)

    await callback.message.edit_text(
        "🎯 **Какая у тебя главная цель?**",
        parse_mode="Markdown",
        reply_markup=get_goal_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_goal)
    await callback.answer()


@router.message(OnboardingStates.waiting_target_weight)
async def process_target_weight(message: Message, state: FSMContext):
    """Обработка ручного ввода целевого веса"""
    try:
        target = float(message.text.replace(",", "."))
        if target < 30 or target > 300:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный вес (30-300 кг)")
        return

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
        user.country = data.get("country", "Россия")
        user.timezone = data.get("timezone", "Europe/Moscow")
        user.height = data["height"]
        user.current_weight = data["weight"]
        user.target_weight = data.get("target_weight", data["weight"])
        user.age = data.get("age")
        user.gender = data.get("gender")
        user.goal = data.get("goal", "health")
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
        f"💡 **Моя философия:**\n"
        f"Не диеты и сила воли, а маленькие шаги и новые привычки. "
        f"Я помогу заменить вредное на полезное так, чтобы вес ушёл навсегда.\n\n"
        f"Теперь можешь:\n"
        f"• Писать что съел — запишу и подскажу альтернативы\n"
        f"• Отправлять фото еды — распознаю и дам советы\n"
        f"• Спрашивать что угодно про питание\n\n"
        f"Начнём? 🚀",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
