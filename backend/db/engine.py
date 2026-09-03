from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from backend.config import settings

def get_async_db_url(url: str) -> str:
    clean_url = url.strip()
    if clean_url.startswith("postgresql://"):
        clean_url = clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif clean_url.startswith("postgres://"):
        clean_url = clean_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif clean_url.startswith("postgresql+psycopg2://"):
        clean_url = clean_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    return clean_url


db_url = get_async_db_url(settings.supabase_db_url)

engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
