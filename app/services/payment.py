"""Payment business logic."""

import uuid
from typing import Any

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.constants import PAYMENT_NEW_EVENT_TYPE
from app.core.exceptions import PaymentNotFoundError
from app.db.enums import OutboxStatus, PaymentStatus
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment
from app.repositories.outbox import OutboxRepository
from app.repositories.payment import PaymentRepository
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
)


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
        """Create a payment or return an existing one for the idempotency key."""
        existing = await self._payment_repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return PaymentCreateResponse.from_model(existing)

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
        except IntegrityError:
            await self._session.rollback()
            existing = await self._payment_repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return PaymentCreateResponse.from_model(existing)
            raise

        await self._session.refresh(payment)
        return PaymentCreateResponse.from_model(payment)

    async def get_payment(self, payment_id: uuid.UUID) -> PaymentDetailResponse:
        """Return payment details or raise if not found."""
        payment = await self._payment_repo.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError()
        return PaymentDetailResponse.from_model(payment)

    @staticmethod
    def _build_outbox_payload(payment: Payment) -> dict[str, Any]:
        """Build the outbox event payload for a new payment."""
        return {
            "payment_id": str(payment.id),
            "amount": str(payment.amount),
            "currency": payment.currency.value,
            "webhook_url": payment.webhook_url,
        }


def get_payment_service(
    session: AsyncSession = Depends(get_db),
) -> PaymentService:
    """Return a payment service bound to the request database session."""
    return PaymentService(
        session=session,
        payment_repo=PaymentRepository(session),
        outbox_repo=OutboxRepository(session),
    )
