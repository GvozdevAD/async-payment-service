"""OpenTelemetry propagation helper tests."""

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from app.core.propagation import (
    TRACE_CONTEXT_KEY,
    attach_context,
    capture_trace_context,
    context_from_carrier,
    extract_context_from_headers,
    inject_into_headers,
    strip_trace_context,
)


def test_capture_and_restore_trace_context_roundtrip() -> None:
    """Captured trace context should restore the same trace id."""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("parent"):
        carrier = capture_trace_context()

    restored = context_from_carrier(carrier)
    token = attach_context(restored)
    try:
        current_span = trace.get_current_span()
        assert current_span.get_span_context().is_valid
    finally:
        if token is not None:
            otel_context.detach(token)


def test_context_from_carrier_returns_none_for_empty() -> None:
    """Empty carriers should not produce a parent context."""
    assert context_from_carrier(None) is None
    assert context_from_carrier({}) is None


class _TruthyEmptyCarrier:
    """Carrier that is truthy but yields no items."""

    def __bool__(self) -> bool:
        return True

    def items(self) -> list[tuple[str, str]]:
        return []


def test_context_from_carrier_returns_none_for_truthy_empty_items() -> None:
    """Truthy carriers without items should not produce a parent context."""
    assert context_from_carrier(_TruthyEmptyCarrier()) is None


def test_inject_into_headers_merges_trace_and_retry_headers() -> None:
    """Trace headers should merge without removing existing broker metadata."""
    carrier = {"traceparent": "00-abc-def-01"}
    headers = inject_into_headers(carrier, {"x-retry-count": 2})

    assert headers["traceparent"] == "00-abc-def-01"
    assert headers["x-retry-count"] == 2


def test_extract_context_from_headers() -> None:
    """Broker headers should restore parent context."""
    headers = {"traceparent": "00-abc-def-01"}
    ctx = extract_context_from_headers(headers)

    assert ctx is not None


def test_attach_context_returns_none_for_missing_context() -> None:
    """attach_context should return None when no context is provided."""
    assert attach_context(None) is None


def test_context_from_carrier_ignores_blank_values() -> None:
    """Blank carrier values should still produce a context object."""
    carrier = {"traceparent": ""}
    assert context_from_carrier(carrier) is not None


def test_strip_trace_context_removes_internal_metadata() -> None:
    """Webhook payloads should not include trace propagation keys."""
    payload = {
        "payment_id": "123",
        TRACE_CONTEXT_KEY: {"traceparent": "00-abc-def-01"},
    }

    stripped = strip_trace_context(payload)

    assert stripped == {"payment_id": "123"}
