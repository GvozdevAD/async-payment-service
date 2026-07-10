"""Outbox repository integration tests."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PAYMENT_NEW_EVENT_TYPE
from app.db.enums import Currency, OutboxStatus, PaymentStatus
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment
from app.repositories.outbox import OutboxRepository


@pytest.fixture
def outbox_repo(db_session: AsyncSession) -> OutboxRepository:
    """Return an outbox repository bound to the test session."""
    return OutboxRepository(db_session)


async def _create_payment(db_session: AsyncSession) -> Payment:
    """Persist a payment required as outbox aggregate."""
    payment = Payment(
        amount="10.00",
        currency=Currency.RUB,
        description="Outbox test",
        metadata_={},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"outbox-{uuid.uuid4()}",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.flush()
    return payment


async def _create_outbox(
    db_session: AsyncSession,
    payment: Payment,
    *,
    status: OutboxStatus = OutboxStatus.PENDING,
) -> Outbox:
    """Persist an outbox record for tests."""
    outbox = Outbox(
        aggregate_id=payment.id,
        event_type=PAYMENT_NEW_EVENT_TYPE,
        payload={
            "payment_id": str(payment.id),
            "amount": "10.00",
            "currency": "RUB",
            "webhook_url": "https://example.com/webhook",
        },
        status=status,
    )
    db_session.add(outbox)
    await db_session.flush()
    return outbox


async def test_get_pending_batch_returns_only_pending(
    db_session: AsyncSession,
    outbox_repo: OutboxRepository,
) -> None:
    """get_pending_batch should return pending records ordered by created_at."""
    payment = await _create_payment(db_session)
    pending = await _create_outbox(db_session, payment, status=OutboxStatus.PENDING)
    await _create_outbox(db_session, payment, status=OutboxStatus.PUBLISHED)
    await db_session.commit()

    batch = await outbox_repo.get_pending_batch(limit=10)

    assert [record.id for record in batch] == [pending.id]


async def test_mark_published_updates_status(
    db_session: AsyncSession,
    outbox_repo: OutboxRepository,
) -> None:
    """mark_published should set status and processed_at."""
    payment = await _create_payment(db_session)
    outbox = await _create_outbox(db_session, payment)
    await db_session.commit()
    processed_at = datetime.now(UTC)

    await outbox_repo.mark_published(outbox.id, processed_at=processed_at)
    await db_session.commit()
    await db_session.refresh(outbox)

    assert outbox.status == OutboxStatus.PUBLISHED
    assert outbox.processed_at == processed_at


async def test_mark_failed_updates_status(
    db_session: AsyncSession,
    outbox_repo: OutboxRepository,
) -> None:
    """mark_failed should set status to failed."""
    payment = await _create_payment(db_session)
    outbox = await _create_outbox(db_session, payment)
    await db_session.commit()
    processed_at = datetime.now(UTC)

    await outbox_repo.mark_failed(outbox.id, processed_at=processed_at)
    await db_session.commit()
    await db_session.refresh(outbox)

    assert outbox.status == OutboxStatus.FAILED
    assert outbox.processed_at == processed_at
