"""Webhook dispatcher entrypoint tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dispatcher import main as dispatcher_main


async def test_dispatcher_main_runs_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() should start dispatcher, run forever, then stop and close DB."""
    mock_init_db = AsyncMock()
    mock_close_db = AsyncMock()
    mock_dispatcher = MagicMock()
    mock_dispatcher.start = AsyncMock()
    mock_dispatcher.run_forever = AsyncMock()
    mock_dispatcher.stop = AsyncMock()

    monkeypatch.setattr(dispatcher_main, "init_db", mock_init_db)
    monkeypatch.setattr(dispatcher_main, "close_db", mock_close_db)
    monkeypatch.setattr(dispatcher_main, "setup_logging", MagicMock())
    monkeypatch.setattr(
        dispatcher_main,
        "create_webhook_dispatcher",
        MagicMock(return_value=mock_dispatcher),
    )
    monkeypatch.setattr(
        dispatcher_main,
        "get_async_sessionmaker",
        MagicMock(),
    )

    await dispatcher_main.main()

    mock_init_db.assert_awaited_once()
    mock_dispatcher.start.assert_awaited_once()
    mock_dispatcher.run_forever.assert_awaited_once()
    mock_dispatcher.stop.assert_awaited_once()
    mock_close_db.assert_awaited_once()
