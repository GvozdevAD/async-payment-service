"""RabbitMQ broker factory."""

from faststream.rabbit import RabbitBroker


def create_broker(url: str) -> RabbitBroker:
    """Return a configured RabbitBroker instance."""
    return RabbitBroker(url)
