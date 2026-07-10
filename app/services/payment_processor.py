"""Payment queue message processing orchestration."""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import PoisonMessageError
from app.core.propagation import TRACE_CONTEXT_KEY, capture_trace_context
from app.core.settings import Settings
from app.db.enums import PaymentStatus
from app.db.models.payment import Payment
from app.mappers.webhook import to_webhook_payload
from app.messaging.schemas import PaymentNewMessage
from app.repositories.payment import PaymentRepository
from app.repositories.webhook_delivery import WebhookDeliveryRepository
from app.services.gateway import GatewayEmulator, PaymentGateway

logger = logging.getLogger(__name__)


class PaymentProcessorService:
    """Process payment-new queue messages end-to-end."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway

    async def process(self, message: PaymentNewMessage) -> None:
        """Process a payment-new queue message end-to-end.

        Args:
            message: Validated payment-new event from the queue.

        Raises:
            PoisonMessageError: If the payment record does not exist.
        """
        logger.info(
            "Processing payment message payment_id=%s outbox_id=%s",
            message.payment_id,
            message.outbox_id,
        )

        async with self._session_factory() as session:
            payment_repo = PaymentRepository(session)
            webhook_repo = WebhookDeliveryRepository(session)
            payment = await payment_repo.get_by_id(message.payment_id)
            if payment is None:
                msg = f"Payment not found: {message.payment_id}"
                raise PoisonMessageError(msg)

            if payment.status != PaymentStatus.PENDING:
                logger.info(
                    "Skipping gateway for non-pending payment payment_id=%s status=%s",
                    payment.id,
                    payment.status.value,
                )
                await self._enqueue_webhook(webhook_repo, payment)
                await session.commit()
                return

            gateway_status = await self._gateway.emulate(payment)
            processed_at = datetime.now(UTC)
            await payment_repo.update_status(
                payment.id,
                status=gateway_status,
                processed_at=processed_at,
            )
            payment.status = gateway_status
            payment.processed_at = processed_at
            await self._enqueue_webhook(webhook_repo, payment)
            await session.commit()

    async def _enqueue_webhook(
        self,
        webhook_repo: WebhookDeliveryRepository,
        payment: Payment,
    ) -> None:
        """Enqueue a webhook delivery record for the payment.

        Args:
            webhook_repo: Webhook delivery repository.
            payment: Payment whose status should be delivered.
        """
        payload = to_webhook_payload(payment).model_dump(mode="json")
        trace_context = capture_trace_context()
        if trace_context:
            payload[TRACE_CONTEXT_KEY] = trace_context
        await webhook_repo.enqueue(
            payment_id=payment.id,
            url=payment.webhook_url,
            payload=payload,
            next_attempt_at=datetime.now(UTC),
        )


def create_payment_processor(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> PaymentProcessorService:
    """Build a payment processor with default gateway service.

    Args:
        settings: Application settings for gateway emulation.
        session_factory: Async SQLAlchemy session factory.

    Returns:
        Configured payment processor service.
    """
    return PaymentProcessorService(
        session_factory=session_factory,
        gateway=GatewayEmulator(settings),
    )
