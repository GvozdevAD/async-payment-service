"""Payment API schemas."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment


class PaymentCreateRequest(BaseModel):
    """Request body for creating a payment."""

    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=20)
    currency: Currency
    description: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    @field_validator("amount")
    @classmethod
    def validate_amount_scale(cls, value: Decimal) -> Decimal:
        """Ensure amount has at most two decimal places."""
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            msg = "Amount must have at most 2 decimal places"
            raise ValueError(msg)
        return value


class PaymentCreateResponse(BaseModel):
    """Response body for a created or idempotent payment request."""

    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime

    @classmethod
    def from_model(cls, payment: Payment) -> "PaymentCreateResponse":
        """Build a create response from a Payment ORM instance."""
        return cls(
            payment_id=payment.id,
            status=payment.status,
            created_at=payment.created_at,
        )


class PaymentDetailResponse(BaseModel):
    """Detailed payment information."""

    payment_id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_model(cls, payment: Payment) -> "PaymentDetailResponse":
        """Build a detail response from a Payment ORM instance."""
        return cls(
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata_,
            status=payment.status,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )
