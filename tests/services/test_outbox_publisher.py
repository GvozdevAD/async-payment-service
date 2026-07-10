"""Outbox publisher service unit tests."""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aio_pika.exceptions import AMQPConnectionError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.propagation import TRACE_CONTEXT_KEY
from app.core.settings import LocalSettings
from app.db.enums import OutboxStatus
from app.db.models.outbox import Outbox
from app.messaging.schemas import PaymentNewMessage
from app.services.outbox_publisher import (
    OutboxPublisherService,
    create_outbox_publisher,
)


@pytest.fixture
def publisher_settings() -> LocalSettings:
    """Return settings for outbox publisher tests."""
    return LocalSettings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        database_url_sync="postgresql+psycopg://user:pass@localhost/db",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        api_key="test-api-key-16chars",
        rabbitmq_exchange="payments",
        rabbitmq_payments_new_queue="payments.new",
        rabbitmq_payments_new_dlq="payments.new.dlq",
        rabbitmq_payments_new_routing_key="payments.new",
        outbox_publish_max_attempts=3,
        outbox_batch_size=10,
    )


def _make_outbox(
    *,
    outbox_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
) -> Outbox:
    """Build an outbox ORM instance for tests."""
    payment_id = payment_id or uuid.uuid4()
    return Outbox(
        id=outbox_id or uuid.uuid4(),
        aggregate_id=payment_id,
        event_type="payments.new",
        payload={
            "payment_id": str(payment_id),
            "amount": "100.50",
            "currency": "RUB",
            "webhook_url": "https://example.com/webhook",
        },
        status=OutboxStatus.PENDING,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def publisher_service(
    publisher_settings: LocalSettings,
) -> tuple[OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]]:
    """Return a publisher service with mocked broker and session factory."""
    session = AsyncMock(spec=AsyncSession)
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    broker = AsyncMock()
    service = OutboxPublisherService(
        session_factory=session_factory,
        broker=broker,
        settings=publisher_settings,
    )
    return service, broker, session_factory


