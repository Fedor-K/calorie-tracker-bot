from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.db import async_session
from database.models import User
from keyboards.main import get_settings_keyboard, get_reminders_keyboard

router = Router()


class SettingsStates(StatesGroup):
    waiting_for_calories = State()
    waiting_for_water = State()
    waiting_for_target_weight = State()
    waiting_for_height = State()


@router.message(F.text == "⚙️ Настройки")
async def handle_settings_button(message: Message):
    """Кнопка настроек"""
    await show_settings(message)


@router.message(F.text.lower().startswith("/settings"))
async def cmd_settings(message: Message):
    """Команда /settings"""
    await show_settings(message)


async def show_settings(message: Message):
    """Показать настройки"""
    user_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("Сначала напиши /start")
        return

    response = (
        f"⚙️ **Настройки**\n\n"
        f"🎯 Цель калорий: **{user.calorie_goal}** ккал\n"
        f"💧 Цель воды: **{user.water_goal}** мл\n"
        f"⚖️ Целевой вес: **{user.target_weight or 'не указан'}** кг\n"
        f"📏 Рост: **{user.height or 'не указан'}** см\n\n"
        f"🔔 Напоминания:\n"
        f"  💧 Вода: {'✅' if user.remind_water else '❌'}\n"
        f"  🍽 Еда: {'✅' if user.remind_food else '❌'}\n"
        f"  ⚖️ Вес: {'✅' if user.remind_weight else '❌'}\n"
    )

    await message.answer(
        response,
        reply_markup=get_settings_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "set_calories")
async def set_calories_callback(callback: CallbackQuery, state: FSMContext):
    """Установка цели калорий"""
    await callback.message.edit_text(
        "🎯 **Цель калорий**\n\n"
        "Отправь число (например: 2000)",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_calories)
    await callback.answer()


@router.message(SettingsStates.waiting_for_calories)
async def process_calories_input(message: Message, state: FSMContext):
    """Обработка ввода калорий"""
    try:
        calories = int(message.text)
        if calories < 500 or calories > 10000:
            await message.answer("❌ Укажи значение от 500 до 10000 ккал")
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.calorie_goal = calories
                await session.commit()

        await message.answer(f"✅ Цель калорий: **{calories}** ккал", parse_mode="Markdown")
        await state.clear()

    except ValueError:
        await message.answer("❌ Отправь число")


@router.callback_query(F.data == "set_water")
async def set_water_callback(callback: CallbackQuery, state: FSMContext):
    """Установка цели воды"""
    await callback.message.edit_text(
        "💧 **Цель воды**\n\n"
        "Отправь число в мл (например: 2500)",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_water)
    await callback.answer()


@router.message(SettingsStates.waiting_for_water)
async def process_water_input(message: Message, state: FSMContext):
    """Обработка ввода воды"""
    try:
        water = int(message.text)
        if water < 500 or water > 10000:
            await message.answer("❌ Укажи значение от 500 до 10000 мл")
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.water_goal = water
                await session.commit()

        await message.answer(f"✅ Цель воды: **{water}** мл", parse_mode="Markdown")
        await state.clear()

    except ValueError:
        await message.answer("❌ Отправь число")


@router.callback_query(F.data == "set_target_weight")
async def set_target_weight_callback(callback: CallbackQuery, state: FSMContext):
    """Установка целевого веса"""
    await callback.message.edit_text(
        "⚖️ **Целевой вес**\n\n"
        "Отправь вес в кг (например: 70)",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_target_weight)
    await callback.answer()


@router.message(SettingsStates.waiting_for_target_weight)
async def process_target_weight_input(message: Message, state: FSMContext):
    """Обработка ввода целевого веса"""
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 30 or weight > 300:
            await message.answer("❌ Укажи реальный вес (30-300 кг)")
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.target_weight = weight
                await session.commit()

        await message.answer(f"✅ Целевой вес: **{weight}** кг", parse_mode="Markdown")
        await state.clear()

    except ValueError:
        await message.answer("❌ Отправь число")


@router.callback_query(F.data == "set_height")
async def set_height_callback(callback: CallbackQuery, state: FSMContext):
    """Установка роста"""
    await callback.message.edit_text(
        "📏 **Рост**\n\n"
        "Отправь рост в см (например: 175)",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_height)
    await callback.answer()


@router.message(SettingsStates.waiting_for_height)
async def process_height_input(message: Message, state: FSMContext):
    """Обработка ввода роста"""
    try:
        height = int(message.text)
        if height < 100 or height > 250:
            await message.answer("❌ Укажи реальный рост (100-250 см)")
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.height = height
                await session.commit()

        await message.answer(f"✅ Рост: **{height}** см", parse_mode="Markdown")
        await state.clear()

    except ValueError:
        await message.answer("❌ Отправь число")


@router.callback_query(F.data == "set_reminders")
async def set_reminders_callback(callback: CallbackQuery):
    """Настройки напоминаний"""
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user:
        await callback.message.edit_text(
            "🔔 **Напоминания**\n\n"
            "Нажми, чтобы включить/выключить:",
            reply_markup=get_reminders_keyboard(user),
            parse_mode="Markdown"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_"))
async def toggle_reminder(callback: CallbackQuery):
    """Переключение напоминаний"""
    user_id = callback.from_user.id
    reminder_type = callback.data.replace("toggle_", "").replace("_reminder", "")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            if reminder_type == "water":
                user.remind_water = not user.remind_water
            elif reminder_type == "food":
                user.remind_food = not user.remind_food
            elif reminder_type == "weight":
                user.remind_weight = not user.remind_weight

            await session.commit()

            await callback.message.edit_reply_markup(
                reply_markup=get_reminders_keyboard(user)
            )

    await callback.answer("Настройки обновлены")


@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: CallbackQuery):
    """Назад к настройкам"""
    await callback.message.edit_text(
        "⚙️ Выбери настройку:",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "close_settings")
async def close_settings(callback: CallbackQuery):
    """Закрыть настройки"""
    await callback.message.delete()
    await callback.answer()
