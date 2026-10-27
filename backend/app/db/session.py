from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    # Test each pooled connection before use: MariaDB drops idle connections
    pool_pre_ping=True,
    pool_recycle=3600,
)

# expire_on_commit=False: objects stay readable after commit (no implicit lazy reload in async code)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed afterwards."""
    async with SessionLocal() as session:
        yield session
