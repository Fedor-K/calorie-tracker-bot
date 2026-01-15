from aiogram import Router
from handlers.start import router as start_router
from handlers.food import router as food_router
from handlers.weight import router as weight_router
from handlers.water import router as water_router
from handlers.activity import router as activity_router
from handlers.stats import router as stats_router
from handlers.settings import router as settings_router
from handlers.health import router as health_router


def setup_routers() -> Router:
    """Настройка всех роутеров"""
    main_router = Router()

    main_router.include_router(start_router)
    main_router.include_router(food_router)
    main_router.include_router(weight_router)
    main_router.include_router(water_router)
    main_router.include_router(activity_router)
    main_router.include_router(stats_router)
    main_router.include_router(settings_router)
    main_router.include_router(health_router)

    return main_router
