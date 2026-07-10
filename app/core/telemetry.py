"""OpenTelemetry tracing and metrics setup."""

from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import metrics as metrics_api
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.metrics import init_metrics
from app.core.settings import Settings


@dataclass
class ObservabilityHandles:
    """Handles returned from observability setup for shutdown."""

    enabled: bool


class Observability:
    """Process-wide OpenTelemetry tracing and metrics state.

    Encapsulates provider lifecycle and idempotent auto-instrumentation so the
    module exposes a single instance instead of mutable module-level globals.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self._instrumented_fastapi = False
        self._instrumented_sqlalchemy = False
        self._instrumented_httpx = False
        self._instrumented_logging = False

    @property
    def enabled(self) -> bool:
        """Return whether OpenTelemetry export is enabled."""
        return self._enabled

    def setup(self, *, service_name: str, settings: Settings) -> ObservabilityHandles:
        """Configure OTel tracing and metrics export when enabled.

        Args:
            service_name: Logical service name for the current process.
            settings: Application settings with OTel configuration.

        Returns:
            Handles used during graceful shutdown.
        """
        self._enabled = settings.otel_enabled
        init_metrics(enabled=self._enabled)

        if not self._enabled:
            return ObservabilityHandles(enabled=False)

        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": settings.app_env,
            },
        )

        span_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        self._tracer_provider = TracerProvider(resource=resource)
        self._tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(self._tracer_provider)

        metric_exporter = OTLPMetricExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=settings.otel_metric_export_interval_ms,
        )
        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics_api.set_meter_provider(self._meter_provider)
        init_metrics(enabled=True)

        return ObservabilityHandles(enabled=True)

    def instrument_fastapi(self, app: FastAPI) -> None:
        """Auto-instrument a FastAPI application for HTTP tracing."""
        if not self._enabled or self._instrumented_fastapi:
            return

        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        self._instrumented_fastapi = True

    def instrument_sqlalchemy(self, engine: object) -> None:
        """Auto-instrument a SQLAlchemy engine for database tracing."""
        if not self._enabled or self._instrumented_sqlalchemy:
            return

        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
        self._instrumented_sqlalchemy = True

    def instrument_sqlalchemy_if_ready(self) -> None:
        """Auto-instrument the initialized async engine when available."""
        if not self._enabled or self._instrumented_sqlalchemy:
            return

        try:
            from app.db.session import get_engine
        except ImportError:
            return

        try:
            self.instrument_sqlalchemy(get_engine().sync_engine)
        except RuntimeError:
            return

    def instrument_httpx(self) -> None:
        """Auto-instrument httpx clients for outbound HTTP tracing."""
        if not self._enabled or self._instrumented_httpx:
            return

        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        self._instrumented_httpx = True

    def instrument_logging(self) -> None:
        """Correlate Python logs with active trace and span IDs."""
        if not self._enabled or self._instrumented_logging:
            return

        LoggingInstrumentor().instrument(set_logging_format=True)
        self._instrumented_logging = True

    def shutdown(self, handles: ObservabilityHandles | None = None) -> None:
        """Flush and shut down configured OTel providers.

        Args:
            handles: Handles returned from setup; when disabled, shutdown is a no-op.
        """
        if handles is not None and not handles.enabled:
            return

        if self._tracer_provider is not None:
            self._tracer_provider.shutdown()
            self._tracer_provider = None

        if self._meter_provider is not None:
            self._meter_provider.shutdown()
            self._meter_provider = None

        self._enabled = False
        init_metrics(enabled=False)


_observability = Observability()


def get_observability() -> Observability:
    """Return the process-wide observability instance."""
    return _observability


def is_observability_enabled() -> bool:
    """Return whether OpenTelemetry export is enabled."""
    return _observability.enabled


def setup_observability(
    *,
    service_name: str,
    settings: Settings,
) -> ObservabilityHandles:
    """Configure OTel tracing and metrics export when enabled.

    Args:
        service_name: Logical service name for the current process.
        settings: Application settings with OTel configuration.

    Returns:
        Handles used during graceful shutdown.
    """
    return _observability.setup(service_name=service_name, settings=settings)


def instrument_fastapi(app: FastAPI) -> None:
    """Auto-instrument a FastAPI application for HTTP tracing."""
    _observability.instrument_fastapi(app)


def instrument_sqlalchemy(engine: object) -> None:
    """Auto-instrument a SQLAlchemy engine for database tracing."""
    _observability.instrument_sqlalchemy(engine)


def instrument_sqlalchemy_if_ready() -> None:
    """Auto-instrument the initialized async engine when available."""
    _observability.instrument_sqlalchemy_if_ready()


def instrument_httpx() -> None:
    """Auto-instrument httpx clients for outbound HTTP tracing."""
    _observability.instrument_httpx()


def instrument_logging() -> None:
    """Correlate Python logs with active trace and span IDs."""
    _observability.instrument_logging()


def shutdown_observability(handles: ObservabilityHandles | None = None) -> None:
    """Flush and shut down configured OTel providers."""
    _observability.shutdown(handles)
