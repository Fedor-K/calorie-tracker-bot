from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from database.db import async_session
from database.models import User, FoodEntry
from services.ai import analyze_food_image, generate_meal_plan
from keyboards.main import get_main_keyboard

router = Router()


@router.message(F.photo)
async def handle_food_photo(message: Message):
    """Обработка фото еды"""
    user_id = message.from_user.id

    # Отправляем сообщение о начале анализа
    processing_msg = await message.answer("🔍 Анализирую фото...")

    try:
        # Получаем фото максимального размера
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_data = await message.bot.download_file(file.file_path)
        image_bytes = file_data.read()

        # Анализируем через AI
        result = await analyze_food_image(image_bytes)

        # Сохраняем в базу
        async with async_session() as session:
            # Получаем пользователя
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            if not user:
                # Создаём если нет
                user = User(id=user_id, username=message.from_user.username)
                session.add(user)
                await session.flush()

            # Создаём запись о еде
            total = result.get("total", {})
            food_entry = FoodEntry(
                user_id=user_id,
                description=result.get("description", "Еда"),
                meal_type=result.get("meal_type"),
                calories=total.get("calories", 0),
                protein=total.get("protein", 0),
                carbs=total.get("carbs", 0),
                fat=total.get("fat", 0),
                fiber=total.get("fiber", 0),
                photo_file_id=photo.file_id,
                ai_raw_response=str(result)
            )
            session.add(food_entry)
            await session.commit()

        # Формируем ответ
        items_text = ""
        if "items" in result:
            for item in result["items"]:
                items_text += f"  • {item['name']}: {item.get('calories', '?')} ккал\n"

        response = (
            f"🍽 **{result.get('description', 'Анализ еды')}**\n\n"
            f"📊 **Итого:**\n"
            f"🔥 Калории: **{total.get('calories', 0)}** ккал\n"
            f"🥩 Белки: {total.get('protein', 0)} г\n"
            f"🍞 Углеводы: {total.get('carbs', 0)} г\n"
            f"🧈 Жиры: {total.get('fat', 0)} г\n"
        )

        if total.get("fiber"):
            response += f"🥬 Клетчатка: {total.get('fiber', 0)} г\n"

        if items_text:
            response += f"\n📝 **Состав:**\n{items_text}"

        if result.get("health_notes"):
            response += f"\n💡 {result['health_notes']}"

        # Удаляем сообщение "Анализирую..."
        await processing_msg.delete()

        await message.answer(response, parse_mode="Markdown")

    except Exception as e:
        await processing_msg.edit_text(
            f"❌ Ошибка при анализе: {str(e)[:100]}\n"
            "Попробуй отправить другое фото."
        )


@router.message(F.text == "🍽 План питания")
async def handle_meal_plan_button(message: Message):
    """Кнопка плана питания"""
    await cmd_plan(message)


@router.message(F.text.lower().startswith("/plan"))
async def cmd_plan(message: Message):
    """Генерация плана питания"""
    user_id = message.from_user.id

    processing_msg = await message.answer("🍽 Составляю план питания...")

    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            calorie_goal = user.calorie_goal if user else 2000

        plan = await generate_meal_plan(calorie_goal)

        await processing_msg.delete()
        await message.answer(
            f"🍽 **План питания на день**\n"
            f"🎯 Цель: {calorie_goal} ккал\n\n"
            f"{plan}",
            parse_mode="Markdown"
        )

    except Exception as e:
        await processing_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
