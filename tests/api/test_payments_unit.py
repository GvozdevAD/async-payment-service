"""Payment API unit tests without PostgreSQL."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.api.v1.payments import _validate_idempotency_key, create_payment, get_payment
from app.core.exceptions import ValidationAppError
from app.db.enums import Currency, PaymentStatus
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
)


def test_validate_idempotency_key_rejects_empty_string() -> None:
    """Empty idempotency key should fail validation."""
    with pytest.raises(ValueError, match="1 and 255"):
        _validate_idempotency_key("")


def test_validate_idempotency_key_rejects_non_ascii() -> None:
    """Non-ASCII idempotency key should fail validation."""
    with pytest.raises(ValueError, match="printable ASCII"):
        _validate_idempotency_key("ключ-emoji")


def test_validate_idempotency_key_accepts_printable_ascii() -> None:
    """Valid printable ASCII idempotency key should be returned unchanged."""
    assert _validate_idempotency_key("order-123") == "order-123"


async def test_create_payment_raises_validation_error_for_empty_key(
    payment_payload: dict[str, object],
) -> None:
    """create_payment should map empty idempotency key to ValidationAppError."""
    body = PaymentCreateRequest.model_validate(payment_payload)
    service = AsyncMock()

    with pytest.raises(ValidationAppError, match="1 and 255"):
        await create_payment(body, "", service)

    service.create_payment.assert_not_called()


async def test_create_payment_raises_validation_error_for_non_ascii_key(
    payment_payload: dict[str, object],
) -> None:
    """create_payment should map non-ASCII idempotency key to ValidationAppError."""
    body = PaymentCreateRequest.model_validate(payment_payload)
    service = AsyncMock()

    with pytest.raises(ValidationAppError, match="printable ASCII"):
        await create_payment(body, "ключ-emoji", service)

    service.create_payment.assert_not_called()


async def test_create_payment_delegates_to_service(
    payment_payload: dict[str, object],
) -> None:
    """create_payment should validate the key and delegate to PaymentService."""
    body = PaymentCreateRequest.model_validate(payment_payload)
    expected = PaymentCreateResponse(
        payment_id=uuid.uuid4(),
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    service = AsyncMock()
    service.create_payment = AsyncMock(return_value=expected)

    result = await create_payment(body, "valid-idempotency-key", service)

    assert result == expected
    service.create_payment.assert_awaited_once_with(body, "valid-idempotency-key")


async def test_get_payment_delegates_to_service() -> None:
    """get_payment should delegate lookup to PaymentService."""
    payment_id = uuid.uuid4()
    expected = PaymentDetailResponse(
        payment_id=payment_id,
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="Unit test",
        metadata={},
        status=PaymentStatus.PENDING,
        webhook_url="https://example.com/webhook",
        created_at=datetime.now(UTC),
        processed_at=None,
    )
    service = AsyncMock()
    service.get_payment = AsyncMock(return_value=expected)

    result = await get_payment(payment_id, service)

    assert result == expected
    service.get_payment.assert_awaited_once_with(payment_id)
