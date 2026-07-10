"""Webhook dispatcher service unit tests."""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import LocalSettings
from app.db.enums import WebhookDeliveryStatus
from app.db.models.webhook_delivery import WebhookDelivery
from app.services.webhook_dispatcher import (
    WebhookDispatcherService,
    compute_backoff_seconds,
)


@pytest.fixture
def dispatcher_settings() -> LocalSettings:
    """Return settings for webhook dispatcher tests."""
    return LocalSettings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        database_url_sync="postgresql+psycopg://user:pass@localhost/db",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        api_key="test-api-key-16chars",
        rabbitmq_exchange="payments",
        rabbitmq_payments_new_queue="payments.new",
        rabbitmq_payments_new_dlq="payments.new.dlq",
        rabbitmq_payments_new_routing_key="payments.new",
        webhook_max_attempts=3,
        webhook_dispatcher_batch_size=10,
    )


def _make_delivery(
    *,
    delivery_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    attempts: int = 0,
) -> WebhookDelivery:
    """Build a webhook delivery ORM instance for tests."""
    return WebhookDelivery(
        id=delivery_id or uuid.uuid4(),
        payment_id=payment_id or uuid.uuid4(),
        url="https://example.com/webhook",
        payload={"payment_id": str(payment_id or uuid.uuid4())},
        status=WebhookDeliveryStatus.PENDING,
        attempts=attempts,
        next_attempt_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def dispatcher_service(
    dispatcher_settings: LocalSettings,
) -> tuple[WebhookDispatcherService, AsyncMock, async_sessionmaker[AsyncSession]]:
    """Return a dispatcher service with mocked webhook service and session factory."""
    session = AsyncMock(spec=AsyncSession)
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    session_factory = MagicMock(spec=async_sessionmaker)
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    webhook_service = AsyncMock()
    webhook_service.deliver_once = AsyncMock(return_value=200)
    service = WebhookDispatcherService(
        session_factory=session_factory,
        webhook_service=webhook_service,
        settings=dispatcher_settings,
    )
    return service, webhook_service, session_factory


async def test_dispatch_pending_success(
    dispatcher_service: tuple[
        WebhookDispatcherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Due delivery should be dispatched and marked delivered."""
    service, webhook_service, _session_factory = dispatcher_service
    delivery = _make_delivery()
    repo = AsyncMock()
    repo.get_due_batch = AsyncMock(side_effect=[[delivery], []])
    repo.mark_delivered = AsyncMock()
    monkeypatch.setattr(
        "app.services.webhook_dispatcher.WebhookDeliveryRepository",
        lambda _session: repo,
    )

    delivered = await service.dispatch_pending()

    assert delivered == 1
    webhook_service.deliver_once.assert_awaited_once()
    repo.mark_delivered.assert_awaited_once()
    repo.mark_failed.assert_not_called()
    repo.reschedule.assert_not_called()


async def test_dispatch_pending_empty_batch(
    dispatcher_service: tuple[
        WebhookDispatcherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No due deliveries should return zero dispatched webhooks."""
    service, webhook_service, _session_factory = dispatcher_service
    repo = AsyncMock()
    repo.get_due_batch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.webhook_dispatcher.WebhookDeliveryRepository",
        lambda _session: repo,
    )

    delivered = await service.dispatch_pending()

    assert delivered == 0
    webhook_service.deliver_once.assert_not_awaited()


async def test_dispatch_reschedules_on_retryable_error(
    dispatcher_service: tuple[
        WebhookDispatcherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retryable errors should reschedule the delivery."""
    service, webhook_service, _session_factory = dispatcher_service
    delivery = _make_delivery(attempts=0)
    repo = AsyncMock()
    repo.get_due_batch = AsyncMock(side_effect=[[delivery], []])
    repo.reschedule = AsyncMock()
    monkeypatch.setattr(
        "app.services.webhook_dispatcher.WebhookDeliveryRepository",
        lambda _session: repo,
    )
    webhook_service.deliver_once = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "service unavailable",
            request=httpx.Request("POST", delivery.url),
            response=httpx.Response(503),
        ),
    )

    delivered = await service.dispatch_pending()

    assert delivered == 0
    repo.reschedule.assert_awaited_once()
    repo.mark_failed.assert_not_called()


async def test_dispatch_marks_failed_after_max_attempts(
    dispatcher_settings: LocalSettings,
    dispatcher_service: tuple[
        WebhookDispatcherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Max retry attempts should mark the delivery as failed."""
    dispatcher_settings.webhook_max_attempts = 3
    service, webhook_service, _session_factory = dispatcher_service
    delivery = _make_delivery(attempts=2)
    repo = AsyncMock()
    repo.get_due_batch = AsyncMock(side_effect=[[delivery], []])
    repo.mark_failed = AsyncMock()
    monkeypatch.setattr(
        "app.services.webhook_dispatcher.WebhookDeliveryRepository",
        lambda _session: repo,
    )
    webhook_service.deliver_once = AsyncMock(
        side_effect=httpx.TimeoutException("timeout"),
    )

    delivered = await service.dispatch_pending()

    assert delivered == 0
    repo.mark_failed.assert_awaited_once()
    repo.reschedule.assert_not_called()


async def test_dispatch_non_retryable_error_propagates(
    dispatcher_service: tuple[
        WebhookDispatcherService, AsyncMock, async_sessionmaker[AsyncSession]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-retryable errors should propagate without reschedule."""
    service, webhook_service, _session_factory = dispatcher_service
    delivery = _make_delivery()
    repo = AsyncMock()
    repo.get_due_batch = AsyncMock(return_value=[delivery])
    monkeypatch.setattr(
        "app.services.webhook_dispatcher.WebhookDeliveryRepository",
        lambda _session: repo,
    )
    webhook_service.deliver_once = AsyncMock(side_effect=RuntimeError("unexpected"))

    with pytest.raises(RuntimeError, match="unexpected"):
        await service.dispatch_pending()


async def test_start_and_stop_manage_client(
    dispatcher_settings: LocalSettings,
) -> None:
    """start() and stop() should manage the shared HTTP client lifecycle."""
    session_factory = MagicMock()
    service = WebhookDispatcherService(
        session_factory=session_factory,
        webhook_service=AsyncMock(),
        settings=dispatcher_settings,
    )

    await service.start()
    assert service._client is not None

    await service.stop()
    assert service._client is None


async def test_run_forever_cancels_cleanly(
    dispatcher_settings: LocalSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_forever should propagate CancelledError after logging shutdown."""
    session_factory = MagicMock()
    service = WebhookDispatcherService(
        session_factory=session_factory,
        webhook_service=AsyncMock(),
        settings=dispatcher_settings,
    )
    dispatcher_settings.webhook_dispatcher_poll_interval_seconds = 0.01
    dispatch_mock = AsyncMock(return_value=0)
    monkeypatch.setattr(service, "dispatch_pending", dispatch_mock)

    task = asyncio.create_task(service.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_run_forever_logs_iteration_error(
    dispatcher_settings: LocalSettings,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected errors in dispatch_pending should be logged and retried."""
    import logging

    session_factory = MagicMock()
    service = WebhookDispatcherService(
        session_factory=session_factory,
        webhook_service=AsyncMock(),
        settings=dispatcher_settings,
    )
    dispatcher_settings.webhook_dispatcher_poll_interval_seconds = 0.01
    monkeypatch.setattr(
        service,
        "dispatch_pending",
        AsyncMock(side_effect=[RuntimeError("db down"), asyncio.CancelledError()]),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await service.run_forever()

    assert "Webhook dispatcher iteration failed" in caplog.text


def test_compute_backoff_seconds() -> None:
    """Backoff should grow exponentially and cap at 10 seconds."""
    assert compute_backoff_seconds(1) == 1.0
    assert compute_backoff_seconds(2) == 2.0
    assert compute_backoff_seconds(4) == 8.0
    assert compute_backoff_seconds(5) == 10.0


def test_create_webhook_dispatcher(
    dispatcher_settings: LocalSettings,
) -> None:
    """Factory should build a configured webhook dispatcher service."""
    from app.services.webhook_dispatcher import create_webhook_dispatcher

    session_factory = MagicMock()
    dispatcher = create_webhook_dispatcher(dispatcher_settings, session_factory)

    assert dispatcher._settings is dispatcher_settings
    assert dispatcher._session_factory is session_factory
