"""Webhook service unit tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.settings import Settings, get_settings
from app.core.signing import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    sign_payload,
)
from app.db.enums import PaymentStatus
from app.services.webhook import (
    WebhookService,
    is_retryable_exception,
    is_retryable_status,
)


@pytest.fixture
def webhook_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return settings with webhook timeout for tests."""
    monkeypatch.setenv("WEBHOOK_TIMEOUT_SECONDS", "5")
    get_settings.cache_clear()
    return get_settings()


def _make_payload() -> dict[str, object]:
    """Build a webhook payload dict for tests."""
    return {
        "payment_id": str(uuid.uuid4()),
        "status": PaymentStatus.SUCCEEDED.value,
        "amount": "100.00",
        "currency": "RUB",
        "description": "Webhook test",
        "metadata": {"order_id": "1"},
        "processed_at": datetime.now(UTC).isoformat(),
    }


async def test_deliver_once_success(webhook_settings: Settings) -> None:
    """A 200 response should return the status code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    status_code = await service.deliver_once(
        "https://example.com/webhook", _make_payload()
    )

    assert status_code == 200


async def test_deliver_once_raises_on_429(webhook_settings: Settings) -> None:
    """429 responses should raise HTTPStatusError for dispatcher retry."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await service.deliver_once("https://example.com/webhook", _make_payload())


async def test_deliver_once_raises_on_503(webhook_settings: Settings) -> None:
    """5xx responses should raise HTTPStatusError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await service.deliver_once("https://example.com/webhook", _make_payload())


async def test_deliver_once_returns_on_404(webhook_settings: Settings) -> None:
    """Non-retryable 4xx should return status without raising."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    status_code = await service.deliver_once(
        "https://example.com/webhook", _make_payload()
    )

    assert status_code == 404
    assert attempts["count"] == 1


async def test_deliver_once_creates_and_closes_internal_client(
    webhook_settings: Settings,
) -> None:
    """Service without injected client should create and close its own client."""
    mock_client = AsyncMock()
    request = httpx.Request("POST", "https://example.com/webhook")
    mock_client.post = AsyncMock(return_value=httpx.Response(200, request=request))
    mock_client.aclose = AsyncMock()

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        service = WebhookService(webhook_settings)
        await service.deliver_once("https://example.com/webhook", _make_payload())

    mock_client.aclose.assert_awaited_once()


@pytest.fixture
def signing_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return settings with webhook signing enabled for tests."""
    monkeypatch.setenv("WEBHOOK_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "super-secret-value-32chars-long!")
    get_settings.cache_clear()
    return get_settings()


async def test_deliver_once_signs_payload_when_enabled(
    signing_settings: Settings,
) -> None:
    """When signing is enabled, requests carry HMAC signature headers."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["content"] = request.content
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(signing_settings, client=client)

    await service.deliver_once("https://example.com/webhook", _make_payload())

    headers = captured["headers"]
    assert SIGNATURE_HEADER in headers
    timestamp = int(headers[TIMESTAMP_HEADER])
    expected = sign_payload(
        signing_settings.webhook_signing_secret,
        captured["content"],
        timestamp,
    )
    assert headers[SIGNATURE_HEADER] == f"t={timestamp},v1={expected}"


async def test_deliver_once_skips_signature_without_secret(
    webhook_settings: Settings,
) -> None:
    """Without a configured secret, no signature headers should be sent."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WebhookService(webhook_settings, client=client)

    await service.deliver_once("https://example.com/webhook", _make_payload())

    assert SIGNATURE_HEADER not in captured["headers"]


def test_is_retryable_exception_for_non_retryable_http_status() -> None:
    """HTTP 400 should not be treated as retryable at the exception layer."""
    response = httpx.Response(400)
    exc = httpx.HTTPStatusError(
        "bad request",
        request=httpx.Request("GET", "https://example.com"),
        response=response,
    )

    assert is_retryable_status(400) is False
    assert is_retryable_exception(exc) is False


def test_is_retryable_exception_for_transport_error() -> None:
    """Network transport errors should be retryable."""
    assert is_retryable_exception(httpx.TransportError("down")) is True
