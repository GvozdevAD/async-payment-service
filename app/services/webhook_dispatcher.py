"""Webhook delivery dispatcher service."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import UnsafeWebhookUrlError
from app.core.metrics import record_webhook_delivery
from app.core.propagation import (
    TRACE_CONTEXT_KEY,
    context_from_carrier,
    strip_trace_context,
)
from app.core.settings import Settings
from app.core.url_guard import ensure_webhook_destination_allowed
from app.repositories.webhook_delivery import WebhookDeliveryRepository
from app.services.webhook import WebhookService, is_retryable_exception

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def compute_backoff_seconds(attempts: int) -> float:
    """Return exponential backoff delay capped at 10 seconds.

    Args:
        attempts: Number of completed delivery attempts.

    Returns:
        Delay in seconds before the next attempt.
    """
    return min(10.0, float(2 ** max(attempts - 1, 0)))


class WebhookDispatcherService:
    """Poll pending webhook deliveries and dispatch them over HTTP."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        webhook_service: WebhookService,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._webhook_service = webhook_service
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Create the shared HTTP client for webhook delivery."""
        self._client = httpx.AsyncClient(
            timeout=self._settings.webhook_timeout_seconds,
        )
        self._webhook_service = WebhookService(
            self._settings,
            client=self._client,
        )

    async def stop(self) -> None:
        """Close the shared HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def dispatch_pending(self) -> int:
        """Process up to one batch of due webhook deliveries.

        Returns:
            Number of successfully delivered webhooks in this batch.
        """
        delivered_count = 0
        for _ in range(self._settings.webhook_dispatcher_batch_size):
            result = await self._dispatch_next()
            if result is None:
                break
            if result:
                delivered_count += 1
        return delivered_count

    async def run_forever(self) -> None:
        """Poll webhook deliveries until the task is cancelled.

        Raises:
            asyncio.CancelledError: When the background task is cancelled.
        """
        try:
            while True:
                try:
                    await self.dispatch_pending()
                except Exception:
                    logger.exception("Webhook dispatcher iteration failed")
                await asyncio.sleep(
                    self._settings.webhook_dispatcher_poll_interval_seconds
                )
        except asyncio.CancelledError:
            logger.info("Webhook dispatcher stopped")
            raise

    async def _dispatch_next(self) -> bool | None:
        """Dispatch the next due webhook delivery if available.

        Returns:
            True if a webhook was delivered, False if processing stopped
            without delivery (transient error or max attempts), None if the
            queue is empty.
        """
        async with self._session_factory() as session:
            repo = WebhookDeliveryRepository(session)
            now = datetime.now(UTC)
            async with session.begin():
                records = await repo.get_due_batch(
                    limit=1,
                    now=now,
                )
                if not records:
                    return None

                delivery = records[0]
                processed_at = datetime.now(UTC)
                trace_carrier = delivery.payload.get(TRACE_CONTEXT_KEY)
                parent_ctx = (
                    context_from_carrier(trace_carrier)
                    if isinstance(trace_carrier, dict)
                    else None
                )
                webhook_payload = strip_trace_context(delivery.payload)

                try:
                    await ensure_webhook_destination_allowed(
                        delivery.url,
                        self._settings,
                    )
                except UnsafeWebhookUrlError as exc:
                    await repo.mark_failed(
                        delivery.id,
                        processed_at=processed_at,
                        status_code=None,
                        error=str(exc),
                    )
                    record_webhook_delivery("blocked")
                    logger.error(
                        "Webhook delivery blocked by SSRF policy "
                        "delivery_id=%s payment_id=%s reason=%s",
                        delivery.id,
                        delivery.payment_id,
                        exc,
                    )
                    return False

                with tracer.start_as_current_span(
                    "webhook.dispatch",
                    context=parent_ctx,
                    attributes={"payment.id": str(delivery.payment_id)},
                ):
                    try:
                        status_code = await self._webhook_service.deliver_once(
                            delivery.url,
                            webhook_payload,
                        )
                    except Exception as exc:
                        if not is_retryable_exception(exc):
                            raise

                        next_attempts = delivery.attempts + 1
                        status_code = (
                            exc.response.status_code
                            if isinstance(exc, httpx.HTTPStatusError)
                            else None
                        )
                        error = str(exc)
                        if next_attempts >= self._settings.webhook_max_attempts:
                            await repo.mark_failed(
                                delivery.id,
                                processed_at=processed_at,
                                status_code=status_code,
                                error=error,
                            )
                            record_webhook_delivery("failed")
                            logger.error(
                                "Webhook delivery failed permanently "
                                "delivery_id=%s payment_id=%s attempts=%d",
                                delivery.id,
                                delivery.payment_id,
                                next_attempts,
                            )
                            return False

                        backoff = compute_backoff_seconds(next_attempts)
                        await repo.reschedule(
                            delivery.id,
                            attempts=next_attempts,
                            next_attempt_at=processed_at + timedelta(seconds=backoff),
                            status_code=status_code,
                            error=error,
                        )
                        logger.warning(
                            "Webhook delivery rescheduled delivery_id=%s "
                            "payment_id=%s attempt=%d/%d",
                            delivery.id,
                            delivery.payment_id,
                            next_attempts,
                            self._settings.webhook_max_attempts,
                        )
                        return False

                    await repo.mark_delivered(
                        delivery.id,
                        processed_at=processed_at,
                        status_code=status_code,
                    )
                    record_webhook_delivery("delivered")
                    current_span = trace.get_current_span()
                    if current_span.is_recording():
                        current_span.set_attribute("http.status_code", status_code)
                    logger.info(
                        "Webhook delivered delivery_id=%s payment_id=%s status_code=%s",
                        delivery.id,
                        delivery.payment_id,
                        status_code,
                    )
                    return True


def create_webhook_dispatcher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> WebhookDispatcherService:
    """Build a webhook dispatcher service from application dependencies.

    Args:
        settings: Application settings for polling and retry behavior.
        session_factory: Async SQLAlchemy session factory.

    Returns:
        Configured webhook dispatcher service.
    """
    return WebhookDispatcherService(
        session_factory=session_factory,
        webhook_service=WebhookService(settings),
        settings=settings,
    )
