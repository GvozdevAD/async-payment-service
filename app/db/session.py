"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings

_engine: AsyncEngine | None = None
_async_session: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the initialized async database engine.

    Returns:
        Active async SQLAlchemy engine.

    Raises:
        RuntimeError: If init_db has not been called yet.
    """
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the initialized async session factory.

    Returns:
        Configured async session maker.

    Raises:
        RuntimeError: If init_db has not been called yet.
    """
    if _async_session is None:
        raise RuntimeError("Database session maker is not initialized")
    return _async_session


async def init_db() -> None:
    """Create the async engine and session factory."""
    global _engine, _async_session

    settings = get_settings()
    _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    _async_session = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_db() -> None:
    """Dispose the async engine and reset session factory."""
    global _engine, _async_session

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for dependency injection.

    Yields:
        Request-scoped async database session.
    """
    async with get_async_sessionmaker()() as session:
        yield session
