"""Database session lifecycle tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import (
    close_db,
    get_async_sessionmaker,
    get_engine,
    get_session,
    init_db,
)


@pytest.fixture(autouse=True)
async def reset_db_state() -> None:
    """Reset module-level engine state between tests."""
    await close_db()
    yield
    await close_db()


def test_get_engine_before_init_raises() -> None:
    """get_engine should fail before init_db is called."""
    with pytest.raises(RuntimeError, match="not initialized"):
        get_engine()


def test_get_async_sessionmaker_before_init_raises() -> None:
    """get_async_sessionmaker should fail before init_db is called."""
    with pytest.raises(RuntimeError, match="not initialized"):
        get_async_sessionmaker()


async def test_init_close_and_get_engine(configure_test_env: None) -> None:
    """init_db should create an engine that close_db disposes."""
    await init_db()

    engine = get_engine()
    assert engine is not None
    assert get_async_sessionmaker() is not None

    await close_db()

    with pytest.raises(RuntimeError, match="not initialized"):
        get_engine()


async def test_get_session_yields_async_session(configure_test_env: None) -> None:
    """get_session should yield an initialized async session."""
    await init_db()

    gen = get_session()
    session = await gen.__anext__()

    assert isinstance(session, AsyncSession)

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
