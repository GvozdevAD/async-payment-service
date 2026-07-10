"""Outbox repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox import Outbox


class OutboxRepository:
    """Data access for outbox records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, outbox: Outbox) -> Outbox:
        """Add a new outbox record to the current session."""
        self._session.add(outbox)
        return outbox
