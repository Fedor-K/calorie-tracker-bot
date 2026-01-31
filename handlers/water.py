from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, WaterEntry
from keyboards.main import get_water_keyboard

router = Router()


async def get_today_water(user_id: int) -> int:
    """Получить количество воды за сегодня (с учётом часового пояса пользователя)"""
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        try:
            tz = ZoneInfo(user.timezone if user else "Europe/Moscow")
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        result = await session.execute(
            select(func.sum(WaterEntry.amount))
            .where(WaterEntry.user_id == user_id)
            .where(WaterEntry.created_at >= day_start_utc)
        )
        total = result.scalar_one_or_none()
        return total or 0


async def add_water(user_id: int, amount: int) -> tuple[int, int]:
    """Добавить воду и вернуть (всего сегодня, цель)"""
    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            user = User(id=user_id)
            session.add(user)
            await session.flush()

        # Добавляем запись
        entry = WaterEntry(user_id=user_id, amount=amount)
        session.add(entry)
        await session.commit()

        water_goal = user.water_goal

    total = await get_today_water(user_id)
    return total, water_goal


@router.message(F.text == "💧 Вода")
async def handle_water_button(message: Message):
    """Кнопка воды - показать клавиатуру"""
    user_id = message.from_user.id
    total = await get_today_water(user_id)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        goal = user.water_goal if user else 2000

    progress = min(100, int(total / goal * 100))
    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

    await message.answer(
        f"💧 **Вода за сегодня**\n\n"
        f"Выпито: **{total}** / {goal} мл\n"
        f"[{bar}] {progress}%\n\n"
        f"Выбери количество:",
        reply_markup=get_water_keyboard(),
        parse_mode="Markdown"
    )


@router.message(F.text.lower().startswith("/water"))
async def cmd_water(message: Message):
    """Команда /water [количество]"""
    user_id = message.from_user.id
    text = message.text

    # Парсим количество
    parts = text.split()
    if len(parts) > 1:
        try:
            amount = int(parts[1])
            if amount <= 0 or amount > 5000:
                await message.answer("❌ Укажи количество от 1 до 5000 мл")
                return

            total, goal = await add_water(user_id, amount)
            progress = min(100, int(total / goal * 100))

            await message.answer(
                f"💧 +{amount} мл добавлено!\n\n"
                f"Всего: **{total}** / {goal} мл ({progress}%)",
                parse_mode="Markdown"
            )
        except ValueError:
            await message.answer(
                "💧 Используй: /water 250\n"
                "Или нажми кнопку «Вода»",
                reply_markup=get_water_keyboard()
            )
    else:
        # Показываем клавиатуру
        await handle_water_button(message)


@router.callback_query(F.data.startswith("water_"))
async def handle_water_callback(callback: CallbackQuery):
    """Обработка нажатий на кнопки воды"""
    user_id = callback.from_user.id
    amount = int(callback.data.split("_")[1])

    total, goal = await add_water(user_id, amount)
    progress = min(100, int(total / goal * 100))
    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

    # Проверяем достижение цели
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

    # Это количество воды
    amount = int(action)
    total, goal = await add_water(user_id, amount)
    progress = min(100, int(total / goal * 100))
    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

    # Проверяем достижение цели
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
