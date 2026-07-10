"""Payment processor unit tests without PostgreSQL."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import PoisonMessageError
from app.core.propagation import TRACE_CONTEXT_KEY
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.messaging.schemas import PaymentNewMessage
from app.services.payment_processor import (
    PaymentProcessorService,
    create_payment_processor,
)


def _make_payment(*, status: PaymentStatus = PaymentStatus.PENDING) -> Payment:
    """Build a payment ORM instance for unit tests."""
    return Payment(
        id=uuid.uuid4(),
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Processor unit test",
        metadata_={},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"processor-unit-{uuid.uuid4()}",
        status=status,
        created_at=datetime.now(UTC),
    )


def _make_message(payment_id: uuid.UUID) -> PaymentNewMessage:
    """Build a queue message for unit tests."""
    return PaymentNewMessage(
        outbox_id=uuid.uuid4(),
        event_type="payment.new",
        payment_id=payment_id,
        amount="100.50",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )


async def test_process_pending_payment_enqueues_webhook_with_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Processing a pending payment should enqueue webhook with trace context."""
    payment = _make_payment()
    payment_repo = AsyncMock()
    payment_repo.get_by_id = AsyncMock(return_value=payment)
    webhook_repo = AsyncMock()
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()

    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    gateway = AsyncMock()
    gateway.emulate = AsyncMock(return_value=PaymentStatus.SUCCEEDED)

    monkeypatch.setattr(
        "app.services.payment_processor.PaymentRepository",
        lambda _session: payment_repo,
    )
    monkeypatch.setattr(
        "app.services.payment_processor.WebhookDeliveryRepository",
        lambda _session: webhook_repo,
    )
    monkeypatch.setattr(
        "app.services.payment_processor.capture_trace_context",
        lambda: {"traceparent": "00-abc-def-01"},
    )

    processor = PaymentProcessorService(session_factory, gateway)
    await processor.process(_make_message(payment.id))

    gateway.emulate.assert_awaited_once()
    payment_repo.update_status.assert_awaited_once()
    webhook_repo.enqueue.assert_awaited_once()
    enqueue_kwargs = webhook_repo.enqueue.await_args.kwargs
    assert enqueue_kwargs["payload"][TRACE_CONTEXT_KEY] == {
        "traceparent": "00-abc-def-01",
    }


async def test_process_skips_gateway_for_non_pending_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-pending payments should only enqueue webhook delivery."""
    payment = _make_payment(status=PaymentStatus.SUCCEEDED)
    payment.processed_at = datetime.now(UTC)
    payment_repo = AsyncMock()
    payment_repo.get_by_id = AsyncMock(return_value=payment)
    webhook_repo = AsyncMock()
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()

    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    gateway = AsyncMock()

    monkeypatch.setattr(
        "app.services.payment_processor.PaymentRepository",
        lambda _session: payment_repo,
    )
    monkeypatch.setattr(
        "app.services.payment_processor.WebhookDeliveryRepository",
        lambda _session: webhook_repo,
    )
    monkeypatch.setattr(
        "app.services.payment_processor.capture_trace_context",
        lambda: {},
    )

    processor = PaymentProcessorService(session_factory, gateway)
    await processor.process(_make_message(payment.id))

    gateway.emulate.assert_not_called()
    webhook_repo.enqueue.assert_awaited_once()


async def test_process_raises_when_payment_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing payment records should raise PoisonMessageError."""
    payment_repo = AsyncMock()
    payment_repo.get_by_id = AsyncMock(return_value=None)
    session = AsyncMock(spec=AsyncSession)

    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "app.services.payment_processor.PaymentRepository",
        lambda _session: payment_repo,
    )
    monkeypatch.setattr(
        "app.services.payment_processor.WebhookDeliveryRepository",
        lambda _session: AsyncMock(),
    )

    processor = PaymentProcessorService(session_factory, AsyncMock())

    with pytest.raises(PoisonMessageError):
        await processor.process(_make_message(uuid.uuid4()))


def test_create_payment_processor_builds_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Factory should wire gateway emulator and session factory."""
    session_factory = MagicMock()
    settings = MagicMock()
    settings.gateway_min_delay_seconds = 1.0
    settings.gateway_max_delay_seconds = 2.0
    settings.gateway_success_rate = 1.0

    processor = create_payment_processor(settings, session_factory)

    assert isinstance(processor, PaymentProcessorService)
