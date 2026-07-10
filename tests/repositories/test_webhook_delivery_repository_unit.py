"""Webhook delivery repository unit tests without PostgreSQL."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.webhook_delivery import WebhookDeliveryRepository


@pytest.mark.asyncio
async def test_enqueue_executes_insert() -> None:
    """enqueue should execute an insert statement."""
    session = AsyncMock(spec=AsyncSession)
    repo = WebhookDeliveryRepository(session)

    await repo.enqueue(
        payment_id=uuid.uuid4(),
        url="https://example.com/webhook",
        payload={"payment_id": "123"},
        next_attempt_at=datetime.now(UTC),
    )

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_due_batch_returns_locked_rows() -> None:
    """get_due_batch should return due pending deliveries."""
    delivery = MagicMock()
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [delivery]
    session.execute = AsyncMock(return_value=result)
    repo = WebhookDeliveryRepository(session)

    rows = await repo.get_due_batch(limit=5, now=datetime.now(UTC))

    assert rows == [delivery]
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_delivered_executes_update() -> None:
    """mark_delivered should execute an update statement."""
    session = AsyncMock(spec=AsyncSession)
    repo = WebhookDeliveryRepository(session)

    await repo.mark_delivered(
        uuid.uuid4(),
        processed_at=datetime.now(UTC),
        status_code=200,
    )

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failed_executes_update() -> None:
    """mark_failed should execute an update statement."""
    session = AsyncMock(spec=AsyncSession)
    repo = WebhookDeliveryRepository(session)

    await repo.mark_failed(
        uuid.uuid4(),
        processed_at=datetime.now(UTC),
        status_code=500,
        error="boom",
    )

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_reschedule_executes_update() -> None:
    """reschedule should execute an update statement."""
    session = AsyncMock(spec=AsyncSession)
    repo = WebhookDeliveryRepository(session)

    await repo.reschedule(
        uuid.uuid4(),
        attempts=2,
        next_attempt_at=datetime.now(UTC),
        status_code=503,
        error="retry later",
    )

    session.execute.assert_awaited_once()
