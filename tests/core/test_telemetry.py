"""OpenTelemetry setup and shutdown tests."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.settings.local import LocalSettings
from app.core.telemetry import (
    Observability,
    ObservabilityHandles,
    get_observability,
    instrument_fastapi,
    instrument_httpx,
    instrument_logging,
    instrument_sqlalchemy,
    instrument_sqlalchemy_if_ready,
    is_observability_enabled,
    setup_observability,
    shutdown_observability,
)


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure valid settings environment variables."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://payments:payments@localhost:5432/payments",
    )
    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg://payments:payments@localhost:5432/payments",
    )
    monkeypatch.setenv(
        "RABBITMQ_URL", "amqp://payments:payments@localhost:5672/payments"
    )
    monkeypatch.setenv("API_KEY", "test-api-key-16chars")
    monkeypatch.setenv("RABBITMQ_EXCHANGE", "payments")
    monkeypatch.setenv("RABBITMQ_PAYMENTS_NEW_QUEUE", "payments.new")
    monkeypatch.setenv("RABBITMQ_PAYMENTS_NEW_DLQ", "payments.new.dlq")
    monkeypatch.setenv("RABBITMQ_PAYMENTS_NEW_ROUTING_KEY", "payments.new")
    monkeypatch.setenv("OTEL_ENABLED", "false")


def test_setup_observability_disabled(valid_env: None) -> None:
    """Disabled OTel should return handles without enabling export."""
    settings = LocalSettings()

    handles = setup_observability(service_name="api", settings=settings)

    assert handles.enabled is False
    assert is_observability_enabled() is False
    shutdown_observability(handles)


def test_setup_observability_enabled(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabled OTel should configure providers and metric instruments."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    settings = LocalSettings()

    with (
        patch("app.core.telemetry.OTLPSpanExporter"),
        patch("app.core.telemetry.OTLPMetricExporter"),
        patch("app.core.telemetry.BatchSpanProcessor"),
        patch("app.core.telemetry.PeriodicExportingMetricReader"),
    ):
        handles = setup_observability(service_name="api", settings=settings)

    assert handles.enabled is True
    assert is_observability_enabled() is True
    shutdown_observability(handles)
    assert is_observability_enabled() is False


def test_module_helpers_delegate_to_singleton(valid_env: None) -> None:
    """Module-level helpers should operate on the shared observability instance."""
    settings = LocalSettings()

    handles = setup_observability(service_name="api", settings=settings)

    assert get_observability().enabled is False
    instrument_fastapi(MagicMock())
    instrument_sqlalchemy(MagicMock())
    instrument_sqlalchemy_if_ready()
    instrument_httpx()
    instrument_logging()

    shutdown_observability(handles)


def test_instrument_helpers_noop_when_disabled() -> None:
    """Auto-instrumentation helpers should no-op when OTel is disabled."""
    observability = Observability()

    observability.instrument_fastapi(MagicMock())
    observability.instrument_sqlalchemy(MagicMock())
    observability.instrument_sqlalchemy_if_ready()
    observability.instrument_httpx()
    observability.instrument_logging()

    assert observability.enabled is False


def test_instrument_helpers_run_when_enabled() -> None:
    """Auto-instrumentation helpers should run when observability is enabled."""
    observability = Observability()
    observability._enabled = True

    with (
        patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor",
        ) as fastapi_instr,
        patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor",
        ) as sqlalchemy_instr,
        patch(
            "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor",
        ) as httpx_instr,
        patch("app.core.telemetry.LoggingInstrumentor") as logging_instr,
        patch("app.db.session.get_engine", side_effect=RuntimeError),
    ):
        observability.instrument_fastapi(MagicMock())
        observability.instrument_sqlalchemy(MagicMock())
        observability.instrument_sqlalchemy_if_ready()
        observability.instrument_httpx()
        observability.instrument_logging()

    fastapi_instr.instrument_app.assert_called_once()
    sqlalchemy_instr.return_value.instrument.assert_called_once()
    httpx_instr.return_value.instrument.assert_called_once()
    logging_instr.return_value.instrument.assert_called_once()


def test_shutdown_observability_without_handles(valid_env: None) -> None:
    """Shutdown should be safe when handles are omitted."""
    shutdown_observability(None)


def test_instrument_sqlalchemy_if_ready_uses_engine() -> None:
    """instrument_sqlalchemy_if_ready should instrument when engine is ready."""
    observability = Observability()
    observability._enabled = True

    mock_engine = MagicMock()
    mock_engine.sync_engine = MagicMock()

    with (
        patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor",
        ) as sqlalchemy_instr,
        patch(
            "app.db.session.get_engine",
            return_value=mock_engine,
        ),
    ):
        observability.instrument_sqlalchemy_if_ready()

    sqlalchemy_instr.return_value.instrument.assert_called_once_with(
        engine=mock_engine.sync_engine,
    )


def test_observability_handles_dataclass() -> None:
    """ObservabilityHandles should store enabled flag."""
    handles = ObservabilityHandles(enabled=True)
    assert handles.enabled is True


def test_instrument_helpers_skip_when_already_instrumented() -> None:
    """Auto-instrumentation helpers should no-op after the first call."""
    observability = Observability()
    observability._enabled = True
    observability._instrumented_fastapi = True
    observability._instrumented_sqlalchemy = True
    observability._instrumented_httpx = True
    observability._instrumented_logging = True

    with (
        patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor",
        ) as fastapi_instr,
        patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor",
        ) as sqlalchemy_instr,
        patch(
            "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor",
        ) as httpx_instr,
        patch("app.core.telemetry.LoggingInstrumentor") as logging_instr,
    ):
        observability.instrument_fastapi(MagicMock())
        observability.instrument_sqlalchemy(MagicMock())
        observability.instrument_sqlalchemy_if_ready()
        observability.instrument_httpx()
        observability.instrument_logging()

    fastapi_instr.assert_not_called()
    sqlalchemy_instr.assert_not_called()
    httpx_instr.assert_not_called()
    logging_instr.assert_not_called()


def test_instrument_sqlalchemy_if_ready_ignores_runtime_error() -> None:
    """instrument_sqlalchemy_if_ready should ignore uninitialized database engine."""
    observability = Observability()
    observability._enabled = True

    mock_engine = MagicMock()
    mock_engine.sync_engine = MagicMock()

    with (
        patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor",
        ) as sqlalchemy_instr,
        patch(
            "app.db.session.get_engine",
            return_value=mock_engine,
        ),
        patch.object(
            observability,
            "instrument_sqlalchemy",
            side_effect=RuntimeError("engine not ready"),
        ),
    ):
        observability.instrument_sqlalchemy_if_ready()

    sqlalchemy_instr.assert_not_called()


def test_instrument_sqlalchemy_if_ready_returns_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """instrument_sqlalchemy_if_ready should return when get_engine import fails."""
    import builtins

    observability = Observability()
    observability._enabled = True

    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "app.db.session":
            msg = "forced import error"
            raise ImportError(msg)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor",
    ) as sqlalchemy_instr:
        observability.instrument_sqlalchemy_if_ready()

    sqlalchemy_instr.assert_not_called()
