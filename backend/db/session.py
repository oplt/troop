from collections.abc import AsyncGenerator
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.modules.observability.metrics import record_db_pool_checkout_wait

# AsyncAdaptedQueuePool (SQLAlchemy default when poolclass is omitted) reuses connections
# across requests in the same process. Celery workers use smaller pool settings via
# DATABASE_POOL_*_WORKER / DATABASE_PROCESS_ROLE. Alembic keeps NullPool separately.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.effective_database_pool_size,
    max_overflow=settings.effective_database_max_overflow,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    started = perf_counter()
    session = SessionLocal()
    record_db_pool_checkout_wait(perf_counter() - started, role=settings.database_process_role)
    try:
        yield session
    finally:
        await session.close()
