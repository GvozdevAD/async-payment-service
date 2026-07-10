"""register_handlers unit tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.consumer.handlers import register_handlers
from app.core.settings import get_settings
from app.messaging.schemas import PaymentNewMessage


def _make_message() -> PaymentNewMessage:
    """Build a payment-new message for handler registration tests."""
    return PaymentNewMessage(
        outbox_id=uuid.uuid4(),
        event_type="payment.new",
        payment_id=uuid.uuid4(),
        amount="10.00",
        currency="RUB",
        webhook_url="https://example.com/webhook",
    )


async def test_register_handlers_subscriber_delegates_to_delivery() -> None:
    """Registered subscriber should delegate to handle_payment_new_message."""
    captured: dict[str, object] = {}

    def subscriber_decorator(**kwargs: object) -> object:
        def decorator(fn: object) -> object:
            captured["handler"] = fn
            captured["kwargs"] = kwargs
            return fn

        return decorator

    broker = MagicMock()
    broker.subscriber = subscriber_decorator
    processor = AsyncMock()
    settings = get_settings()

    with patch(
        "app.consumer.handlers.handle_payment_new_message",
        AsyncMock(),
    ) as mock_handle:
        register_handlers(broker, processor, settings)

        handler = captured["handler"]
        assert handler is not None
        assert captured["kwargs"]["queue"].name == settings.rabbitmq_payments_new_queue

        message = _make_message()
        raw_message = MagicMock()
        raw_message.raw_message = MagicMock()

        with patch(
            "app.consumer.handlers.get_delivery_count",
            return_value=2,
        ) as mock_delivery_count:
            await handler(message, raw_message)  # type: ignore[operator]

        mock_delivery_count.assert_called_once_with(
            raw_message.raw_message,
            settings.rabbitmq_payments_new_queue,
        )
        mock_handle.assert_awaited_once_with(
            message,
            processor=processor,
            settings=settings,
            delivery_count=2,
            raw_message=raw_message.raw_message,
        )
