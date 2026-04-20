import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncGenerator:
    session = SessionLocal()
    try:
        yield session
    finally:
        close_task = asyncio.create_task(session.close())
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            # Let close complete cleanly before propagating cancellation.
            await close_task
            raise