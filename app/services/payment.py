"""Payment business logic."""

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PAYMENT_NEW_EVENT_TYPE
from app.core.exceptions import PaymentNotFoundError
from app.core.logging import get_logger
from app.db.enums import OutboxStatus, PaymentStatus
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment
from app.mappers.payment import to_create_response, to_detail_response
from app.repositories.outbox import OutboxRepository
from app.repositories.payment import PaymentRepository
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
)

logger = get_logger(__name__)


class PaymentService:
    """Create and retrieve payments with outbox event recording."""

    def __init__(
        self,
        session: AsyncSession,
        payment_repo: PaymentRepository,
        outbox_repo: OutboxRepository,
    ) -> None:
        self._session = session
        self._payment_repo = payment_repo
        self._outbox_repo = outbox_repo

    async def create_payment(
        self,
        data: PaymentCreateRequest,
        idempotency_key: str,
    ) -> PaymentCreateResponse:
        """Create a payment or return an existing one for the idempotency key.

        Args:
            data: Validated payment creation payload.
            idempotency_key: Unique key for duplicate request protection.

        Returns:
            The created or existing payment summary.

        Raises:
            IntegrityError: If commit fails for a non-idempotency reason.
        """
        existing = await self._payment_repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return to_create_response(existing)

        payment = Payment(
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            metadata_=data.metadata,
            webhook_url=str(data.webhook_url),
            idempotency_key=idempotency_key,
            status=PaymentStatus.PENDING,
        )
        await self._payment_repo.create(payment)
        await self._session.flush()

        outbox = Outbox(
            aggregate_id=payment.id,
            event_type=PAYMENT_NEW_EVENT_TYPE,
            payload=self._build_outbox_payload(payment),
            status=OutboxStatus.PENDING,
        )
        await self._outbox_repo.create(outbox)

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._payment_repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.debug(
                    "Idempotency race resolved for key=%s payment_id=%s",
                    idempotency_key,
                    existing.id,
                )
                return to_create_response(existing)
            logger.warning(
                "Unexpected integrity error while creating payment key=%s",
                idempotency_key,
                exc_info=exc,
            )
            raise

        await self._session.refresh(payment)
        return to_create_response(payment)

    async def get_payment(self, payment_id: uuid.UUID) -> PaymentDetailResponse:
        """Return payment details or raise if not found."""
        payment = await self._payment_repo.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError()
        return to_detail_response(payment)

    @staticmethod
    def _build_outbox_payload(payment: Payment) -> dict[str, Any]:
        """Build the outbox event payload for a new payment."""
        return {
            "payment_id": str(payment.id),
            "amount": str(payment.amount),
            "currency": payment.currency.value,
            "webhook_url": payment.webhook_url,
        }
