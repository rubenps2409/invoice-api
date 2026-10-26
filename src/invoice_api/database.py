from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_api.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as db:
        yield db
