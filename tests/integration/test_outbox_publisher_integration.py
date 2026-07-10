"""Outbox publisher integration tests with PostgreSQL."""

import uuid
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import PAYMENT_NEW_EVENT_TYPE
from app.core.settings import get_settings
from app.db.enums import Currency, OutboxStatus, PaymentStatus
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment
from app.messaging.broker import create_broker
from app.messaging.schemas import PaymentNewMessage
from app.services.outbox_publisher import create_outbox_publisher


async def _persist_pending_outbox(
    db_session: AsyncSession,
    *,
    payload: dict[str, str] | None = None,
) -> tuple[Payment, Outbox]:
    """Insert a pending payment and outbox record for publisher tests."""
    payment = Payment(
        amount="25.00",
        currency=Currency.RUB,
        description="Publisher integration",
        metadata_={"source": "integration"},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"pub-{uuid.uuid4()}",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.flush()

    outbox = Outbox(
        aggregate_id=payment.id,
        event_type=PAYMENT_NEW_EVENT_TYPE,
        payload=payload
        or {
            "payment_id": str(payment.id),
            "amount": "25.00",
            "currency": "RUB",
            "webhook_url": "https://example.com/webhook",
        },
        status=OutboxStatus.PENDING,
    )
    db_session.add(outbox)
    await db_session.commit()
    return payment, outbox


async def test_publish_pending_marks_outbox_published_in_database(
    db_session: AsyncSession,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Pending outbox row should be published to the broker and marked published in DB."""
    settings = get_settings()
    payment, outbox = await _persist_pending_outbox(db_session)

    broker = create_broker(settings.rabbitmq_url)
    broker.publish = AsyncMock()
    publisher = create_outbox_publisher(settings, db_session_factory, broker)

    published_count = await publisher.publish_pending()

    assert published_count == 1
    broker.publish.assert_awaited_once()
    published_body = broker.publish.await_args.args[0]
    assert published_body["payment_id"] == str(payment.id)

    async with db_session_factory() as verify_session:
        stored = await verify_session.get(Outbox, outbox.id)
        assert stored is not None
        assert stored.status == OutboxStatus.PUBLISHED
        assert stored.processed_at is not None


async def test_publish_pending_marks_invalid_payload_failed_in_database(
    db_session: AsyncSession,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Poison outbox payload should be marked failed without publishing to the broker."""
    settings = get_settings()
    _payment, outbox = await _persist_pending_outbox(
        db_session,
        payload={"payment_id": "not-a-valid-uuid"},
    )

    broker = create_broker(settings.rabbitmq_url)
    broker.publish = AsyncMock()
    publisher = create_outbox_publisher(settings, db_session_factory, broker)

    published_count = await publisher.publish_pending()

    assert published_count == 0
    broker.publish.assert_not_awaited()

    async with db_session_factory() as verify_session:
        stored = await verify_session.get(Outbox, outbox.id)
        assert stored is not None
        assert stored.status == OutboxStatus.FAILED
        assert stored.processed_at is not None


async def test_publish_pending_message_matches_payment_new_schema(
    db_session: AsyncSession,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Published broker payload should validate as a payment-new queue message."""
    settings = get_settings()
    payment, outbox = await _persist_pending_outbox(db_session)

    broker = create_broker(settings.rabbitmq_url)
    broker.publish = AsyncMock()
    publisher = create_outbox_publisher(settings, db_session_factory, broker)

    await publisher.publish_pending()

    message = PaymentNewMessage.model_validate(broker.publish.await_args.args[0])
    assert message.payment_id == payment.id
    assert message.outbox_id == outbox.id
    assert message.event_type == PAYMENT_NEW_EVENT_TYPE
