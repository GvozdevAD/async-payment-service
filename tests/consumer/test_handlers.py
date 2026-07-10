"""Consumer handler unit tests."""

import logging
import uuid
from unittest.mock import AsyncMock

import pytest
from faststream.exceptions import NackMessage, RejectMessage

from app.consumer.delivery import handle_payment_new_message
from app.core.exceptions import PoisonMessageError
from app.core.settings import Settings, get_settings
from app.messaging.schemas import PaymentNewMessage


@pytest.fixture
def consumer_settings() -> Settings:
    """Return application settings for consumer handler tests."""
    return get_settings()


def _make_message() -> PaymentNewMessage:
    """Build a payment-new message for handler tests."""
    return PaymentNewMessage(
        outbox_id=uuid.uuid4(),
        event_type="payment.new",
        payment_id=uuid.uuid4(),
        amount="10.00",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )


async def test_handler_delegates_to_processor(consumer_settings) -> None:
    """Handler should delegate processing to PaymentProcessorService."""
    processor = AsyncMock()
    processor.process = AsyncMock()

    await handle_payment_new_message(
        _make_message(),
        processor=processor,
        settings=consumer_settings,
        delivery_count=0,
    )

    processor.process.assert_awaited_once()


async def test_handler_rejects_poison_message(consumer_settings) -> None:
    """Poison messages should be rejected without requeue."""
    processor = AsyncMock()
    processor.process = AsyncMock(side_effect=PoisonMessageError("missing"))

    with pytest.raises(RejectMessage):
        await handle_payment_new_message(
            _make_message(),
            processor=processor,
            settings=consumer_settings,
            delivery_count=0,
        )


async def test_handler_nacks_transient_error_before_max_attempts(
    consumer_settings,
) -> None:
    """Transient errors should nack with requeue before max attempts."""
    processor = AsyncMock()
    processor.process = AsyncMock(side_effect=RuntimeError("db down"))

    with pytest.raises(NackMessage):
        await handle_payment_new_message(
            _make_message(),
            processor=processor,
            settings=consumer_settings,
            delivery_count=0,
        )


async def test_handler_rejects_after_max_attempts(consumer_settings) -> None:
    """Transient errors should reject to DLQ after max attempts."""
    processor = AsyncMock()
    processor.process = AsyncMock(side_effect=RuntimeError("db down"))

    with pytest.raises(RejectMessage):
        await handle_payment_new_message(
            _make_message(),
            processor=processor,
            settings=consumer_settings,
            delivery_count=consumer_settings.consumer_max_attempts - 1,
        )


async def test_handler_logs_warning_on_transient_nack(
    consumer_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Transient errors should log a warning before nacking with requeue."""
    processor = AsyncMock()
    processor.process = AsyncMock(side_effect=RuntimeError("db down"))

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(NackMessage),
    ):
        await handle_payment_new_message(
            _make_message(),
            processor=processor,
            settings=consumer_settings,
            delivery_count=0,
        )

    assert "Transient error, nacking with requeue" in caplog.text


async def test_handler_logs_error_on_final_reject(
    consumer_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Transient errors should log an error before rejecting to DLQ."""
    processor = AsyncMock()
    processor.process = AsyncMock(side_effect=RuntimeError("db down"))

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(RejectMessage),
    ):
        await handle_payment_new_message(
            _make_message(),
            processor=processor,
            settings=consumer_settings,
            delivery_count=consumer_settings.consumer_max_attempts - 1,
        )

    assert "Rejecting message to DLQ after max attempts" in caplog.text
