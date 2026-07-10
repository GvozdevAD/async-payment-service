"""Publisher entrypoint tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.publisher import main as publisher_main


async def test_publisher_main_runs_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() should start publisher, run forever, then stop and close DB."""
    mock_init_db = AsyncMock()
    mock_close_db = AsyncMock()
    mock_publisher = MagicMock()
    mock_publisher.start = AsyncMock()
    mock_publisher.run_forever = AsyncMock()
    mock_publisher.stop = AsyncMock()

    monkeypatch.setattr(publisher_main, "init_db", mock_init_db)
    monkeypatch.setattr(publisher_main, "close_db", mock_close_db)
    monkeypatch.setattr(publisher_main, "setup_logging", MagicMock())
    monkeypatch.setattr(publisher_main, "create_broker", MagicMock())
    monkeypatch.setattr(
        publisher_main,
        "create_outbox_publisher",
        MagicMock(return_value=mock_publisher),
    )
    monkeypatch.setattr(
        publisher_main,
        "get_async_sessionmaker",
        MagicMock(),
    )

    await publisher_main.main()

    mock_init_db.assert_awaited_once()
    mock_publisher.start.assert_awaited_once()
    mock_publisher.run_forever.assert_awaited_once()
    mock_publisher.stop.assert_awaited_once()
    mock_close_db.assert_awaited_once()
