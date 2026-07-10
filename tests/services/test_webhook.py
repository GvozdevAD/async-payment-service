"""Webhook service unit tests."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.settings import Settings, get_settings
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.services.webhook import (
    WebhookDeliveryError,
    WebhookService,
    _is_retryable_exception,
    is_retryable_status,
)


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


async def test_send_creates_and_closes_internal_client(webhook_settings) -> None:
    """Service without injected client should create and close its own client."""
    mock_client = AsyncMock()
    request = httpx.Request("POST", "https://example.com/webhook")
    mock_client.post = AsyncMock(return_value=httpx.Response(200, request=request))
    mock_client.aclose = AsyncMock()

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        service = WebhookService(webhook_settings)
        await service.send(_make_payment())

    mock_client.aclose.assert_awaited_once()


async def test_send_raises_non_retryable_http_status_error(webhook_settings) -> None:
    """Non-retryable HTTPStatusError from retry loop should propagate."""
    service = WebhookService(webhook_settings, client=httpx.AsyncClient())
    payment = _make_payment()

    with patch.object(
        service,
        "_post_with_retry",
        side_effect=httpx.HTTPStatusError(
            "bad request",
            request=httpx.Request("POST", payment.webhook_url),
            response=httpx.Response(400),
        ),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await service.send(payment)


async def test_send_wraps_retry_error_in_webhook_delivery_error(
    webhook_settings,
) -> None:
    """Exhausted tenacity retries should raise WebhookDeliveryError."""
    from tenacity import RetryError

    service = WebhookService(webhook_settings, client=httpx.AsyncClient())
    payment = _make_payment()
    retry_error = RetryError(MagicMock())

    with patch.object(service, "_post_with_retry", side_effect=retry_error):
        with pytest.raises(WebhookDeliveryError):
            await service.send(payment)


def test_is_retryable_exception_for_non_retryable_http_status() -> None:
    """HTTP 400 should not be treated as retryable at the exception layer."""
    response = httpx.Response(400)
    exc = httpx.HTTPStatusError(
        "bad request",
        request=httpx.Request("GET", "https://example.com"),
        response=response,
    )

    assert is_retryable_status(400) is False
    assert _is_retryable_exception(exc) is False


def test_is_retryable_exception_for_transport_error() -> None:
    """Network transport errors should be retryable."""
    assert _is_retryable_exception(httpx.TransportError("down")) is True
