"""
Callbacks Handler - Обработка callback_query для еды (фото)
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main import get_main_keyboard
from handlers.photo import PhotoStates
from services.coach import save_food_entry, format_food_analysis, get_user_context

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# Подтверждение еды с фото
# ============================================================================

@router.callback_query(F.data == "food_confirm")
async def food_confirm_callback(callback: CallbackQuery, state: FSMContext):
    """Подтвердить и записать еду"""
    user_id = callback.from_user.id

    # Получаем данные из FSM
    data = await state.get_data()
    pending_food = data.get("pending_food")

    if not pending_food:
        await callback.answer("❌ Данные не найдены. Отправь фото заново.", show_alert=True)
        await state.clear()
        return

    try:
        # Сохраняем в базу
        await save_food_entry(user_id, pending_food)

        # Формируем ответ с обновлённой статистикой
        user_context = await get_user_context(user_id)
        response = await format_food_analysis(user_id, pending_food, user_context, saved=True)

        # Очищаем состояние
        await state.clear()

        # Обновляем сообщение
        await callback.message.edit_text(
            response,
            parse_mode="Markdown"
        )
        await callback.message.answer(
            "👍 Записано! Что дальше?",
            reply_markup=get_main_keyboard()
        )
        await callback.answer("✅ Записано!")

    except Exception as e:
        logger.error(f"[FOOD_CONFIRM] user={user_id} | Error: {e}")
        await callback.answer(f"❌ Ошибка при сохранении", show_alert=True)


@router.callback_query(F.data == "food_correct")
async def food_correct_callback(callback: CallbackQuery, state: FSMContext):
    """Начать исправление еды - просто напомнить что можно написать"""
    await callback.answer("✏️ Напиши уточнение текстом", show_alert=False)


@router.callback_query(F.data == "food_cancel")
async def food_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Отменить запись еды"""
    await state.clear()

    await callback.message.edit_text(
        "❌ Отменено. Можешь отправить другое фото или написать что съел.",
    )
    await callback.message.answer(
        "Что дальше?",
        reply_markup=get_main_keyboard()
    )
    await callback.answer("Отменено")
