"""Consumer delivery helper unit tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from aio_pika import IncomingMessage
from faststream.exceptions import NackMessage

from app.consumer.delivery import (
    RETRY_COUNT_HEADER,
    get_delivery_count,
    handle_payment_new_message,
    set_retry_count,
)
from app.core.settings import Settings, get_settings
from app.messaging.schemas import PaymentNewMessage


@pytest.fixture
def consumer_settings() -> Settings:
    """Return application settings for delivery tests."""
    return get_settings()


def _make_message() -> PaymentNewMessage:
    return PaymentNewMessage(
        outbox_id=uuid.uuid4(),
        event_type="payment.new",
        payment_id=uuid.uuid4(),
        amount="10.00",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )


def _make_incoming_message(
    *,
    headers: dict | None = None,
    redelivered: bool = False,
) -> IncomingMessage:
    message = MagicMock(spec=IncomingMessage)
    message.headers = headers
    message.redelivered = redelivered
    return message


def test_get_delivery_count_returns_zero_on_first_delivery() -> None:
    """First delivery without headers should count as zero prior attempts."""
    message = _make_incoming_message()

    assert get_delivery_count(message, "payments.new") == 0


def test_get_delivery_count_uses_x_retry_count_header() -> None:
    """Consumer-managed retry header should take priority."""
    message = _make_incoming_message(headers={RETRY_COUNT_HEADER: 2})

    assert get_delivery_count(message, "payments.new") == 2


def test_get_delivery_count_ignores_redelivered_without_retry_header() -> None:
    """Redelivered flag alone should not advance attempt counting."""
    message = _make_incoming_message(redelivered=True)

    assert get_delivery_count(message, "payments.new") == 0


def test_get_delivery_count_reads_x_death_for_queue() -> None:
    """Broker x-death metadata should be used when retry header is absent."""
    message = _make_incoming_message(
        headers={
            "x-death": [
                {"queue": "payments.new", "count": 2},
                {"queue": "other", "count": 9},
            ],
        },
    )

    assert get_delivery_count(message, "payments.new") == 2


def test_set_retry_count_updates_message_headers() -> None:
    """Retry counter should be written to x-retry-count before nack."""
    message = _make_incoming_message(headers={"existing": "value"})

    set_retry_count(message, 1)

    assert message.headers == {"existing": "value", RETRY_COUNT_HEADER: 1}


async def test_handler_sets_retry_header_before_nack(
    consumer_settings: Settings,
) -> None:
    """Transient nack should increment x-retry-count on the raw message."""
    processor = AsyncMock()
    processor.process = AsyncMock(side_effect=RuntimeError("db down"))
    raw_message = _make_incoming_message()

    with pytest.raises(NackMessage):
        await handle_payment_new_message(
            _make_message(),
            processor=processor,
            settings=consumer_settings,
            delivery_count=0,
            raw_message=raw_message,
        )

    assert raw_message.headers[RETRY_COUNT_HEADER] == 1
