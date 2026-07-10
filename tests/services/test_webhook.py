"""Webhook service unit tests."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.core.settings import Settings, get_settings
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.services.webhook import WebhookDeliveryError, WebhookService


@pytest.fixture
def webhook_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return settings with fast webhook retries for tests."""
    monkeypatch.setenv("WEBHOOK_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("WEBHOOK_TIMEOUT_SECONDS", "5")
    get_settings.cache_clear()
    return get_settings()


def _make_payment() -> Payment:
    """Build a processed payment for webhook tests."""
    return Payment(
        id=uuid.uuid4(),
        amount=Decimal("100.00"),
        currency=Currency.RUB,
        description="Webhook test",
        metadata_={"order_id": "1"},
        webhook_url="https://example.com/webhook",
        idempotency_key="webhook-test",
        status=PaymentStatus.SUCCEEDED,
        processed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


async def test_send_success(webhook_settings) -> None:
    """A 200 response should complete without error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    await service.send(_make_payment())


async def test_send_retries_on_429(webhook_settings) -> None:
    """429 responses should be retried until success."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(429)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    await service.send(_make_payment())
    assert attempts["count"] == 3


async def test_send_retries_on_503(webhook_settings) -> None:
    """5xx responses should be retried."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    await service.send(_make_payment())
    assert attempts["count"] == 2


async def test_send_no_retry_on_404(webhook_settings) -> None:
    """4xx client errors should not be retried."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    await service.send(_make_payment())
    assert attempts["count"] == 1


async def test_send_raises_after_max_attempts(webhook_settings) -> None:
    """Persistent 503 should raise after max attempts."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    with pytest.raises(WebhookDeliveryError):
        await service.send(_make_payment())
