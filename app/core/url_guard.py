"""SSRF protection for outbound webhook URLs.

Validation happens in two stages:

* :func:`validate_webhook_url` performs cheap, network-free checks on the
  scheme, credentials, host, and port. It is safe to call at request time
  (e.g. when a payment is created) to fail fast on obviously unsafe URLs.
* :func:`ensure_public_destination` resolves the host asynchronously and
  rejects any address that points at private, loopback, link-local, or
  otherwise internal ranges. It is called right before delivery to defend
  against DNS rebinding.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from app.core.exceptions import UnsafeWebhookUrlError
from app.core.settings import Settings

Resolver = Callable[[str], list[str]]


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_webhook_url(url: str, settings: Settings) -> None:
    """Validate the scheme, credentials, host, and port of a webhook URL.

    This performs no DNS resolution and is safe to run on the request path.

    Args:
        url: Client-supplied webhook URL.
        settings: Active application settings holding the destination policy.

    Raises:
        UnsafeWebhookUrlError: If the URL violates the destination policy.
    """
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    if scheme not in settings.webhook_allowed_schemes:
        msg = f"Webhook URL scheme '{scheme}' is not allowed"
        raise UnsafeWebhookUrlError(msg)

    if parts.username or parts.password:
        msg = "Webhook URL must not contain embedded credentials"
        raise UnsafeWebhookUrlError(msg)

    if not parts.hostname:
        msg = "Webhook URL must include a host"
        raise UnsafeWebhookUrlError(msg)

    try:
        port = parts.port
    except ValueError as exc:
        msg = "Webhook URL has an invalid port"
        raise UnsafeWebhookUrlError(msg) from exc

    if port is not None and port not in settings.webhook_allowed_ports:
        msg = f"Webhook URL port {port} is not allowed"
        raise UnsafeWebhookUrlError(msg)


async def ensure_public_destination(
    url: str,
    settings: Settings,
    resolver: Resolver = _default_resolver,
) -> None:
    """Resolve the host and reject private or otherwise internal addresses.

    DNS resolution runs in a worker thread so the caller's event loop is not
    blocked.

    Args:
        url: Webhook URL whose host will be resolved.
        settings: Active application settings holding the destination policy.
        resolver: Callable mapping a host to a list of IP address strings.
            Injectable for testing.

    Raises:
        UnsafeWebhookUrlError: If the host cannot be resolved or resolves to a
            blocked address range.
    """
    if not settings.webhook_block_private_networks:
        return

    host = urlsplit(url).hostname
    if not host:
        msg = "Webhook URL must include a host"
        raise UnsafeWebhookUrlError(msg)

    try:
        addresses = await asyncio.to_thread(resolver, host)
    except OSError as exc:
        msg = f"Webhook host '{host}' could not be resolved"
        raise UnsafeWebhookUrlError(msg) from exc

    if not addresses:
        msg = f"Webhook host '{host}' did not resolve to any address"
        raise UnsafeWebhookUrlError(msg)

    for address in addresses:
        if _is_blocked_ip(ipaddress.ip_address(address)):
            msg = f"Webhook host '{host}' resolves to a blocked address"
            raise UnsafeWebhookUrlError(msg)


async def ensure_webhook_destination_allowed(url: str, settings: Settings) -> None:
    """Run the full webhook destination policy (format + resolution).

    Args:
        url: Webhook URL to validate.
        settings: Active application settings holding the destination policy.

    Raises:
        UnsafeWebhookUrlError: If the URL violates the destination policy.
    """
    validate_webhook_url(url, settings)
    await ensure_public_destination(url, settings)
