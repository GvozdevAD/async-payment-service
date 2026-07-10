"""Webhook delivery repository integration tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import Currency, PaymentStatus, WebhookDeliveryStatus
from app.db.models.payment import Payment
from app.repositories.webhook_delivery import WebhookDeliveryRepository


@pytest.fixture
def webhook_repo(db_session: AsyncSession) -> WebhookDeliveryRepository:
    """Return a webhook delivery repository bound to the test session."""
    return WebhookDeliveryRepository(db_session)


async def _create_payment(db_session: AsyncSession) -> Payment:
    """Persist a payment required as webhook delivery aggregate."""
    payment = Payment(
        amount="10.00",
        currency=Currency.RUB,
        description="Webhook delivery test",
        metadata_={},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"webhook-{uuid.uuid4()}",
        status=PaymentStatus.SUCCEEDED,
        processed_at=datetime.now(UTC),
    )
    db_session.add(payment)
    await db_session.flush()
    return payment


def _payload(payment: Payment) -> dict[str, object]:
    """Build a webhook payload for tests."""
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": "10.00",
        "currency": "RUB",
        "description": payment.description,
        "metadata": {},
        "processed_at": payment.processed_at.isoformat()
        if payment.processed_at
        else None,
    }


async def test_enqueue_creates_pending_delivery(
    db_session: AsyncSession,
    webhook_repo: WebhookDeliveryRepository,
) -> None:
    """enqueue should insert a pending webhook delivery record."""
    payment = await _create_payment(db_session)
    now = datetime.now(UTC)

    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload=_payload(payment),
        next_attempt_at=now,
    )
    await db_session.commit()

    batch = await webhook_repo.get_due_batch(limit=10, now=now)
    assert len(batch) == 1
    assert batch[0].payment_id == payment.id
    assert batch[0].status == WebhookDeliveryStatus.PENDING


async def test_enqueue_is_idempotent(
    db_session: AsyncSession,
    webhook_repo: WebhookDeliveryRepository,
) -> None:
    """Duplicate enqueue for the same payment_id should be ignored."""
    payment = await _create_payment(db_session)
    now = datetime.now(UTC)
    payload = _payload(payment)

    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload=payload,
        next_attempt_at=now,
    )
    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload={"duplicate": True},
        next_attempt_at=now,
    )
    await db_session.commit()

    batch = await webhook_repo.get_due_batch(limit=10, now=now)
    assert len(batch) == 1
    assert batch[0].payload == payload


async def test_get_due_batch_respects_next_attempt_at(
    db_session: AsyncSession,
    webhook_repo: WebhookDeliveryRepository,
) -> None:
    """Only deliveries with next_attempt_at <= now should be returned."""
    payment = await _create_payment(db_session)
    now = datetime.now(UTC)

    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload=_payload(payment),
        next_attempt_at=now + timedelta(minutes=5),
    )
    await db_session.commit()

    batch = await webhook_repo.get_due_batch(limit=10, now=now)
    assert batch == []


async def test_mark_delivered_updates_status(
    db_session: AsyncSession,
    webhook_repo: WebhookDeliveryRepository,
) -> None:
    """mark_delivered should set status and processed_at."""
    payment = await _create_payment(db_session)
    now = datetime.now(UTC)
    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload=_payload(payment),
        next_attempt_at=now,
    )
    await db_session.commit()

    batch = await webhook_repo.get_due_batch(limit=1, now=now)
    delivery = batch[0]
    processed_at = datetime.now(UTC)

    await webhook_repo.mark_delivered(
        delivery.id,
        processed_at=processed_at,
        status_code=200,
    )
    await db_session.commit()
    await db_session.refresh(delivery)

    assert delivery.status == WebhookDeliveryStatus.DELIVERED
    assert delivery.processed_at == processed_at
    assert delivery.last_status_code == 200


async def test_mark_failed_updates_status(
    db_session: AsyncSession,
    webhook_repo: WebhookDeliveryRepository,
) -> None:
    """mark_failed should set status to failed."""
    payment = await _create_payment(db_session)
    now = datetime.now(UTC)
    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload=_payload(payment),
        next_attempt_at=now,
    )
    await db_session.commit()

    batch = await webhook_repo.get_due_batch(limit=1, now=now)
    delivery = batch[0]
    processed_at = datetime.now(UTC)

    await webhook_repo.mark_failed(
        delivery.id,
        processed_at=processed_at,
        status_code=503,
        error="service unavailable",
    )
    await db_session.commit()
    await db_session.refresh(delivery)

    assert delivery.status == WebhookDeliveryStatus.FAILED
    assert delivery.last_status_code == 503
    assert delivery.last_error == "service unavailable"


async def test_reschedule_updates_attempts_and_next_attempt_at(
    db_session: AsyncSession,
    webhook_repo: WebhookDeliveryRepository,
) -> None:
    """reschedule should update retry metadata while keeping status pending."""
    payment = await _create_payment(db_session)
    now = datetime.now(UTC)
    await webhook_repo.enqueue(
        payment_id=payment.id,
        url=payment.webhook_url,
        payload=_payload(payment),
        next_attempt_at=now,
    )
    await db_session.commit()

    batch = await webhook_repo.get_due_batch(limit=1, now=now)
    delivery = batch[0]
    next_attempt_at = now + timedelta(seconds=5)

    await webhook_repo.reschedule(
        delivery.id,
        attempts=1,
        next_attempt_at=next_attempt_at,
        status_code=503,
        error="retry later",
    )
    await db_session.commit()
    await db_session.refresh(delivery)

    assert delivery.status == WebhookDeliveryStatus.PENDING
    assert delivery.attempts == 1
    assert delivery.next_attempt_at == next_attempt_at
    assert delivery.last_status_code == 503
    assert delivery.last_error == "retry later"
