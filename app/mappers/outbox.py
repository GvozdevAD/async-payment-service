"""Outbox ORM to messaging schema mappers."""

from app.db.models.outbox import Outbox
from app.messaging.schemas import PaymentNewMessage


def to_payment_new_message(outbox: Outbox) -> PaymentNewMessage:
    """Map an outbox record to a payment-new queue message.

    Args:
        outbox: Outbox ORM instance with event payload.

    Returns:
        Validated message ready for publication.

    Raises:
        ValidationError: If outbox payload is invalid.
    """
    payload = outbox.payload
    return PaymentNewMessage.model_validate(
        {
            "outbox_id": outbox.id,
            "event_type": outbox.event_type,
            "payment_id": payload.get("payment_id"),
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
            "webhook_url": payload.get("webhook_url"),
        },
    )
