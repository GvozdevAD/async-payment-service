"""Payment repository."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentStatus
from app.db.models.payment import Payment


class PaymentRepository:
    """Data access for payment records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        """Return a payment by primary key.

        Args:
            payment_id: Payment UUID.

        Returns:
            Matching payment or None if not found.
        """
        result = await self._session.execute(
            select(Payment).where(Payment.id == payment_id),
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        """Return a payment by idempotency key.

        Args:
            idempotency_key: Client-supplied idempotency key.

        Returns:
            Matching payment or None if not found.
        """
        result = await self._session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key),
        )
        return result.scalar_one_or_none()

    async def create(self, payment: Payment) -> Payment:
        """Add a new payment to the current session.

        Args:
            payment: Payment ORM instance to persist.

        Returns:
            The same payment instance attached to the session.
        """
        self._session.add(payment)
        return payment

    async def update_status(
        self,
        payment_id: uuid.UUID,
        *,
        status: PaymentStatus,
        processed_at: datetime,
    ) -> None:
        """Update payment status and processed_at timestamp.

        Args:
            payment_id: Payment UUID.
            status: New payment status.
            processed_at: Timestamp when processing completed.
        """
        await self._session.execute(
            update(Payment)
            .where(Payment.id == payment_id)
            .values(status=status, processed_at=processed_at),
        )
