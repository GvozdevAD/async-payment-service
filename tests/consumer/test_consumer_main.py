"""Consumer entrypoint tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.consumer import main as consumer_main
from app.core.telemetry import ObservabilityHandles


async def test_consumer_main_startup_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() should initialize DB, register handlers, run app, and close DB."""
    mock_init_db = AsyncMock()
    mock_close_db = AsyncMock()
    mock_declare_topology = AsyncMock()
    mock_processor = MagicMock()
    mock_create_processor = MagicMock(return_value=mock_processor)
    mock_register_handlers = MagicMock()

    mock_app = MagicMock()
    mock_app.run = AsyncMock()
    mock_faststream = MagicMock(return_value=mock_app)

    monkeypatch.setattr(consumer_main, "init_db", mock_init_db)
    monkeypatch.setattr(consumer_main, "close_db", mock_close_db)
    monkeypatch.setattr(consumer_main, "declare_topology", mock_declare_topology)
    monkeypatch.setattr(
        consumer_main, "create_payment_processor", mock_create_processor
    )
    monkeypatch.setattr(consumer_main, "register_handlers", mock_register_handlers)
    monkeypatch.setattr(consumer_main, "FastStream", mock_faststream)
    monkeypatch.setattr(consumer_main, "setup_logging", MagicMock())
    monkeypatch.setattr(
        consumer_main,
        "setup_observability",
        MagicMock(return_value=ObservabilityHandles(enabled=False)),
    )
    monkeypatch.setattr(consumer_main, "shutdown_observability", MagicMock())
    monkeypatch.setattr(consumer_main, "instrument_logging", MagicMock())
    monkeypatch.setattr(consumer_main, "instrument_sqlalchemy_if_ready", MagicMock())
    monkeypatch.setattr(consumer_main, "create_broker", MagicMock())
    monkeypatch.setattr(consumer_main, "get_async_sessionmaker", MagicMock())

    await consumer_main.main()

    mock_init_db.assert_awaited_once()
    mock_register_handlers.assert_called_once()
    mock_app.run.assert_awaited_once()
    mock_close_db.assert_awaited_once()
    mock_app.after_startup.assert_called_once()

    startup_callback = mock_app.after_startup.call_args[0][0]
    broker = mock_register_handlers.call_args.args[0]
    settings = mock_register_handlers.call_args.args[2]
    await startup_callback()
    mock_declare_topology.assert_awaited_once_with(broker, settings)
