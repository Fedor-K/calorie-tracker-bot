import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database.db import init_db
from handlers import setup_routers
from services.scheduler import setup_scheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""

    # Проверяем конфигурацию
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return

    if not config.CLAUDE_API_KEY and not config.ZAI_API_KEY:
        logger.error("CLAUDE_API_KEY или ZAI_API_KEY не установлен!")
        return

    if not config.DATABASE_URL:
        logger.error("DATABASE_URL не установлен!")
        return

    # Инициализируем базу данных
    logger.info("Инициализация базы данных...")
    await init_db()
    logger.info("База данных готова")

    # Создаём бота и диспетчер
    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Подключаем роутеры
    router = setup_routers()
    dp.include_router(router)

    # Запускаем планировщик напоминаний
    logger.info("Запуск планировщика напоминаний...")
    setup_scheduler(bot)

    # Удаляем webhook если был
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем бота
    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
