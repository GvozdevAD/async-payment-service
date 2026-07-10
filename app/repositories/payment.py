"""Payment repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.payment import Payment


class PaymentRepository:
    """Data access for payment records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        """Return a payment by primary key."""
        result = await self._session.execute(
            select(Payment).where(Payment.id == payment_id),
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        """Return a payment by idempotency key."""
        result = await self._session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key),
        )
        return result.scalar_one_or_none()

    async def create(self, payment: Payment) -> Payment:
        """Add a new payment to the current session."""
        self._session.add(payment)
        return payment
