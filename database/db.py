import ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database.models import Base
import config


def get_database_url():
    """Преобразует URL для asyncpg"""
    url = config.DATABASE_URL
    # Заменяем драйвер
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    # Убираем sslmode и channel_binding (asyncpg использует ssl=require)
    if "?" in url:
        base, params = url.split("?", 1)
        param_list = params.split("&")
        filtered_params = [p for p in param_list if not p.startswith(("sslmode=", "channel_binding="))]
        if filtered_params:
            url = base + "?" + "&".join(filtered_params)
        else:
            url = base
    return url


# SSL контекст для Neon
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Создаём async engine для PostgreSQL
engine = create_async_engine(
    get_database_url(),
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": ssl_context}
)

# Session factory
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Инициализация базы данных - создание всех таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получить сессию базы данных"""
    async with async_session() as session:
        return session
