"""Outbox repository."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OutboxStatus
from app.db.models.outbox import Outbox


class OutboxRepository:
    """Data access for outbox records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, outbox: Outbox) -> Outbox:
        """Add a new outbox record to the current session.

        Args:
            outbox: Outbox ORM instance to persist.

        Returns:
            The same outbox instance attached to the session.
        """
        self._session.add(outbox)
        return outbox

    async def get_pending_batch(self, *, limit: int) -> list[Outbox]:
        """Fetch pending outbox records with row-level lock.

        Args:
            limit: Maximum number of records to return.

        Returns:
            Pending outbox records ordered by creation time.
        """
        stmt = (
            select(Outbox)
            .where(Outbox.status == OutboxStatus.PENDING)
            .order_by(Outbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_published(
        self,
        outbox_id: uuid.UUID,
        *,
        processed_at: datetime,
    ) -> None:
        """Mark outbox record as published.

        Args:
            outbox_id: Outbox record UUID.
            processed_at: Timestamp when publication completed.
        """
        await self._session.execute(
            update(Outbox)
            .where(Outbox.id == outbox_id)
            .values(
                status=OutboxStatus.PUBLISHED,
                processed_at=processed_at,
            ),
        )

    async def mark_failed(
        self,
        outbox_id: uuid.UUID,
        *,
        processed_at: datetime,
    ) -> None:
        """Mark outbox record as permanently failed.

        Args:
            outbox_id: Outbox record UUID.
            processed_at: Timestamp when processing stopped.
        """
        await self._session.execute(
            update(Outbox)
            .where(Outbox.id == outbox_id)
            .values(
                status=OutboxStatus.FAILED,
                processed_at=processed_at,
            ),
        )
