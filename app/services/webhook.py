"""Webhook HTTP delivery with retries."""

import logging

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.settings import Settings
from app.db.models.payment import Payment
from app.mappers.webhook import to_webhook_payload
from app.schemas.webhook import WebhookPayload

logger = logging.getLogger(__name__)

WEBHOOK_RETRYABLE_STATUS_CODES = frozenset({408, 429})


class WebhookDeliveryError(Exception):
    """Webhook delivery failed after all retry attempts."""


def is_retryable_status(status_code: int) -> bool:
    """Return whether an HTTP status code should trigger a retry."""
    return status_code in WEBHOOK_RETRYABLE_STATUS_CODES or status_code >= 500


def _is_retryable_exception(exc: BaseException) -> bool:
    """Return whether an exception should trigger a webhook retry."""
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
    """Deliver payment status updates to client webhook URLs."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._max_attempts = settings.webhook_max_attempts
        self._timeout = settings.webhook_timeout_seconds
        self._client = client

    async def send(self, payment: Payment) -> None:
        """POST payment status to the client webhook URL.

        Args:
            payment: Processed payment whose status should be delivered.

        Raises:
            WebhookDeliveryError: If delivery fails after all retry attempts.
            httpx.HTTPStatusError: For non-retryable HTTP client errors.
        """
        payload = to_webhook_payload(payment)
        url = payment.webhook_url
        logger.info(
            "Sending webhook payment_id=%s status=%s url=%s",
            payment.id,
            payment.status.value,
            url,
        )
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            await self._post_with_retry(url, payload, client)
        except RetryError as exc:
            logger.exception(
                "Webhook delivery failed after retries payment_id=%s url=%s",
                payment.id,
                url,
            )
            raise WebhookDeliveryError(str(exc)) from exc
        except (
            httpx.HTTPStatusError,
            httpx.TimeoutException,
            httpx.TransportError,
            httpx.NetworkError,
        ) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and not is_retryable_status(
                exc.response.status_code,
            ):
                raise
            logger.exception(
                "Webhook delivery failed after retries payment_id=%s url=%s",
                payment.id,
                url,
            )
            raise WebhookDeliveryError(str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _post_with_retry(
        self,
        url: str,
        payload: WebhookPayload,
        client: httpx.AsyncClient,
    ) -> None:
        """POST webhook payload with exponential backoff retries."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(_is_retryable_exception),
            reraise=True,
        ):
            with attempt:
                await self._post_once(url, payload, client)

    async def _post_once(
        self,
        url: str,
        payload: WebhookPayload,
        client: httpx.AsyncClient,
    ) -> None:
        """Perform a single webhook HTTP POST."""
        body = payload.model_dump(mode="json")
        response = await client.post(url, json=body)

        if is_retryable_status(response.status_code):
            response.raise_for_status()

        if response.status_code >= 400:
            logger.warning(
                "Webhook client error status=%s url=%s payment_id=%s",
                response.status_code,
                url,
                payload.payment_id,
            )
            return

        response.raise_for_status()
