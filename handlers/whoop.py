"""
Обработчик команд WHOOP
"""
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from database.db import async_session
from database.models import User, ActivityEntry
from services.whoop import (
    get_auth_url,
    get_today_summary,
    get_recovery,
    get_sleep,
    get_workouts
)
import config

router = Router()


def get_whoop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Восстановление", callback_data="whoop_recovery")],
        [InlineKeyboardButton(text="😴 Сон", callback_data="whoop_sleep")],
        [InlineKeyboardButton(text="🏋️ Тренировки", callback_data="whoop_workouts")],
        [InlineKeyboardButton(text="🔄 Синхронизировать всё", callback_data="whoop_sync")],
    ])


@router.message(F.text.lower().startswith("/whoop"))
async def cmd_whoop(message: Message):
    """Команда /whoop"""
    user_id = message.from_user.id

    # Проверяем, настроен ли WHOOP
    if not config.WHOOP_CLIENT_ID:
        await message.answer(
            "⚠️ **WHOOP не настроен**\n\n"
            "Для подключения WHOOP нужно:\n\n"
            "1. Зарегистрироваться на [developer.whoop.com](https://developer.whoop.com)\n"
            "2. Создать приложение и получить Client ID и Secret\n"
            "3. Добавить в .env:\n"
            "```\n"
            "WHOOP_CLIENT_ID=xxx\n"
            "WHOOP_CLIENT_SECRET=xxx\n"
            "WHOOP_REDIRECT_URI=http://your-server:8080/whoop/callback\n"
            "```\n"
            "4. Перезапустить бота",
            parse_mode="Markdown"
        )
        return

    # Проверяем, подключен ли пользователь
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user and user.whoop_access_token:
            # Уже подключен - показываем меню
            await message.answer(
                "⌚ **WHOOP подключен!**\n\n"
                "Выбери что хочешь посмотреть:",
                parse_mode="Markdown",
                reply_markup=get_whoop_keyboard()
            )
            return

    # Не подключен - даём ссылку для авторизации
    auth_url = get_auth_url(user_id)

    await message.answer(
        "⌚ **Подключение WHOOP**\n\n"
        f"[Нажми сюда для авторизации]({auth_url})\n\n"
        "После авторизации ты сможешь:\n"
        "• Смотреть Recovery Score\n"
        "• Отслеживать сон\n"
        "• Синхронизировать тренировки\n"
        "• Автоматически получать данные",
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "whoop_recovery")
async def whoop_recovery(callback):
    """Показать данные восстановления"""
    user_id = callback.from_user.id

    await callback.message.edit_text("🔄 Загружаю данные...")

    data = await get_recovery(user_id)

    if "error" in data:
        await callback.message.edit_text(
            f"❌ Ошибка: {data['error']}\n\n"
            "Попробуй переподключить WHOOP: /whoop"
        )
        return

    records = data.get("records", [])
    if not records:
        await callback.message.edit_text(
            "📊 Нет данных о восстановлении за сегодня",
            reply_markup=get_whoop_keyboard()
        )
        return

    latest = records[0]
    score = latest.get("score", {})

    recovery_pct = score.get("recovery_score", 0)
    hrv = score.get("hrv_rmssd_milli", 0)
    rhr = score.get("resting_heart_rate", 0)

    # Определяем цвет/статус
    if recovery_pct >= 67:
        status = "🟢 Отличное"
    elif recovery_pct >= 34:
        status = "🟡 Нормальное"
    else:
        status = "🔴 Низкое"

    await callback.message.edit_text(
        f"📊 **Восстановление WHOOP**\n\n"
        f"**Recovery: {recovery_pct}%** {status}\n\n"
        f"❤️ HRV: {hrv:.1f} мс\n"
        f"💓 Пульс покоя: {rhr} уд/мин\n",
        parse_mode="Markdown",
        reply_markup=get_whoop_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "whoop_sleep")
