"""Consumer message delivery helpers."""

import logging
from typing import Any

from aio_pika import IncomingMessage
from faststream.exceptions import NackMessage, RejectMessage
from pydantic import ValidationError

from app.core.exceptions import PoisonMessageError
from app.core.settings import Settings
from app.messaging.schemas import PaymentNewMessage
from app.services.payment_processor import PaymentProcessorService

logger = logging.getLogger(__name__)

RETRY_COUNT_HEADER = "x-retry-count"


def get_delivery_count(raw_message: IncomingMessage, queue_name: str) -> int:
    """Return how many times a message was already delivered to the consumer.

    Priority:
    1. ``x-retry-count`` header set by this consumer on prior nacks.
    2. ``x-death`` count for the target queue (broker dead-letter metadata).
    3. ``0`` for the first delivery.

    Args:
        raw_message: Raw aio-pika incoming message with broker headers.
        queue_name: Queue name used to match x-death entries.

    Returns:
        Number of prior delivery attempts before the current one.
    """
    headers = raw_message.headers or {}
    retry_count = headers.get(RETRY_COUNT_HEADER)
    if isinstance(retry_count, int):
        return retry_count

    x_death = headers.get("x-death")
    if x_death:
        for entry in x_death:
            if entry.get("queue") == queue_name:
                count = entry.get("count", 0)
                if isinstance(count, int):
                    return count

    return 0


def set_retry_count(raw_message: IncomingMessage, retry_count: int) -> None:
    """Persist the retry counter in message headers before nack/requeue.

    Args:
        raw_message: Raw aio-pika incoming message to annotate.
        retry_count: Attempt count to store in ``x-retry-count``.
    """
    headers: dict[str, Any] = dict(raw_message.headers or {})
    headers[RETRY_COUNT_HEADER] = retry_count
    raw_message.headers = headers


async def handle_payment_new_message(
    message: PaymentNewMessage,
    *,
    processor: PaymentProcessorService,
    settings: Settings,
    delivery_count: int = 0,
    raw_message: IncomingMessage | None = None,
) -> None:
    """Process a payment-new message and map failures to broker ack actions.

    Args:
        message: Validated payment-new event from the queue.
        processor: Service that orchestrates gateway, DB, and webhook steps.
        settings: Application settings including consumer retry limits.
        delivery_count: Number of prior delivery attempts for this message.
        raw_message: Optional raw broker message for retry header updates.

    Raises:
        RejectMessage: For poison messages or after max delivery attempts.
        NackMessage: For transient errors before max delivery attempts.
    """
    try:
        await processor.process(message)
    except (PoisonMessageError, ValidationError) as exc:
        raise RejectMessage(requeue=False) from exc
    except Exception as exc:
        next_attempt = delivery_count + 1
        if next_attempt >= settings.consumer_max_attempts:
            logger.error(
                "Rejecting message to DLQ after max attempts "
                "payment_id=%s delivery_count=%d",
                message.payment_id,
                delivery_count,
                exc_info=exc,
            )
            raise RejectMessage(requeue=False) from exc
        if raw_message is not None:
            set_retry_count(raw_message, next_attempt)
        logger.warning(
            "Transient error, nacking with requeue "
            "payment_id=%s delivery_count=%d attempt=%d/%d",
            message.payment_id,
            delivery_count,
            next_attempt,
            settings.consumer_max_attempts,
            exc_info=exc,
        )
        raise NackMessage(requeue=True) from exc
