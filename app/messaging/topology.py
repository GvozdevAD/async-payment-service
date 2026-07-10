"""RabbitMQ exchange, queue and binding declarations."""

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.core.settings import Settings


async def declare_topology(broker: RabbitBroker, settings: Settings) -> None:
    """Declare exchange, queues and bindings for payment events."""
    exchange = RabbitExchange(
        name=settings.rabbitmq_exchange,
        type=ExchangeType.TOPIC,
        durable=True,
    )
    dlq = RabbitQueue(
        name=settings.rabbitmq_payments_new_dlq,
        durable=True,
    )
    queue = RabbitQueue(
        name=settings.rabbitmq_payments_new_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.rabbitmq_payments_new_dlq,
        },
    )

    declared_exchange = await broker.declare_exchange(exchange)
    await broker.declare_queue(dlq)
    declared_queue = await broker.declare_queue(queue)
    await declared_queue.bind(
        declared_exchange,
        routing_key=settings.rabbitmq_payments_new_routing_key,
    )
