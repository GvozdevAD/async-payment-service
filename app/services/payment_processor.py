"""Payment queue message processing orchestration."""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import PoisonMessageError
from app.core.settings import Settings
from app.db.enums import PaymentStatus
from app.db.models.payment import Payment
from app.messaging.schemas import PaymentNewMessage
from app.repositories.payment import PaymentRepository
from app.services.gateway import GatewayEmulator, PaymentGateway
from app.services.webhook import WebhookDeliveryError, WebhookService

logger = logging.getLogger(__name__)


class PaymentProcessorService:
    """Process payment-new queue messages end-to-end."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway,
        webhook_service: WebhookService,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway
        self._webhook_service = webhook_service

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
            repo = PaymentRepository(session)
            payment = await repo.get_by_id(message.payment_id)
            if payment is None:
                msg = f"Payment not found: {message.payment_id}"
                raise PoisonMessageError(msg)

            if payment.status != PaymentStatus.PENDING:
                logger.info(
                    "Skipping gateway for non-pending payment payment_id=%s status=%s",
                    payment.id,
                    payment.status.value,
                )
                await self._send_webhook(payment)
                return

            gateway_status = await self._gateway.emulate(payment)
            processed_at = datetime.now(UTC)
            await repo.update_status(
                payment.id,
                status=gateway_status,
                processed_at=processed_at,
            )
            await session.commit()
            await session.refresh(payment)

        await self._send_webhook(payment)

    async def _send_webhook(self, payment: Payment) -> None:
        """Send webhook and swallow delivery errors after DB update."""
        try:
            await self._webhook_service.send(payment)
        except WebhookDeliveryError:
            logger.error(
                "Webhook failed after DB update payment_id=%s status=%s",
                payment.id,
                payment.status.value,
            )


def create_payment_processor(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> PaymentProcessorService:
    """Build a payment processor with default gateway and webhook services.

    Args:
        settings: Application settings for gateway and webhook services.
        session_factory: Async SQLAlchemy session factory.

    Returns:
        Configured payment processor service.
    """
    return PaymentProcessorService(
        session_factory=session_factory,
        gateway=GatewayEmulator(settings),
        webhook_service=WebhookService(settings),
    )
