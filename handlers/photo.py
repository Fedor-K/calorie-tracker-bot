"""
Photo Handler - Обработка фото (еда и фитнес-трекеры)
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from database.db import async_session
from database.models import User
from services.ai import analyze_food_image
from services.coach import handle_photo_message, handle_fitness_photo, get_user_context
from keyboards.main import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обработка фото (еда или фитнес-трекер)"""
    user_id = message.from_user.id
    logger.info(f"[PHOTO] user={user_id} | Получено фото")

    # Проверяем, что пользователь не в состоянии FSM
    current_state = await state.get_state()
    if current_state is not None:
        logger.info(f"[PHOTO] user={user_id} | Skip: user in state {current_state}")
        return

    # Отправляем сообщение о начале анализа
    processing_msg = await message.answer("🔍 Анализирую фото...")

    try:
        # Проверяем/создаём пользователя
        async with async_session() as session:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            if not user:
                user = User(
                    id=user_id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name
                )
                session.add(user)
                await session.commit()

        # Получаем фото максимального размера
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_data = await message.bot.download_file(file.file_path)
        image_bytes = file_data.read()

        # Анализируем через AI
        photo_data = await analyze_food_image(image_bytes)
        photo_type = photo_data.get("type", "food")

        # Обрабатываем в зависимости от типа
        if photo_type == "fitness":
            response = await handle_fitness_photo(user_id, photo_data)
            logger.info(f"[PHOTO] user={user_id} | Fitness: {photo_data.get('device', '?')}")
        elif photo_type == "food":
            response = await handle_photo_message(user_id, photo_data)
            logger.info(
                f"[PHOTO] user={user_id} | Food: {photo_data.get('description', '?')} | "
                f"{photo_data.get('total', {}).get('calories', 0)} ккал"
            )
        else:
            # Другое фото
            description = photo_data.get("description", "Не удалось распознать")
            response = f"🤔 Это не похоже на еду или фитнес-трекер.\n\n{description}"
            logger.info(f"[PHOTO] user={user_id} | Other: {description[:50]}")

        # Удаляем индикатор и отправляем ответ
        await processing_msg.delete()
        await message.answer(
            response,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"[PHOTO] user={user_id} | Error: {e}")
        try:
            await processing_msg.edit_text(
                f"❌ Ошибка при анализе фото.\n\n"
                f"Попробуй:\n"
                f"• Отправить другое фото\n"
                f"• Сделать фото ближе\n"
                f"• Написать что съел текстом"
            )
        except Exception:
            await message.answer(
                f"❌ Ошибка при анализе. Попробуй отправить другое фото."
            )
