"""RabbitMQ message schemas."""

import uuid

from pydantic import BaseModel


class PaymentNewMessage(BaseModel):
    """Message published to the payments.new queue."""

    outbox_id: uuid.UUID
    event_type: str
    payment_id: uuid.UUID
    amount: str
    currency: str
    webhook_url: str
