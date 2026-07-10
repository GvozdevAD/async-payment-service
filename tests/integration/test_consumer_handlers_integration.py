"""Consumer handler end-to-end integration tests."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from faststream.rabbit import RabbitBroker, TestRabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.consumer.handlers import register_handlers
from app.core.settings import Settings, get_settings
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.messaging.schemas import PaymentNewMessage
from app.services.payment_processor import (
    PaymentProcessorService,
    create_payment_processor,
)


@pytest.fixture
def consumer_settings() -> Settings:
    """Return application settings for consumer integration tests."""
    return get_settings()


async def _persist_pending_payment(db_session: AsyncSession) -> Payment:
    """Insert a pending payment for consumer integration tests."""
    payment = Payment(
        amount="50.00",
        currency=Currency.RUB,
        description="Consumer integration",
        metadata_={"order_id": "99"},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"consumer-{uuid.uuid4()}",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()
    return payment


def _make_queue_message(
    *,
    payment: Payment,
    outbox_id: uuid.UUID | None = None,
) -> PaymentNewMessage:
    """Build a payment-new queue message for an existing payment."""
    return PaymentNewMessage(
        outbox_id=outbox_id or uuid.uuid4(),
        event_type="payments.new",
        payment_id=payment.id,
        amount="50.00",
        currency="RUB",
        webhook_url=payment.webhook_url,
    )


@pytest.fixture
def processor_with_mocks(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[PaymentProcessorService, AsyncMock, AsyncMock]:
    """Return a real processor with mocked gateway and webhook boundaries."""
    gateway = AsyncMock()
    gateway.emulate = AsyncMock(return_value=PaymentStatus.SUCCEEDED)
    webhook = AsyncMock()
    webhook.send = AsyncMock()
    processor = PaymentProcessorService(db_session_factory, gateway, webhook)
    return processor, gateway, webhook


async def test_subscriber_processes_payment_end_to_end(
    db_session: AsyncSession,
    db_session_factory: async_sessionmaker[AsyncSession],
    consumer_settings: Settings,
    processor_with_mocks: tuple[PaymentProcessorService, AsyncMock, AsyncMock],
) -> None:
    """Published queue message should update payment status and trigger webhook."""
    payment = await _persist_pending_payment(db_session)
    processor, gateway, webhook = processor_with_mocks
    message = _make_queue_message(payment=payment)

    broker = RabbitBroker()
    register_handlers(broker, processor, consumer_settings)

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish(
            message.model_dump(mode="json"),
            queue=consumer_settings.rabbitmq_payments_new_queue,
        )

    async with db_session_factory() as verify_session:
        updated = await verify_session.get(Payment, payment.id)
        assert updated is not None
        assert updated.status == PaymentStatus.SUCCEEDED
        assert updated.processed_at is not None

    gateway.emulate.assert_awaited_once()
    webhook.send.assert_awaited_once()


async def test_subscriber_with_factory_processor_updates_payment(
    db_session: AsyncSession,
    db_session_factory: async_sessionmaker[AsyncSession],
    consumer_settings: Settings,
) -> None:
    """create_payment_processor should wire a processor that handles queue messages."""
    payment = await _persist_pending_payment(db_session)
    message = _make_queue_message(payment=payment)

    gateway = AsyncMock()
    gateway.emulate = AsyncMock(return_value=PaymentStatus.SUCCEEDED)
    webhook = AsyncMock()
    webhook.send = AsyncMock()

    with (
        patch(
            "app.services.payment_processor.GatewayEmulator",
            return_value=gateway,
        ),
        patch(
            "app.services.payment_processor.WebhookService",
            return_value=webhook,
        ),
    ):
        processor = create_payment_processor(consumer_settings, db_session_factory)

    broker = RabbitBroker()
    register_handlers(broker, processor, consumer_settings)

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish(
            message.model_dump(mode="json"),
            queue=consumer_settings.rabbitmq_payments_new_queue,
        )

    async with db_session_factory() as verify_session:
        updated = await verify_session.get(Payment, payment.id)
        assert updated is not None
        assert updated.status == PaymentStatus.SUCCEEDED

    gateway.emulate.assert_awaited_once()
    webhook.send.assert_awaited_once()


async def test_subscriber_ignores_unknown_payment_without_side_effects(
    consumer_settings: Settings,
    processor_with_mocks: tuple[PaymentProcessorService, AsyncMock, AsyncMock],
) -> None:
    """Unknown payment id should not call gateway or webhook."""
    processor, gateway, webhook = processor_with_mocks
    message = PaymentNewMessage(
        outbox_id=uuid.uuid4(),
        event_type="payments.new",
        payment_id=uuid.uuid4(),
        amount="10.00",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )

    broker = RabbitBroker()
    register_handlers(broker, processor, consumer_settings)

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish(
            message.model_dump(mode="json"),
            queue=consumer_settings.rabbitmq_payments_new_queue,
        )

    gateway.emulate.assert_not_awaited()
    webhook.send.assert_not_awaited()
