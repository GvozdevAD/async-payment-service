"""RabbitMQ broker factory."""

from faststream.rabbit import RabbitBroker


def create_broker(url: str) -> RabbitBroker:
    """Return a configured RabbitBroker instance.

    Args:
        url: AMQP connection URL.

    Returns:
        FastStream RabbitMQ broker connected to the given URL.
    """
    return RabbitBroker(url)
