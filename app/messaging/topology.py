"""RabbitMQ exchange, queue and binding declarations."""

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.core.settings import Settings


def payments_new_dlq(settings: Settings) -> RabbitQueue:
    """Return the dead-letter queue definition for payment-new messages.

    Args:
        settings: Application settings with queue names.

    Returns:
        Durable DLQ definition for failed payment-new messages.
    """
    return RabbitQueue(
        name=settings.rabbitmq_payments_new_dlq,
        durable=True,
    )


def payments_new_queue(settings: Settings) -> RabbitQueue:
    """Return the main payments.new queue with DLQ routing.

    Args:
        settings: Application settings with queue names.

    Returns:
        Durable main queue with dead-letter routing configured.
    """
    return RabbitQueue(
        name=settings.rabbitmq_payments_new_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.rabbitmq_payments_new_dlq,
        },
    )


async def declare_topology(broker: RabbitBroker, settings: Settings) -> None:
    """Declare exchange, queues and bindings for payment events.

    Args:
        broker: Connected FastStream RabbitMQ broker.
        settings: Application settings with exchange and routing keys.
    """
    exchange = RabbitExchange(
        name=settings.rabbitmq_exchange,
        type=ExchangeType.TOPIC,
        durable=True,
    )
    dlq = payments_new_dlq(settings)
    queue = payments_new_queue(settings)

    declared_exchange = await broker.declare_exchange(exchange)
    await broker.declare_queue(dlq)
    declared_queue = await broker.declare_queue(queue)
    await declared_queue.bind(
        declared_exchange,
        routing_key=settings.rabbitmq_payments_new_routing_key,
    )
