"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings


class Database:
    """Owns the async engine and session factory lifecycle.

    Encapsulates connection state so callers use a single instance instead of
    mutable module-level globals.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def get_engine(self) -> AsyncEngine:
        """Return the initialized async database engine.

        Returns:
            Active async SQLAlchemy engine.

        Raises:
            RuntimeError: If init has not been called yet.
        """
        if self._engine is None:
            raise RuntimeError("Database engine is not initialized")
        return self._engine

    def get_sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        """Return the initialized async session factory.

        Returns:
            Configured async session maker.

        Raises:
            RuntimeError: If init has not been called yet.
        """
        if self._session_factory is None:
            raise RuntimeError("Database session maker is not initialized")
        return self._session_factory

    async def init(self) -> None:
        """Create the async engine and session factory."""
        settings = get_settings()
        self._engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def close(self) -> None:
        """Dispose the async engine and reset the session factory."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None


_database = Database()


def get_database() -> Database:
    """Return the process-wide database instance."""
    return _database


def get_engine() -> AsyncEngine:
    """Return the initialized async database engine.

    Returns:
        Active async SQLAlchemy engine.

    Raises:
        RuntimeError: If init_db has not been called yet.
    """
    return _database.get_engine()


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the initialized async session factory.

    Returns:
        Configured async session maker.

    Raises:
        RuntimeError: If init_db has not been called yet.
    """
    return _database.get_sessionmaker()


async def init_db() -> None:
    """Create the async engine and session factory."""
    await _database.init()


async def close_db() -> None:
    """Dispose the async engine and reset session factory."""
    await _database.close()


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session for dependency injection.

    Yields:
        Request-scoped async database session.
    """
    async with get_async_sessionmaker()() as session:
        yield session
