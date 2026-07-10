"""Webhook mapper tests."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.mappers.webhook import to_webhook_payload


def _make_payment(*, processed_at: datetime | None) -> Payment:
    """Build a payment ORM instance for mapper tests."""
    return Payment(
        id=uuid.uuid4(),
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="Mapper test",
        metadata_={"k": "v"},
        webhook_url="https://example.com/webhook",
        idempotency_key="mapper-test",
        status=PaymentStatus.SUCCEEDED,
        processed_at=processed_at,
        created_at=datetime.now(UTC),
    )


def test_to_webhook_payload_maps_processed_payment() -> None:
    """Processed payment should map to a webhook payload."""
    processed_at = datetime.now(UTC)
    payment = _make_payment(processed_at=processed_at)

    payload = to_webhook_payload(payment)

    assert payload.payment_id == payment.id
    assert payload.status == PaymentStatus.SUCCEEDED
    assert payload.processed_at == processed_at


def test_to_webhook_payload_requires_processed_at() -> None:
    """Missing processed_at should raise ValueError before HTTP delivery."""
    payment = _make_payment(processed_at=None)

    with pytest.raises(ValueError, match="processed_at is required"):
        to_webhook_payload(payment)
