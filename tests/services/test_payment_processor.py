"""Payment processor unit tests."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import PoisonMessageError
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.messaging.schemas import PaymentNewMessage
from app.services.payment_processor import PaymentProcessorService
from app.services.webhook import WebhookDeliveryError


def _make_payment(
    *,
    payment_id: uuid.UUID | None = None,
    status: PaymentStatus = PaymentStatus.PENDING,
    processed_at: datetime | None = None,
) -> Payment:
    """Build a payment ORM instance for processor tests."""
    return Payment(
        id=payment_id or uuid.uuid4(),
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Processor test",
        metadata_={"order_id": "42"},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"processor-{payment_id or uuid.uuid4()}",
        status=status,
        processed_at=processed_at,
        created_at=datetime.now(UTC),
    )


def _make_message(payment_id: uuid.UUID) -> PaymentNewMessage:
    """Build a queue message for processor tests."""
    return PaymentNewMessage(
        outbox_id=uuid.uuid4(),
        event_type="payment.new",
        payment_id=payment_id,
        amount="100.50",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )


@pytest.fixture
async def processor_factory(
    db_session: AsyncSession,
) -> tuple[async_sessionmaker[AsyncSession], AsyncMock, AsyncMock]:
    """Return a session factory and mocked gateway/webhook services."""
    engine = db_session.bind
    assert engine is not None
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    gateway = AsyncMock()
    gateway.emulate = AsyncMock(return_value=PaymentStatus.SUCCEEDED)
    webhook = AsyncMock()
    webhook.send = AsyncMock()
    return session_factory, gateway, webhook


async def test_process_happy_path(
    db_session: AsyncSession,
    processor_factory: tuple[async_sessionmaker[AsyncSession], AsyncMock, AsyncMock],
) -> None:
    """Pending payment should be processed and webhook sent."""
    payment = _make_payment()
    db_session.add(payment)
    await db_session.commit()

    session_factory, gateway, webhook = processor_factory
    processor = PaymentProcessorService(session_factory, gateway, webhook)

    await processor.process(_make_message(payment.id))

    await db_session.refresh(payment)
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None
    gateway.emulate.assert_awaited_once()
    webhook.send.assert_awaited_once()


async def test_process_gateway_failed(
    db_session: AsyncSession,
    processor_factory: tuple[async_sessionmaker[AsyncSession], AsyncMock, AsyncMock],
) -> None:
    """Failed gateway result should still trigger webhook delivery."""
    payment = _make_payment()
    db_session.add(payment)
    await db_session.commit()

    session_factory, gateway, webhook = processor_factory
    gateway.emulate = AsyncMock(return_value=PaymentStatus.FAILED)
    processor = PaymentProcessorService(session_factory, gateway, webhook)

    await processor.process(_make_message(payment.id))

    await db_session.refresh(payment)
    assert payment.status == PaymentStatus.FAILED
    webhook.send.assert_awaited_once()


async def test_process_idempotent_skips_gateway(
    db_session: AsyncSession,
    processor_factory: tuple[async_sessionmaker[AsyncSession], AsyncMock, AsyncMock],
) -> None:
    """Non-pending payments should skip gateway and only send webhook."""
    processed_at = datetime.now(UTC)
    payment = _make_payment(
        status=PaymentStatus.SUCCEEDED,
        processed_at=processed_at,
    )
    db_session.add(payment)
    await db_session.commit()

    session_factory, gateway, webhook = processor_factory
    processor = PaymentProcessorService(session_factory, gateway, webhook)

    await processor.process(_make_message(payment.id))

    gateway.emulate.assert_not_awaited()
    webhook.send.assert_awaited_once()


async def test_process_poison_message(
    processor_factory: tuple[async_sessionmaker[AsyncSession], AsyncMock, AsyncMock],
) -> None:
    """Missing payment should raise PoisonMessageError."""
    session_factory, gateway, webhook = processor_factory
    processor = PaymentProcessorService(session_factory, gateway, webhook)

    with pytest.raises(PoisonMessageError):
        await processor.process(_make_message(uuid.uuid4()))


async def test_webhook_failure_still_after_db_update(
    db_session: AsyncSession,
    processor_factory: tuple[async_sessionmaker[AsyncSession], AsyncMock, AsyncMock],
) -> None:
    """Webhook errors should not roll back the payment status update."""
    payment = _make_payment()
    db_session.add(payment)
    await db_session.commit()

    session_factory, gateway, webhook = processor_factory
    webhook.send = AsyncMock(side_effect=WebhookDeliveryError("failed"))
    processor = PaymentProcessorService(session_factory, gateway, webhook)

    await processor.process(_make_message(payment.id))

    await db_session.refresh(payment)
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None
