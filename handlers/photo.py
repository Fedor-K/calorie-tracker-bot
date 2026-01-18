"""
Photo Handler - Обработка фото (еда и фитнес-трекеры)
Поддерживает альбомы (несколько фото как один приём пищи)
"""
import asyncio
import logging
from typing import Dict, List, Tuple
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.db import async_session
from database.models import User
from services.ai import analyze_food_image, analyze_food_images_batch
from services.coach import format_food_analysis, handle_fitness_photo, get_user_context
from keyboards.main import get_main_keyboard, get_food_confirm_keyboard

logger = logging.getLogger(__name__)
router = Router()

# Хранилище для альбомов: {media_group_id: {"photos": [...], "user_id": ..., "message": ..., "state": ...}}
_album_storage: Dict[str, dict] = {}
_album_locks: Dict[str, asyncio.Lock] = {}

# Время ожидания всех фото альбома (секунды)
ALBUM_COLLECT_TIMEOUT = 1.5


class PhotoStates(StatesGroup):
    """Состояния для обработки фото"""
    waiting_food_confirm = State()  # Ожидание подтверждения еды
    waiting_food_correction = State()  # Ожидание исправления


async def _get_album_lock(media_group_id: str) -> asyncio.Lock:
    """Получить блокировку для конкретного альбома"""
    if media_group_id not in _album_locks:
        _album_locks[media_group_id] = asyncio.Lock()
    return _album_locks[media_group_id]


async def _process_album(media_group_id: str, bot: Bot):
    """
    Обрабатывает собранный альбом после таймаута
    """
    # Ждём пока соберутся все фото
    await asyncio.sleep(ALBUM_COLLECT_TIMEOUT)

    lock = await _get_album_lock(media_group_id)
    async with lock:
        if media_group_id not in _album_storage:
            return

        album_data = _album_storage.pop(media_group_id)
        # Очищаем lock
        _album_locks.pop(media_group_id, None)

    photos_data = album_data["photos"]
    user_id = album_data["user_id"]
    first_message = album_data["message"]
    state = album_data["state"]
    processing_msg = album_data.get("processing_msg")

    logger.info(f"[ALBUM] user={user_id} | Processing {len(photos_data)} photos")

    try:
        # Анализируем все фото вместе
        photo_data = await analyze_food_images_batch(photos_data)
        photo_type = photo_data.get("type", "food")

        if photo_type == "fitness":
            # Фитнес - сохраняем сразу
            response = await handle_fitness_photo(user_id, photo_data)
            logger.info(f"[ALBUM] user={user_id} | Fitness from album")

            if processing_msg:
                try:
                    await processing_msg.delete()
                except Exception:
                    pass
            await first_message.answer(
                response,
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )

        elif photo_type == "food":
            # Еда - показываем анализ и просим подтвердить
            response = await format_food_analysis(user_id, photo_data, saved=False)
            response += "\n\n_Нажми «Записать» или напиши уточнение_"

            items = photo_data.get("items", [])
            total_cal = photo_data.get("total", {}).get("calories", 0)
            logger.info(
                f"[ALBUM] user={user_id} | Food: {len(items)} items | "
                f"{total_cal} ккал | waiting confirm"
            )

            # Сохраняем данные в FSM для подтверждения
            await state.set_state(PhotoStates.waiting_food_confirm)
            await state.update_data(pending_food=photo_data)

            if processing_msg:
                try:
                    await processing_msg.delete()
                except Exception:
                    pass
            await first_message.answer(
                response,
                parse_mode="Markdown",
                reply_markup=get_food_confirm_keyboard()
            )

        else:
            # Другое
            description = photo_data.get("description", "Не удалось распознать")
            response = f"🤔 Это не похоже на еду или фитнес-трекер.\n\n{description}"
            logger.info(f"[ALBUM] user={user_id} | Other: {description[:50]}")

            if processing_msg:
                try:
                    await processing_msg.delete()
                except Exception:
                    pass
            await first_message.answer(
                response,
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )

    except Exception as e:
        logger.error(f"[ALBUM] user={user_id} | Error: {e}")
        await state.clear()
        if processing_msg:
            try:
                await processing_msg.edit_text(
                    f"❌ Ошибка при анализе фото.\n\n"
                    f"Попробуй:\n"
                    f"• Отправить другое фото\n"
                    f"• Сделать фото ближе\n"
                    f"• Написать что съел текстом"
                )
            except Exception:
                await first_message.answer(
                    f"❌ Ошибка при анализе. Попробуй отправить другое фото."
                )


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обработка фото (еда или фитнес-трекер, включая альбомы)"""
    user_id = message.from_user.id
    media_group_id = message.media_group_id

    # Проверяем состояние FSM
    current_state = await state.get_state()

    # Если ждём исправление - новое фото отменяет старое
    if current_state == PhotoStates.waiting_food_correction:
        await state.clear()
        logger.info(f"[PHOTO] user={user_id} | New photo cancels correction mode")
    # Если ждём подтверждение и пришёл альбом - отменяем старое
    elif current_state == PhotoStates.waiting_food_confirm and media_group_id:
        await state.clear()
        logger.info(f"[PHOTO] user={user_id} | New album cancels pending food")
    # Пропускаем если в других состояниях (не фото-состояниях)
    elif current_state is not None and "Photo" not in str(current_state):
        logger.info(f"[PHOTO] user={user_id} | Skip: user in state {current_state}")
        return

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

    # Если это альбом (несколько фото)
    if media_group_id:
        logger.info(f"[PHOTO] user={user_id} | Album photo, group={media_group_id}")

        lock = await _get_album_lock(media_group_id)
        async with lock:
            if media_group_id not in _album_storage:
                # Первое фото в альбоме - инициализируем хранилище
                _album_storage[media_group_id] = {
                    "photos": [],
                    "user_id": user_id,
                    "message": message,
                    "state": state,
                    "processing_msg": None
                }
                # Отправляем сообщение о начале анализа
                processing_msg = await message.answer("🔍 Анализирую альбом...")
                _album_storage[media_group_id]["processing_msg"] = processing_msg

                # Запускаем таймер обработки
                asyncio.create_task(_process_album(media_group_id, message.bot))

            # Добавляем фото в альбом
            _album_storage[media_group_id]["photos"].append((image_bytes, "image/jpeg"))

        return

    # Одиночное фото - обрабатываем сразу
    logger.info(f"[PHOTO] user={user_id} | Single photo")

    processing_msg = await message.answer("🔍 Анализирую фото...")

    try:
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
