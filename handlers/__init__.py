from aiogram import Router

# Импортируем все роутеры
from handlers.onboarding import router as onboarding_router
from handlers.chat import router as chat_router
from handlers.photo import router as photo_router
from handlers.callbacks import router as callbacks_router
from handlers.water import router as water_router
from handlers.stats import router as stats_router
from handlers.settings import router as settings_router
from handlers.weight import router as weight_router
from handlers.activity import router as activity_router
from handlers.health import router as health_router


def setup_routers() -> Router:
    """Настройка всех роутеров"""
    main_router = Router()

    # Порядок важен!
    # 1. Онбординг - обрабатывает /start и FSM состояния
    main_router.include_router(onboarding_router)

    # 2. Фото - обрабатывает фото еды
    main_router.include_router(photo_router)

    # 3. Callbacks - все inline кнопки
    main_router.include_router(callbacks_router)

    # 4. Специфические handlers для кнопок и команд
    main_router.include_router(water_router)
    main_router.include_router(stats_router)
    main_router.include_router(settings_router)
    main_router.include_router(weight_router)
    main_router.include_router(activity_router)
    main_router.include_router(health_router)

    # 5. Chat - главный AI handler для текста (должен быть последним!)
    main_router.include_router(chat_router)

    return main_router
