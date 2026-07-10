"""Webhook HTTP delivery (single attempt per call)."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.settings import Settings
from app.core.signing import build_signature_headers

logger = logging.getLogger(__name__)

WEBHOOK_RETRYABLE_STATUS_CODES = frozenset({408, 429})


def is_retryable_status(status_code: int) -> bool:
    """Return whether an HTTP status code should trigger a retry.

    Args:
        status_code: HTTP response status code.

    Returns:
        True for retryable client/server errors, False otherwise.
    """
    return status_code in WEBHOOK_RETRYABLE_STATUS_CODES or status_code >= 500


def is_retryable_exception(exc: BaseException) -> bool:
    """Return whether an exception should trigger a webhook retry.

    Args:
        exc: Exception raised during a webhook delivery attempt.

    Returns:
        True for retryable HTTP/transport errors, False otherwise.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return is_retryable_status(exc.response.status_code)
    return isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.TransportError,
            httpx.NetworkError,
        ),
    )


class WebhookService:
    """Perform single-attempt webhook HTTP delivery."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = settings.webhook_timeout_seconds
        self._client = client
        self._signing_secret = settings.webhook_signing_secret
        self._signature_enabled = settings.webhook_signature_enabled and bool(
            self._signing_secret
        )

    def _build_request(self, payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
        """Serialize the payload and build headers, signing when enabled.

        Args:
            payload: JSON-serializable webhook body.

        Returns:
            Tuple of the exact body bytes and the request headers.
        """
        body = json.dumps(payload, separators=(",", ":"), default=str).encode()
        headers = {"Content-Type": "application/json"}
        if self._signature_enabled:
            timestamp = int(datetime.now(UTC).timestamp())
            headers.update(
                build_signature_headers(self._signing_secret, body, timestamp)
            )
        return body, headers

    async def deliver_once(self, url: str, payload: dict[str, Any]) -> int:
        """POST webhook payload once and return the HTTP status code.

        Args:
            url: Client webhook URL.
            payload: JSON-serializable webhook body.

        Returns:
            HTTP response status code.

        Raises:
            httpx.HTTPStatusError: For retryable HTTP error responses.
            httpx.TimeoutException: On request timeout.
            httpx.TransportError: On network/transport failures.
        """
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        body, headers = self._build_request(payload)
        try:
            response = await client.post(url, content=body, headers=headers)

            if is_retryable_status(response.status_code):
                response.raise_for_status()

            if response.status_code >= 400:
                logger.warning(
                    "Webhook client error status=%s url=%s payment_id=%s",
                    response.status_code,
                    url,
                    payload.get("payment_id"),
                )
                return response.status_code

            response.raise_for_status()
            return response.status_code
        finally:
            if owns_client:
                await client.aclose()
