"""
Photo Handler - Обработка фото (еда и фитнес-трекеры)
"""
import json
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.db import async_session
from database.models import User
from services.ai import analyze_food_image
from services.coach import format_food_analysis, handle_fitness_photo, get_user_context
from keyboards.main import get_main_keyboard, get_food_confirm_keyboard

logger = logging.getLogger(__name__)
router = Router()


class PhotoStates(StatesGroup):
    """Состояния для обработки фото"""
    waiting_food_confirm = State()  # Ожидание подтверждения еды
    waiting_food_correction = State()  # Ожидание исправления


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обработка фото (еда или фитнес-трекер)"""
    user_id = message.from_user.id
    logger.info(f"[PHOTO] user={user_id} | Получено фото")

    # Проверяем состояние FSM
    current_state = await state.get_state()

    # Если ждём исправление - новое фото отменяет старое и анализируется заново
    if current_state == PhotoStates.waiting_food_correction:
        await state.clear()
        logger.info(f"[PHOTO] user={user_id} | New photo cancels correction mode")

    # Пропускаем если в других состояниях (не фото-состояниях)
    elif current_state is not None and "Photo" not in str(current_state):
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
            # Фитнес - сохраняем сразу (обновляем дневную активность)
            response = await handle_fitness_photo(user_id, photo_data)
            logger.info(f"[PHOTO] user={user_id} | Fitness: {photo_data.get('device', '?')}")

            await processing_msg.delete()
            await message.answer(
                response,
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )

        elif photo_type == "food":
            # Еда - показываем анализ и просим подтвердить
            response = await format_food_analysis(user_id, photo_data, saved=False)
            response += "\n\n_Нажми «Записать» или напиши уточнение_"

            logger.info(
                f"[PHOTO] user={user_id} | Food: {photo_data.get('description', '?')} | "
                f"{photo_data.get('total', {}).get('calories', 0)} ккал | waiting confirm"
            )

            # Сохраняем данные в FSM для подтверждения
            await state.set_state(PhotoStates.waiting_food_confirm)
            await state.update_data(pending_food=photo_data)

            await processing_msg.delete()
            await message.answer(
                response,
                parse_mode="Markdown",
                reply_markup=get_food_confirm_keyboard()
            )

        else:
            # Другое фото
            description = photo_data.get("description", "Не удалось распознать")
            response = f"🤔 Это не похоже на еду или фитнес-трекер.\n\n{description}"
            logger.info(f"[PHOTO] user={user_id} | Other: {description[:50]}")

            await processing_msg.delete()
            await message.answer(
                response,
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )

    except Exception as e:
        logger.error(f"[PHOTO] user={user_id} | Error: {e}")
        await state.clear()
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


@router.message(PhotoStates.waiting_food_confirm)
async def handle_food_correction_text(message: Message, state: FSMContext):
    """Обработка текстового уточнения к фото еды"""
    user_id = message.from_user.id
    text = message.text or ""

    if not text.strip():
        return

    logger.info(f"[PHOTO] user={user_id} | Correction text: {text}")

    # Получаем сохранённые данные о еде
    data = await state.get_data()
    pending_food = data.get("pending_food", {})

    if not pending_food:
        await state.clear()
        await message.answer("❌ Данные о еде не найдены. Отправь фото заново.")
        return

    processing_msg = await message.answer("🔄 Уточняю...")

    try:
        # Вызываем AI для корректировки данных
        from services.ai import correct_food_analysis
        corrected_food = await correct_food_analysis(pending_food, text)

        # Обновляем данные в FSM
        await state.update_data(pending_food=corrected_food)

        # Показываем обновлённый анализ
        response = await format_food_analysis(user_id, corrected_food, saved=False)
        response += "\n\n_Нажми «Записать» или напиши ещё уточнение_"

        await processing_msg.delete()
        await message.answer(
            response,
            parse_mode="Markdown",
            reply_markup=get_food_confirm_keyboard()
        )

    except Exception as e:
        logger.error(f"[PHOTO] user={user_id} | Correction error: {e}")
        await processing_msg.edit_text(
            f"❌ Ошибка при корректировке. Попробуй записать как есть или отправь новое фото."
        )
