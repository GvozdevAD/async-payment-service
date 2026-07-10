"""Payment ORM to API schema mappers."""

from app.db.models.payment import Payment
from app.schemas.payment import PaymentCreateResponse, PaymentDetailResponse


def to_create_response(payment: Payment) -> PaymentCreateResponse:
    """Map a Payment ORM instance to a create response."""
    return PaymentCreateResponse(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


def to_detail_response(payment: Payment) -> PaymentDetailResponse:
    """Map a Payment ORM instance to a detail response."""
    return PaymentDetailResponse(
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
