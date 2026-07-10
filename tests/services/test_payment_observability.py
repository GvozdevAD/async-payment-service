"""Payment service observability tests."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from app.core.propagation import TRACE_CONTEXT_KEY
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.services.payment import PaymentService


def _make_payment() -> Payment:
    """Build a payment ORM instance for observability tests."""
    return Payment(
        id=uuid.uuid4(),
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="Observability test",
        metadata_={},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"obs-{uuid.uuid4()}",
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )


def test_build_outbox_payload_includes_trace_context_when_span_active() -> None:
    """Outbox payload should capture trace context from the active span."""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("create_payment"):
        payload = PaymentService._build_outbox_payload(_make_payment())

    assert TRACE_CONTEXT_KEY in payload
    assert payload[TRACE_CONTEXT_KEY]
