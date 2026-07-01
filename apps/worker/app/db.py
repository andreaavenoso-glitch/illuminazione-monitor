from collections.abc import AsyncIterator

from app.config import get_worker_settings
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

_settings = get_worker_settings()

# NullPool: each Celery task runs in its own asyncio.run() event loop, so
# pooled asyncpg connections from a previous task's loop are invalid on the
# next ("Future attached to a different loop"). NullPool opens a fresh
# connection per checkout instead of reusing one across loops.
engine = create_async_engine(_settings.database_url, echo=False, poolclass=NullPool)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
