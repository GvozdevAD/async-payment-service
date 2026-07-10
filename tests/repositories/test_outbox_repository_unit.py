"""Outbox repository unit tests without PostgreSQL."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OutboxStatus
from app.db.models.outbox import Outbox
from app.repositories.outbox import OutboxRepository


def _make_outbox() -> Outbox:
    """Build an outbox ORM instance for repository unit tests."""
    return Outbox(
        id=uuid.uuid4(),
        aggregate_id=uuid.uuid4(),
        event_type="payment.new",
        payload={"payment_id": str(uuid.uuid4())},
        status=OutboxStatus.PENDING,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_create_adds_outbox_to_session() -> None:
    """create should add the outbox record to the current session."""
    outbox = _make_outbox()
    session = AsyncMock(spec=AsyncSession)
    repo = OutboxRepository(session)

    created = await repo.create(outbox)

    session.add.assert_called_once_with(outbox)
    assert created == outbox


@pytest.mark.asyncio
async def test_get_pending_batch_returns_locked_rows() -> None:
    """get_pending_batch should return pending rows from the database."""
    outbox = _make_outbox()
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [outbox]
    session.execute = AsyncMock(return_value=result)
    repo = OutboxRepository(session)

    rows = await repo.get_pending_batch(limit=10)

    assert rows == [outbox]
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_count_pending_returns_scalar_value() -> None:
    """count_pending should return the scalar count from the database."""
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one.return_value = 3
    session.execute = AsyncMock(return_value=result)
    repo = OutboxRepository(session)

    count = await repo.count_pending()

    assert count == 3
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_published_executes_update() -> None:
    """mark_published should execute an update statement."""
    outbox_id = uuid.uuid4()
    processed_at = datetime.now(UTC)
    session = AsyncMock(spec=AsyncSession)
    repo = OutboxRepository(session)

    await repo.mark_published(outbox_id, processed_at=processed_at)

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failed_executes_update() -> None:
    """mark_failed should execute an update statement."""
    outbox_id = uuid.uuid4()
    processed_at = datetime.now(UTC)
    session = AsyncMock(spec=AsyncSession)
    repo = OutboxRepository(session)

    await repo.mark_failed(outbox_id, processed_at=processed_at)

    session.execute.assert_awaited_once()