async def whoop_sleep(callback):
    """Показать данные о сне"""
    user_id = callback.from_user.id

    await callback.message.edit_text("🔄 Загружаю данные...")

    data = await get_sleep(user_id)

    if "error" in data:
        await callback.message.edit_text(
            f"❌ Ошибка: {data['error']}",
            reply_markup=get_whoop_keyboard()
        )
        return

    records = data.get("records", [])
    if not records:
        await callback.message.edit_text(
            "😴 Нет данных о сне",
            reply_markup=get_whoop_keyboard()
        )
        return

    latest = records[0]
    score = latest.get("score", {})

    # Время в миллисекундах
    total_ms = score.get("total_in_bed_time_milli", 0)
    sleep_ms = score.get("total_sleep_time_milli", 0)
    rem_ms = score.get("total_rem_sleep_time_milli", 0)
    deep_ms = score.get("total_slow_wave_sleep_time_milli", 0)

    # Конвертируем в часы
    total_h = total_ms / 3600000
    sleep_h = sleep_ms / 3600000
    rem_h = rem_ms / 3600000
    deep_h = deep_ms / 3600000

    efficiency = score.get("sleep_efficiency_percentage", 0)

    await callback.message.edit_text(
        f"😴 **Сон WHOOP**\n\n"
        f"🛏 В постели: {total_h:.1f} ч\n"
        f"😴 Сон: {sleep_h:.1f} ч\n"
        f"🌙 REM: {rem_h:.1f} ч\n"
        f"💤 Глубокий: {deep_h:.1f} ч\n\n"
        f"📊 Эффективность: {efficiency:.0f}%",
        parse_mode="Markdown",
        reply_markup=get_whoop_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "whoop_workouts")
async def whoop_workouts(callback):
    """Показать тренировки"""
    user_id = callback.from_user.id

    await callback.message.edit_text("🔄 Загружаю данные...")

    today = datetime.utcnow().strftime("%Y-%m-%d")
    data = await get_workouts(user_id, today)

    if "error" in data:
        await callback.message.edit_text(
            f"❌ Ошибка: {data['error']}",
            reply_markup=get_whoop_keyboard()
        )
        return

    records = data.get("records", [])
    if not records:
        await callback.message.edit_text(
            "🏋️ Нет тренировок за сегодня",
            reply_markup=get_whoop_keyboard()
        )
        return

    text = "🏋️ **Тренировки WHOOP**\n\n"

    for workout in records[:5]:
        score = workout.get("score", {})
        sport_id = workout.get("sport_id", 0)

        strain = score.get("strain", 0)
        calories = score.get("kilojoule", 0) / 4.184  # конвертируем в ккал
        avg_hr = score.get("average_heart_rate", 0)
        max_hr = score.get("max_heart_rate", 0)

        text += (
            f"**Strain: {strain:.1f}**\n"
            f"🔥 {calories:.0f} ккал\n"
            f"❤️ {avg_hr} / {max_hr} уд/мин\n\n"
        )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_whoop_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "whoop_sync")
async def whoop_sync(callback):
    """Синхронизировать все данные из WHOOP"""
    user_id = callback.from_user.id

    await callback.message.edit_text("🔄 Синхронизирую данные WHOOP...")

    summary = await get_today_summary(user_id)

    synced = []

    # Синхронизируем тренировки
    workouts = summary.get("workouts", {}).get("records", [])
    if workouts:
        async with async_session() as session:
            for workout in workouts:
                score = workout.get("score", {})
                calories = int(score.get("kilojoule", 0) / 4.184)

                if calories > 0:
                    entry = ActivityEntry(
                        user_id=user_id,
                        activity_type="WHOOP Workout",
                        duration=0,
                        calories_burned=calories,
                        note=f"Strain: {score.get('strain', 0):.1f}"
                    )
                    session.add(entry)
                    synced.append(f"🏋️ Тренировка: {calories} ккал")

            await session.commit()

    # Формируем ответ
    recovery = summary.get("recovery", {}).get("records", [])
    sleep_data = summary.get("sleep", {}).get("records", [])

    text = "✅ **Синхронизация завершена!**\n\n"

    if recovery:
        rec = recovery[0].get("score", {})
        text += f"📊 Recovery: {rec.get('recovery_score', 0)}%\n"

    if sleep_data:
        slp = sleep_data[0].get("score", {})
        sleep_h = slp.get("total_sleep_time_milli", 0) / 3600000
        text += f"😴 Сон: {sleep_h:.1f} ч\n"

    if synced:
        text += f"\n🔄 Синхронизировано:\n" + "\n".join(synced)
    else:
        text += "\n💡 Новых тренировок не найдено"

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_whoop_keyboard()
    )
    await callback.answer()
