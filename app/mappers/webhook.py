"""Mappers for webhook payloads."""

from app.db.models.payment import Payment
from app.schemas.webhook import WebhookPayload


def to_webhook_payload(payment: Payment) -> WebhookPayload:
    """Build a webhook payload from a processed payment.

    Args:
        payment: Processed payment ORM instance.

    Returns:
        Serializable webhook payload for HTTP delivery.

    Raises:
        ValueError: If processed_at is not set on the payment.
    """
    if payment.processed_at is None:
        msg = "Payment processed_at is required for webhook delivery"
        raise ValueError(msg)

    return WebhookPayload(
        payment_id=payment.id,
        status=payment.status,
        amount=str(payment.amount),
        currency=payment.currency.value,
        description=payment.description,
        metadata=payment.metadata_,
        processed_at=payment.processed_at,
    )
