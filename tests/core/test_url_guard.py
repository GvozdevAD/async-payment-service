"""SSRF URL guard unit tests."""

import pytest

from app.core.exceptions import UnsafeWebhookUrlError
from app.core.settings import LocalSettings
from app.core.url_guard import (
    ensure_public_destination,
    ensure_webhook_destination_allowed,
    validate_webhook_url,
)


def _make_settings(**overrides: object) -> LocalSettings:
    """Build local settings with sane defaults for URL guard tests."""
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "database_url_sync": "postgresql+psycopg://user:pass@localhost/db",
        "rabbitmq_url": "amqp://guest:guest@localhost:5672/",
        "api_key": "test-api-key-16chars",
        "rabbitmq_exchange": "payments",
        "rabbitmq_payments_new_queue": "payments.new",
        "rabbitmq_payments_new_dlq": "payments.new.dlq",
        "rabbitmq_payments_new_routing_key": "payments.new",
    }
    base.update(overrides)
    return LocalSettings(**base)


def test_validate_webhook_url_accepts_allowed_url() -> None:
    """A well-formed https URL should pass validation."""
    validate_webhook_url("https://example.com/webhook", _make_settings())


def test_validate_webhook_url_rejects_disallowed_scheme() -> None:
    """A scheme outside the allow-list should be rejected."""
    settings = _make_settings(webhook_allowed_schemes=("https",))
    with pytest.raises(UnsafeWebhookUrlError, match="scheme"):
        validate_webhook_url("http://example.com/webhook", settings)


def test_validate_webhook_url_rejects_embedded_credentials() -> None:
    """URLs carrying userinfo should be rejected."""
    with pytest.raises(UnsafeWebhookUrlError, match="credentials"):
        validate_webhook_url("https://user:pass@example.com/hook", _make_settings())


def test_validate_webhook_url_rejects_missing_host() -> None:
    """URLs without a host should be rejected."""
    with pytest.raises(UnsafeWebhookUrlError, match="host"):
        validate_webhook_url("https:///webhook", _make_settings())


def test_validate_webhook_url_rejects_disallowed_port() -> None:
    """Ports outside the allow-list should be rejected."""
    with pytest.raises(UnsafeWebhookUrlError, match="port 8080"):
        validate_webhook_url("https://example.com:8080/webhook", _make_settings())


def test_validate_webhook_url_rejects_invalid_port() -> None:
    """A malformed port should be rejected as unsafe."""
    with pytest.raises(UnsafeWebhookUrlError, match="invalid port"):
        validate_webhook_url("https://example.com:notaport/webhook", _make_settings())


async def test_ensure_public_destination_allows_public_ip() -> None:
    """A public IP address should be permitted."""
    await ensure_public_destination(
        "https://example.com/webhook",
        _make_settings(),
        resolver=lambda _host: ["93.184.216.34"],
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.10",
        "169.254.169.254",
        "::1",
        "0.0.0.0",
        "224.0.0.1",
    ],
)
async def test_ensure_public_destination_blocks_internal_ranges(address: str) -> None:
    """Private, loopback, link-local and similar ranges should be blocked."""
    with pytest.raises(UnsafeWebhookUrlError, match="blocked address"):
        await ensure_public_destination(
            "https://internal.example.com/webhook",
            _make_settings(),
            resolver=lambda _host: [address],
        )


async def test_ensure_public_destination_skipped_when_disabled() -> None:
    """No resolution should occur when private-network blocking is disabled."""

    def _resolver(_host: str) -> list[str]:
        raise AssertionError("resolver should not be called")

    await ensure_public_destination(
        "https://example.com/webhook",
        _make_settings(webhook_block_private_networks=False),
        resolver=_resolver,
    )


async def test_ensure_public_destination_rejects_missing_host() -> None:
    """A URL without a host should be rejected before resolution."""
    with pytest.raises(UnsafeWebhookUrlError, match="host"):
        await ensure_public_destination(
            "https:///webhook",
            _make_settings(),
            resolver=lambda _host: ["93.184.216.34"],
        )


async def test_ensure_public_destination_rejects_unresolvable_host() -> None:
    """DNS resolution failures should be treated as unsafe."""

    def _resolver(_host: str) -> list[str]:
        raise OSError("nxdomain")

    with pytest.raises(UnsafeWebhookUrlError, match="could not be resolved"):
        await ensure_public_destination(
            "https://example.com/webhook",
            _make_settings(),
            resolver=_resolver,
        )


async def test_ensure_public_destination_rejects_empty_resolution() -> None:
    """A host that resolves to nothing should be rejected."""
    with pytest.raises(UnsafeWebhookUrlError, match="did not resolve"):
        await ensure_public_destination(
            "https://example.com/webhook",
            _make_settings(),
            resolver=lambda _host: [],
        )


async def test_ensure_public_destination_uses_default_resolver() -> None:
    """The default system resolver should block a numeric loopback host."""
    with pytest.raises(UnsafeWebhookUrlError, match="blocked address"):
        await ensure_public_destination("https://127.0.0.1/webhook", _make_settings())


async def test_ensure_webhook_destination_allowed_runs_full_policy() -> None:
    """The combined helper should reject a disallowed port before resolving."""
    with pytest.raises(UnsafeWebhookUrlError, match="port"):
        await ensure_webhook_destination_allowed(
            "https://example.com:9000/webhook", _make_settings()
        )
