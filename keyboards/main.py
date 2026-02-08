from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Упрощённая главная клавиатура бота
    Основные быстрые действия + AI коуч для остального
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="💧 Вода")
            ],
            [
                KeyboardButton(text="🍽 План питания"),
                KeyboardButton(text="📈 Тренды")
            ],
            [
                KeyboardButton(text="⚙️ Настройки")
            ]
        ],
        resize_keyboard=True
    )
    return keyboard


def get_water_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для быстрого добавления воды"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🥤 150 мл", callback_data="water_150"),
                InlineKeyboardButton(text="🥤 250 мл", callback_data="water_250"),
                InlineKeyboardButton(text="🥤 350 мл", callback_data="water_350")
            ],
            [
                InlineKeyboardButton(text="🫗 500 мл", callback_data="water_500"),
                InlineKeyboardButton(text="🫗 750 мл", callback_data="water_750"),
                InlineKeyboardButton(text="🫗 1000 мл", callback_data="water_1000")
            ]
        ]
    )
    return keyboard


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Цель калорий", callback_data="set_calories")],
            [InlineKeyboardButton(text="💧 Цель воды", callback_data="set_water")],
            [InlineKeyboardButton(text="⚖️ Текущий вес", callback_data="set_current_weight")],
            [InlineKeyboardButton(text="🎯 Целевой вес", callback_data="set_target_weight")],
            [InlineKeyboardButton(text="📏 Рост", callback_data="set_height")],
            [InlineKeyboardButton(text="🔔 Напоминания", callback_data="set_reminders")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_settings")]
        ]
    )
    return keyboard


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}")
            ]
        ]
    )
    return keyboard


def get_food_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения еды после анализа фото"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Записать", callback_data="food_confirm"),
                InlineKeyboardButton(text="✏️ Исправить", callback_data="food_correct")
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="food_cancel")
            ]
        ]
    )
    return keyboard


def get_reminders_keyboard(user) -> InlineKeyboardMarkup:
    """Клавиатура настроек напоминаний"""
    water_status = "✅" if user.remind_water else "❌"
    food_status = "✅" if user.remind_food else "❌"
    weight_status = "✅" if user.remind_weight else "❌"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{water_status} Напоминания о воде",
                callback_data="toggle_water_reminder"
            )],
            [InlineKeyboardButton(
                text=f"{food_status} Напоминания о еде",
                callback_data="toggle_food_reminder"
            )],
            [InlineKeyboardButton(
                text=f"{weight_status} Напоминания о весе",
                callback_data="toggle_weight_reminder"
            )],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_settings")]
        ]
    )
    return keyboard
