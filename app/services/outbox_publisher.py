"""Outbox event publisher service."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aio_pika.exceptions import AMQPError
from faststream.rabbit import RabbitBroker
from opentelemetry import trace
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger
from app.core.metrics import set_outbox_pending
from app.core.propagation import (
    TRACE_CONTEXT_KEY,
    context_from_carrier,
    inject_into_headers,
)
from app.core.settings import Settings
from app.mappers.outbox import to_payment_new_message
from app.messaging.schemas import PaymentNewMessage
from app.messaging.topology import declare_topology
from app.repositories.outbox import OutboxRepository

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

TRANSIENT_PUBLISH_ERRORS = (AMQPError, ConnectionError, OSError, TimeoutError)


class OutboxPublisherService:
    """Poll pending outbox records and publish them to RabbitMQ."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        broker: RabbitBroker,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._settings = settings
        self._retry_publish = self._build_retry_publish()

    async def start(self) -> None:
        """Connect to RabbitMQ and declare topology."""
        await self._broker.start()
        await declare_topology(self._broker, self._settings)

    async def stop(self) -> None:
        """Close the RabbitMQ broker connection."""
        await self._broker.stop()

    async def publish_pending(self) -> int:
        """Process up to one batch of pending outbox records.

        Returns:
            Number of successfully published messages in this batch.
        """
        published_count = 0
        for _ in range(self._settings.outbox_batch_size):
            result = await self._publish_next()
            if result is None:
                break
            if result:
                published_count += 1
        await self._refresh_outbox_pending()
        return published_count

    async def run_forever(self) -> None:
        """Poll outbox records until the task is cancelled.

        Raises:
            asyncio.CancelledError: When the background task is cancelled.
        """
        try:
            while True:
                try:
                    await self.publish_pending()
                except Exception:
                    logger.exception("Outbox publisher iteration failed")
                await asyncio.sleep(self._settings.outbox_poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Outbox publisher stopped")
            raise

    async def _refresh_outbox_pending(self) -> None:
        """Update the cached pending outbox gauge from the database."""
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            pending_count = await repo.count_pending()
            set_outbox_pending(pending_count)

    async def _publish_next(self) -> bool | None:
        """Publish the next pending outbox record if available.

        Returns:
            True if a message was published, False if processing stopped
            without publishing (transient error or poison pill), None if the
            queue is empty.
        """
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            async with session.begin():
                records = await repo.get_pending_batch(limit=1)
                if not records:
                    return None

                outbox = records[0]
                processed_at = datetime.now(UTC)
                trace_carrier = outbox.payload.get(TRACE_CONTEXT_KEY)
                parent_ctx = (
                    context_from_carrier(trace_carrier)
                    if isinstance(trace_carrier, dict)
                    else None
                )
                span_attributes = {
                    "outbox.id": str(outbox.id),
                    "payment.id": str(outbox.payload.get("payment_id", "")),
                }
                with tracer.start_as_current_span(
                    "outbox.publish",
                    context=parent_ctx,
                    attributes=span_attributes,
                ):
                    try:
                        message = to_payment_new_message(outbox)
                        await self._retry_publish(message, trace_carrier)
                    except ValidationError:
                        logger.exception(
                            "Invalid outbox payload outbox_id=%s event_type=%s",
                            outbox.id,
                            outbox.event_type,
                        )
                        await repo.mark_failed(outbox.id, processed_at=processed_at)
                        return False
                    except TRANSIENT_PUBLISH_ERRORS:
                        logger.exception(
                            "Transient publish error outbox_id=%s event_type=%s; "
                            "will retry on next poll",
                            outbox.id,
                            outbox.event_type,
                        )
                        return False

                    await repo.mark_published(outbox.id, processed_at=processed_at)
                    logger.info(
                        "Published outbox event outbox_id=%s payment_id=%s "
                        "event_type=%s",
                        outbox.id,
                        message.payment_id,
                        outbox.event_type,
                    )
                    return True

    def _build_retry_publish(
        self,
    ) -> Callable[[PaymentNewMessage, dict[str, Any] | None], Awaitable[None]]:
        """Build a retry wrapper configured from application settings."""

        @retry(
            stop=stop_after_attempt(self._settings.outbox_publish_max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(TRANSIENT_PUBLISH_ERRORS),
            reraise=True,
        )
        async def publish(
            message: PaymentNewMessage,
            trace_carrier: dict[str, Any] | None,
        ) -> None:
            headers: dict[str, Any] | None = None
            if isinstance(trace_carrier, dict) and trace_carrier:
                headers = inject_into_headers(
                    {str(key): str(value) for key, value in trace_carrier.items()},
                    {},
                )
            await self._broker.publish(
                message.model_dump(mode="json"),
                exchange=self._settings.rabbitmq_exchange,
                routing_key=self._settings.rabbitmq_payments_new_routing_key,
                headers=headers,
            )

        return publish


def create_outbox_publisher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    broker: RabbitBroker,
) -> OutboxPublisherService:
    """Build an outbox publisher service from application dependencies.

    Args:
        settings: Application settings for polling and retry behavior.
        session_factory: Async SQLAlchemy session factory.
        broker: FastStream RabbitMQ broker for event publication.

    Returns:
        Configured outbox publisher service.
    """
    return OutboxPublisherService(
        session_factory=session_factory,
        broker=broker,
        settings=settings,
    )
