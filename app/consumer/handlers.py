"""FastStream consumer handlers."""

from faststream.rabbit import RabbitBroker, RabbitMessage
from faststream.rabbit.schemas import Channel

from app.consumer.delivery import get_delivery_count, handle_payment_new_message
from app.core.settings import Settings
from app.messaging.schemas import PaymentNewMessage
from app.messaging.topology import payments_new_queue
from app.services.payment_processor import PaymentProcessorService


def register_handlers(
    broker: RabbitBroker,
    processor: PaymentProcessorService,
    settings: Settings,
) -> None:
    """Register RabbitMQ subscribers for payment processing.

    Args:
        broker: FastStream RabbitMQ broker instance.
        processor: Service that processes payment-new queue messages.
        settings: Application settings including prefetch and queue names.
    """
    channel = Channel(prefetch_count=settings.consumer_prefetch_count)

    @broker.subscriber(
        queue=payments_new_queue(settings),
        channel=channel,
    )
    async def handle_payment_new(
        message: PaymentNewMessage,
        raw_message: RabbitMessage,
    ) -> None:
        delivery_count = get_delivery_count(
            raw_message.raw_message,
            settings.rabbitmq_payments_new_queue,
        )
        await handle_payment_new_message(
            message,
            processor=processor,
            settings=settings,
            delivery_count=delivery_count,
        )
