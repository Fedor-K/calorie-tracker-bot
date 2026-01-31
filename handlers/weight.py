from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, desc

from database.db import async_session
from database.models import User, WeightEntry

router = Router()


class WeightStates(StatesGroup):
    waiting_for_weight = State()


@router.message(F.text == "⚖️ Вес")
async def handle_weight_button(message: Message, state: FSMContext):
    """Кнопка веса"""
    user_id = message.from_user.id

    async with async_session() as session:
        # Получаем последние записи веса
        result = await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(desc(WeightEntry.created_at))
            .limit(5)
        )
        entries = result.scalars().all()

        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

    if entries:
        history = "\n".join([
            f"  {e.created_at.strftime('%d.%m')}: **{e.weight}** кг"
            for e in entries
        ])

        current = entries[0].weight
        target = user.target_weight if user and user.target_weight else None

        response = f"⚖️ **Твой вес**\n\n"
        response += f"Текущий: **{current}** кг\n"

        if target:
            diff = current - target
            if diff > 0:
                response += f"До цели: {diff:.1f} кг ↓\n"
            elif diff < 0:
                response += f"До цели: {abs(diff):.1f} кг ↑\n"
            else:
                response += "🎉 Цель достигнута!\n"

        response += f"\n📊 История:\n{history}\n\n"
        response += "Отправь новый вес (например: 75.5)"
    else:
        response = (
            "⚖️ **Вес**\n\n"
            "У тебя пока нет записей.\n"
            "Отправь свой вес (например: 75.5)"
        )

    await message.answer(response, parse_mode="Markdown")
    await state.set_state(WeightStates.waiting_for_weight)


@router.message(F.text.lower().startswith("/weight"))
async def cmd_weight(message: Message):
    """Команда /weight [вес]"""
    user_id = message.from_user.id
    text = message.text

    parts = text.split()
    if len(parts) > 1:
        try:
            weight = float(parts[1].replace(",", "."))
            if weight < 20 or weight > 300:
                await message.answer("❌ Укажи реальный вес (20-300 кг)")
                return

            await save_weight(user_id, weight, message)

        except ValueError:
            await message.answer("❌ Неверный формат. Пример: /weight 75.5")
    else:
        await message.answer("⚖️ Укажи вес: /weight 75.5")


MENU_BUTTONS = {
    "📊 Статистика", "💧 Вода", "⚖️ Вес", "🏃 Активность",
    "🍽 План питания", "⚙️ Настройки"
}


@router.message(WeightStates.waiting_for_weight)
async def process_weight_input(message: Message, state: FSMContext):
    """Обработка ввода веса в состоянии ожидания"""
    # Пропускаем команды и кнопки меню
    if message.text.startswith("/") or message.text in MENU_BUTTONS:
        await state.clear()
        return

    try:
        weight = float(message.text.replace(",", "."))
        if weight < 20 or weight > 300:
            await message.answer("❌ Укажи реальный вес (20-300 кг)")
            return

        await save_weight(message.from_user.id, weight, message)
        await state.clear()

    except ValueError:
        await message.answer("❌ Отправь число (например: 75.5)")


async def save_weight(user_id: int, weight: float, message: Message):
    """Сохранить вес в базу"""
    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)
            await session.flush()

        # Получаем предыдущий вес
        prev_result = await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(desc(WeightEntry.created_at))
            .limit(1)
        )
        prev_entry = prev_result.scalar_one_or_none()

        # Сохраняем новый вес
        entry = WeightEntry(user_id=user_id, weight=weight)
        session.add(entry)

        # Обновляем текущий вес пользователя
        user.current_weight = weight

        await session.commit()

    # Формируем ответ
    response = f"⚖️ Вес **{weight}** кг сохранён!\n"

    if prev_entry:
        diff = weight - prev_entry.weight
        days = (datetime.now(timezone.utc).replace(tzinfo=None) - prev_entry.created_at).days

        if diff > 0:
            response += f"📈 +{diff:.1f} кг"
        elif diff < 0:
            response += f"📉 {diff:.1f} кг"
        else:
            response += "➡️ Без изменений"

        if days > 0:
            response += f" за {days} дн."

    await message.answer(response, parse_mode="Markdown")
