"""FastAPI application lifespan tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.main import app, lifespan


@pytest.fixture(autouse=True)
async def reset_db_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset database module state after lifespan tests."""
    import app.db.session as session_module

    monkeypatch.setattr(session_module, "_engine", None, raising=False)
    monkeypatch.setattr(session_module, "_async_session", None, raising=False)
    yield
    monkeypatch.setattr(session_module, "_engine", None, raising=False)
    monkeypatch.setattr(session_module, "_async_session", None, raising=False)


async def test_lifespan_without_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifespan should skip publisher when outbox_publisher_enabled is false."""
    mock_init_db = AsyncMock()
    mock_close_db = AsyncMock()
    monkeypatch.setattr("app.main.init_db", mock_init_db)
    monkeypatch.setattr("app.main.close_db", mock_close_db)
    monkeypatch.setattr("app.main.setup_logging", MagicMock())
    monkeypatch.setenv("OUTBOX_PUBLISHER_ENABLED", "false")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    async with lifespan(app):
        pass

    mock_init_db.assert_awaited_once()
    mock_close_db.assert_awaited_once()


async def test_lifespan_with_publisher_starts_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifespan should start publisher task and stop it on shutdown."""
    mock_init_db = AsyncMock()
    mock_close_db = AsyncMock()
    mock_publisher = MagicMock()
    mock_publisher.start = AsyncMock()
    mock_publisher.stop = AsyncMock()

    async def fake_run_forever() -> None:
        await asyncio.Event().wait()

    mock_publisher.run_forever = fake_run_forever
    monkeypatch.setattr("app.main.init_db", mock_init_db)
    monkeypatch.setattr("app.main.close_db", mock_close_db)
    monkeypatch.setattr("app.main.setup_logging", MagicMock())
    monkeypatch.setattr("app.main.create_broker", MagicMock())
    monkeypatch.setattr("app.main.get_async_sessionmaker", MagicMock())
    monkeypatch.setattr(
        "app.main.create_outbox_publisher",
        MagicMock(return_value=mock_publisher),
    )
    monkeypatch.setenv("OUTBOX_PUBLISHER_ENABLED", "true")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    async with lifespan(app):
        mock_publisher.start.assert_awaited_once()

    mock_publisher.stop.assert_awaited_once()
    mock_close_db.assert_awaited_once()


async def test_lifespan_cancels_publisher_task_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publisher background task should be cancelled during lifespan teardown."""
    mock_publisher = MagicMock()
    mock_publisher.start = AsyncMock()
    mock_publisher.stop = AsyncMock()
    cancelled = asyncio.Event()

    async def fake_run_forever() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_publisher.run_forever = fake_run_forever
    monkeypatch.setattr("app.main.init_db", AsyncMock())
    monkeypatch.setattr("app.main.close_db", AsyncMock())
    monkeypatch.setattr("app.main.setup_logging", MagicMock())
    monkeypatch.setattr("app.main.create_broker", MagicMock())
    monkeypatch.setattr("app.main.get_async_sessionmaker", MagicMock())
    monkeypatch.setattr(
        "app.main.create_outbox_publisher",
        MagicMock(return_value=mock_publisher),
    )
    monkeypatch.setenv("OUTBOX_PUBLISHER_ENABLED", "true")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    async with lifespan(app):
        await asyncio.sleep(0)

    assert cancelled.is_set()
