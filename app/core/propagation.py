"""W3C trace context propagation helpers."""

from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject

TRACE_CONTEXT_KEY = "trace_context"


def capture_trace_context() -> dict[str, str]:
    """Capture the active trace context as a serializable carrier.

    Returns:
        Carrier dict with W3C traceparent/tracestate keys when a span is active.
    """
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


def context_from_carrier(carrier: dict[str, Any] | None) -> Context | None:
    """Restore an OpenTelemetry context from a stored carrier dict.

    Args:
        carrier: Serialized trace context, e.g. from outbox or webhook payload.

    Returns:
        Restored context or None when carrier is empty or invalid.
    """
    if not carrier:
        return None
    string_carrier = {str(key): str(value) for key, value in carrier.items()}
    if not string_carrier:
        return None
    return extract(string_carrier)


def inject_into_headers(
    carrier: dict[str, str],
    headers: dict[str, Any],
) -> dict[str, Any]:
    """Merge W3C trace context into RabbitMQ message headers.

    Args:
        carrier: Serialized trace context from outbox payload.
        headers: Existing message headers to extend.

    Returns:
        Headers dict including trace propagation keys.
    """
    merged = dict(headers)
    for key, value in carrier.items():
        merged[key] = value
    return merged


def extract_context_from_headers(headers: dict[str, Any] | None) -> Context | None:
    """Extract parent trace context from RabbitMQ message headers.

    Args:
        headers: Raw broker message headers.

    Returns:
        Parent context for a consumer span or None when absent.
    """
    if not headers:
        return None
    return extract({str(key): str(value) for key, value in headers.items()})


def attach_context(ctx: Context | None) -> otel_context.Token | None:
    """Attach a restored context as the current context.

    Args:
        ctx: Context to attach.

    Returns:
        Token for resetting the context, or None when ctx is None.
    """
    if ctx is None:
        return None
    return otel_context.attach(ctx)


def strip_trace_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload without internal trace propagation metadata.

    Args:
        payload: Stored webhook or business payload that may include trace context.

    Returns:
        Payload safe to send to external webhook consumers.
    """
    return {key: value for key, value in payload.items() if key != TRACE_CONTEXT_KEY}