async def test_publish_pending_success(
    publisher_service: tuple[
        OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pending outbox record should be published and marked published."""
    service, broker, _session_factory = publisher_service
    outbox = _make_outbox()
    repo = AsyncMock()
    repo.get_pending_batch = AsyncMock(side_effect=[[outbox], []])
    repo.mark_published = AsyncMock()
    monkeypatch.setattr(
        "app.services.outbox_publisher.OutboxRepository",
        lambda _session: repo,
    )

    published = await service.publish_pending()

    assert published == 1
    broker.publish.assert_awaited_once()
    repo.mark_published.assert_awaited_once()
    repo.mark_failed.assert_not_called()


async def test_publish_pending_empty_batch(
    publisher_service: tuple[
        OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No pending records should return zero published messages."""
    service, broker, _session_factory = publisher_service
    repo = AsyncMock()
    repo.get_pending_batch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.outbox_publisher.OutboxRepository",
        lambda _session: repo,
    )

    published = await service.publish_pending()

    assert published == 0
    broker.publish.assert_not_awaited()


async def test_publish_retries_on_broker_error(
    publisher_settings: LocalSettings,
    publisher_service: tuple[
        OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient broker errors should be retried before success."""
    publisher_settings.outbox_publish_max_attempts = 3
    service, broker, _session_factory = publisher_service
    outbox = _make_outbox()
    repo = AsyncMock()
    repo.get_pending_batch = AsyncMock(side_effect=[[outbox], []])
    repo.mark_published = AsyncMock()
    monkeypatch.setattr(
        "app.services.outbox_publisher.OutboxRepository",
        lambda _session: repo,
    )
    broker.publish = AsyncMock(
        side_effect=[
            AMQPConnectionError("connection refused"),
            AMQPConnectionError("connection refused"),
            None,
        ],
    )

    published = await service.publish_pending()

    assert published == 1
    assert broker.publish.await_count == 3
    repo.mark_published.assert_awaited_once()


async def test_publish_keeps_pending_after_max_retries(
    publisher_settings: LocalSettings,
    publisher_service: tuple[
        OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient broker failures should leave outbox pending for the next poll."""
    publisher_settings.outbox_publish_max_attempts = 3
    service, broker, _session_factory = publisher_service
    outbox = _make_outbox()
    repo = AsyncMock()
    repo.get_pending_batch = AsyncMock(side_effect=[[outbox], []])
    repo.mark_failed = AsyncMock()
    repo.mark_published = AsyncMock()
    monkeypatch.setattr(
        "app.services.outbox_publisher.OutboxRepository",
        lambda _session: repo,
    )
    broker.publish = AsyncMock(side_effect=AMQPConnectionError("connection refused"))

    published = await service.publish_pending()

    assert published == 0
    assert broker.publish.await_count == 3
    repo.mark_failed.assert_not_called()
    repo.mark_published.assert_not_called()


def test_payment_new_message_from_outbox() -> None:
    """Outbox payload should map to a payment-new message."""
    from app.mappers.outbox import to_payment_new_message

    payment_id = uuid.uuid4()
    outbox = _make_outbox(payment_id=payment_id)

    message = to_payment_new_message(outbox)

    assert message == PaymentNewMessage(
        outbox_id=outbox.id,
        event_type="payments.new",
        payment_id=payment_id,
        amount="100.50",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )


def test_payment_new_message_invalid_payload_raises() -> None:
    """Invalid outbox payload should raise validation error."""
    from app.mappers.outbox import to_payment_new_message

    outbox = _make_outbox()
    outbox.payload = {"payment_id": "not-a-valid-message"}

    with pytest.raises(ValidationError):
        to_payment_new_message(outbox)


async def test_publish_marks_failed_on_validation_error(
    publisher_service: tuple[
        OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid outbox payload should mark the record as failed."""
    service, broker, _session_factory = publisher_service
    outbox = _make_outbox()
    outbox.payload = {"payment_id": "not-a-valid-message"}
    repo = AsyncMock()
    repo.get_pending_batch = AsyncMock(side_effect=[[outbox], []])
    repo.mark_failed = AsyncMock()
    monkeypatch.setattr(
        "app.services.outbox_publisher.OutboxRepository",
        lambda _session: repo,
    )

    published = await service.publish_pending()

    assert published == 0
    broker.publish.assert_not_awaited()
    repo.mark_failed.assert_awaited_once()
    repo.mark_published.assert_not_called()


async def test_start_declares_topology(
    publisher_settings: LocalSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start() should connect broker and declare topology."""
    broker = AsyncMock()
    mock_declare = AsyncMock()
    monkeypatch.setattr(
        "app.services.outbox_publisher.declare_topology",
        mock_declare,
    )
    session_factory = MagicMock()
    service = OutboxPublisherService(
        session_factory=session_factory,
        broker=broker,
        settings=publisher_settings,
    )

    await service.start()

    broker.start.assert_awaited_once()
    mock_declare.assert_awaited_once_with(broker, publisher_settings)


async def test_stop_closes_broker(publisher_settings: LocalSettings) -> None:
    """stop() should close the broker connection."""
    broker = AsyncMock()
    session_factory = MagicMock()
    service = OutboxPublisherService(
        session_factory=session_factory,
        broker=broker,
        settings=publisher_settings,
    )

    await service.stop()

    broker.stop.assert_awaited_once()


async def test_run_forever_cancels_cleanly(
    publisher_settings: LocalSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_forever should propagate CancelledError after logging shutdown."""
    broker = AsyncMock()
    session_factory = MagicMock()
    service = OutboxPublisherService(
        session_factory=session_factory,
        broker=broker,
        settings=publisher_settings,
    )
    publisher_settings.outbox_poll_interval_seconds = 0.01
    publish_mock = AsyncMock(return_value=0)
    monkeypatch.setattr(service, "publish_pending", publish_mock)

    task = asyncio.create_task(service.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_run_forever_logs_iteration_error(
    publisher_settings: LocalSettings,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected errors in publish_pending should be logged and retried."""
    import logging

    broker = AsyncMock()
    session_factory = MagicMock()
    service = OutboxPublisherService(
        session_factory=session_factory,
        broker=broker,
        settings=publisher_settings,
    )
    publisher_settings.outbox_poll_interval_seconds = 0.01
    monkeypatch.setattr(
        service,
        "publish_pending",
        AsyncMock(side_effect=[RuntimeError("db down"), asyncio.CancelledError()]),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await service.run_forever()

    assert "Outbox publisher iteration failed" in caplog.text


async def test_publish_includes_trace_headers_when_carrier_present(
    publisher_service: tuple[
        OutboxPublisherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Published messages should include trace context from outbox payload."""
    service, broker, _session_factory = publisher_service
    outbox = _make_outbox()
    outbox.payload[TRACE_CONTEXT_KEY] = {"traceparent": "00-abc-def-01"}
    repo = AsyncMock()
    repo.get_pending_batch = AsyncMock(side_effect=[[outbox], []])
    repo.mark_published = AsyncMock()
    repo.count_pending = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "app.services.outbox_publisher.OutboxRepository",
        lambda _session: repo,
    )

    published = await service.publish_pending()

    assert published == 1
    publish_kwargs = broker.publish.await_args.kwargs
    assert publish_kwargs["headers"]["traceparent"] == "00-abc-def-01"


def test_create_outbox_publisher_factory(
    publisher_settings: LocalSettings,
) -> None:
    """Factory should return a configured outbox publisher service."""
    session_factory = MagicMock()
    broker = MagicMock()

    service = create_outbox_publisher(
        publisher_settings,
        session_factory,
        broker,
    )

    assert isinstance(service, OutboxPublisherService)
