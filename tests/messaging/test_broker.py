"""RabbitMQ broker factory tests."""

from unittest.mock import patch

from faststream.rabbit import RabbitBroker

from app.messaging.broker import create_broker


def test_create_broker_passes_url_to_rabbit_broker() -> None:
    """create_broker should forward the AMQP URL to RabbitBroker."""
    url = "amqp://payments:payments@localhost:5672/payments"

    with patch("app.messaging.broker.RabbitBroker") as broker_cls:
        broker_cls.return_value = RabbitBroker(url)
        broker = create_broker(url)

    broker_cls.assert_called_once_with(url)
    assert isinstance(broker, RabbitBroker)
