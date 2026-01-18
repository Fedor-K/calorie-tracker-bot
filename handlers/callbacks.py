"""
Callbacks Handler - Обработка всех callback_query
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, WaterEntry
from keyboards.main import (
    get_water_keyboard, get_settings_keyboard,
    get_reminders_keyboard
)
from handlers.settings import SettingsStates

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# Вода
# ============================================================================

async def add_water(user_id: int, amount: int) -> tuple[int, int]:
    """Добавить воду и вернуть (всего сегодня, цель)"""
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)
            await session.flush()

        entry = WaterEntry(user_id=user_id, amount=amount)
        session.add(entry)
        await session.commit()

        # Получаем начало дня
        try:
            tz = ZoneInfo(user.timezone or "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # Считаем общее количество
        total_result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )
        total = total_result.scalar_one() or 0

        return total, user.water_goal


@router.callback_query(F.data.startswith("water_"))
async def handle_water_callback(callback: CallbackQuery):
    """Обработка нажатий на кнопки воды"""
    user_id = callback.from_user.id
    amount = int(callback.data.split("_")[1])

    total, goal = await add_water(user_id, amount)
    progress = min(100, int(total / goal * 100))
    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

    achievement = ""
    if total >= goal and (total - amount) < goal:
        achievement = "\n\n🎉 **Цель достигнута!**"

    await callback.message.edit_text(
        f"💧 +{amount} мл добавлено!\n\n"
        f"Всего: **{total}** / {goal} мл\n"
        f"[{bar}] {progress}%{achievement}\n\n"
        f"Добавить ещё:",
        reply_markup=get_water_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer(f"+{amount} мл")


@router.callback_query(F.data.startswith("remind_water_"))
async def handle_remind_water_callback(callback: CallbackQuery):
    """Обработка кнопок из напоминания о воде"""
    user_id = callback.from_user.id
    action = callback.data.replace("remind_water_", "")

    if action == "later":
        await callback.message.edit_text(
            "⏰ Хорошо, напомню позже!\n\n"
            "Не забывай пить воду 💧"
        )
        await callback.answer("Напомню позже")
        return

    amount = int(action)
    total, goal = await add_water(user_id, amount)
    progress = min(100, int(total / goal * 100))
    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

    achievement = ""
    if total >= goal and (total - amount) < goal:
        achievement = "\n\n🎉 **Цель по воде достигнута!**"

    await callback.message.edit_text(
        f"✅ Отлично! +{amount} мл записано\n\n"
        f"💧 Всего: **{total}** / {goal} мл\n"
        f"[{bar}] {progress}%{achievement}",
        parse_mode="Markdown"
    )
    await callback.answer(f"+{amount} мл 👍")


# ============================================================================
# Сон
# ============================================================================

@router.callback_query(F.data.startswith("sleep_"))
async def handle_sleep_callback(callback: CallbackQuery):
    """Обработка кнопок из напоминания о сне"""
    action = callback.data.replace("sleep_", "")

    if action == "going":
        await callback.message.edit_text(
            "😴 **Спокойной ночи!**\n\n"
            "Хорошего отдыха! Увидимся завтра 🌅",
            parse_mode="Markdown"
        )
        await callback.answer("Спокойной ночи! 🌙")
    elif action == "later":
        await callback.message.edit_text(
            "⏰ Хорошо, ещё 30 минут!\n\n"
            "Но не засиживайся допоздна 😉\n"
            "Здоровый сон = здоровое тело 💪",
            parse_mode="Markdown"
        )
        await callback.answer("Не забудь лечь спать!")


# ============================================================================
# Настройки
# ============================================================================

@router.callback_query(F.data == "set_calories")
async def set_calories_callback(callback: CallbackQuery, state: FSMContext):
    """Начать изменение цели калорий"""
    await callback.message.edit_text(
        "🎯 **Цель по калориям**\n\n"
        "Введи новое значение (800-10000 ккал):",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_calories)
    await callback.answer()


@router.callback_query(F.data == "set_water")
async def set_water_callback(callback: CallbackQuery, state: FSMContext):
    """Начать изменение цели воды"""
    await callback.message.edit_text(
        "💧 **Цель по воде**\n\n"
        "Введи новое значение (500-5000 мл):",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_water)
    await callback.answer()


@router.callback_query(F.data == "set_target_weight")
async def set_target_weight_callback(callback: CallbackQuery, state: FSMContext):
    """Начать изменение целевого веса"""
    await callback.message.edit_text(
        "⚖️ **Целевой вес**\n\n"
        "Введи новое значение (30-300 кг):",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_target_weight)
    await callback.answer()


@router.callback_query(F.data == "set_height")
async def set_height_callback(callback: CallbackQuery, state: FSMContext):
    """Начать изменение роста"""
    await callback.message.edit_text(
        "📏 **Рост**\n\n"
        "Введи новое значение (100-250 см):",
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_for_height)
    await callback.answer()


@router.callback_query(F.data == "set_reminders")
async def set_reminders_callback(callback: CallbackQuery):
    """Показать настройки напоминаний"""
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user:
        await callback.message.edit_text(
            "🔔 **Настройки напоминаний**\n\n"
            "Включи/выключи нужные напоминания:",
            reply_markup=get_reminders_keyboard(user),
            parse_mode="Markdown"
        )
    await callback.answer()


@router.callback_query(F.data == "toggle_water_reminder")
async def toggle_water_reminder(callback: CallbackQuery):
    """Переключить напоминания о воде"""
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            user.remind_water = not user.remind_water
            await session.commit()

            await callback.message.edit_text(
                "🔔 **Настройки напоминаний**\n\n"
                "Включи/выключи нужные напоминания:",
                reply_markup=get_reminders_keyboard(user),
                parse_mode="Markdown"
            )

    status = "включены" if user.remind_water else "выключены"
    await callback.answer(f"Напоминания о воде {status}")


@router.callback_query(F.data == "toggle_food_reminder")
async def toggle_food_reminder(callback: CallbackQuery):
    """Переключить напоминания о еде"""
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            user.remind_food = not user.remind_food
            await session.commit()

            await callback.message.edit_text(
                "🔔 **Настройки напоминаний**\n\n"
                "Включи/выключи нужные напоминания:",
                reply_markup=get_reminders_keyboard(user),
                parse_mode="Markdown"
            )

    status = "включены" if user.remind_food else "выключены"
    await callback.answer(f"Напоминания о еде {status}")


@router.callback_query(F.data == "toggle_weight_reminder")
async def toggle_weight_reminder(callback: CallbackQuery):
    """Переключить напоминания о весе"""
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            user.remind_weight = not user.remind_weight
            await session.commit()

            await callback.message.edit_text(
                "🔔 **Настройки напоминаний**\n\n"
                "Включи/выключи нужные напоминания:",
                reply_markup=get_reminders_keyboard(user),
                parse_mode="Markdown"
            )

    status = "включены" if user.remind_weight else "выключены"
    await callback.answer(f"Напоминания о весе {status}")


@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: CallbackQuery):
    """Вернуться к настройкам"""
    await callback.message.edit_text(
        "⚙️ **Настройки**\n\n"
        "Выбери что хочешь изменить:",
        reply_markup=get_settings_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "close_settings")
async def close_settings(callback: CallbackQuery):
    """Закрыть настройки"""
    await callback.message.delete()
    await callback.answer()
