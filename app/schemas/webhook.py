"""Webhook notification schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.enums import PaymentStatus


class WebhookPayload(BaseModel):
    """JSON body sent to the client webhook URL."""

    payment_id: uuid.UUID
    status: PaymentStatus
    amount: str
    currency: str
    description: str
    metadata: dict[str, Any]
    processed_at: datetime
