"""Consumer message delivery helpers."""

import logging

from aio_pika import IncomingMessage
from faststream.exceptions import NackMessage, RejectMessage
from pydantic import ValidationError

from app.core.exceptions import PoisonMessageError
from app.core.settings import Settings
from app.messaging.schemas import PaymentNewMessage
from app.services.payment_processor import PaymentProcessorService

logger = logging.getLogger(__name__)


def get_delivery_count(raw_message: IncomingMessage, queue_name: str) -> int:
    """Return how many times a message was already dead-lettered or redelivered.

    Args:
        raw_message: Raw aio-pika incoming message with broker headers.
        queue_name: Queue name used to match x-death entries.

    Returns:
        Delivery attempt count derived from x-death or redelivered flag.
    """
    headers = raw_message.headers
    if headers:
        x_death = headers.get("x-death")
        if x_death:
            for entry in x_death:
                if entry.get("queue") == queue_name:
                    count = entry.get("count", 0)
                    if isinstance(count, int):
                        return count

    return 1 if raw_message.redelivered else 0


async def handle_payment_new_message(
    message: PaymentNewMessage,
    *,
    processor: PaymentProcessorService,
    settings: Settings,
    delivery_count: int = 0,
) -> None:
    """Process a payment-new message and map failures to broker ack actions.

    Args:
        message: Validated payment-new event from the queue.
        processor: Service that orchestrates gateway, DB, and webhook steps.
        settings: Application settings including consumer retry limits.
        delivery_count: Number of prior delivery attempts for this message.

    Raises:
        RejectMessage: For poison messages or after max delivery attempts.
        NackMessage: For transient errors before max delivery attempts.
    """
    try:
        await processor.process(message)
    except (PoisonMessageError, ValidationError) as exc:
        raise RejectMessage(requeue=False) from exc
    except Exception as exc:
        if delivery_count + 1 >= settings.consumer_max_attempts:
            logger.error(
                "Rejecting message to DLQ after max attempts "
                "payment_id=%s delivery_count=%d",
                message.payment_id,
                delivery_count,
                exc_info=exc,
            )
            raise RejectMessage(requeue=False) from exc
        logger.warning(
            "Transient error, nacking with requeue "
            "payment_id=%s delivery_count=%d attempt=%d/%d",
            message.payment_id,
            delivery_count,
            delivery_count + 1,
            settings.consumer_max_attempts,
            exc_info=exc,
        )
        raise NackMessage(requeue=True) from exc
