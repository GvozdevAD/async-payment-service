"""RabbitMQ topology tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.settings import get_settings
from app.messaging.topology import (
    declare_topology,
    payments_new_dlq,
    payments_new_queue,
)


@pytest.fixture
def topology_settings():
    """Return application settings for topology tests."""
    return get_settings()


def test_payments_new_queue_has_dlq_arguments(topology_settings) -> None:
    """Main queue should route dead letters to the DLQ."""
    queue = payments_new_queue(topology_settings)

    assert queue.name == topology_settings.rabbitmq_payments_new_queue
    assert queue.arguments["x-dead-letter-routing-key"] == (
        topology_settings.rabbitmq_payments_new_dlq
    )


def test_payments_new_dlq_is_durable(topology_settings) -> None:
    """DLQ definition should be durable."""
    dlq = payments_new_dlq(topology_settings)

    assert dlq.name == topology_settings.rabbitmq_payments_new_dlq
    assert dlq.durable is True


async def test_declare_topology_declares_exchange_queues_and_binding(
    topology_settings,
) -> None:
    """declare_topology should declare exchange, queues, and bind main queue."""
    broker = AsyncMock()
    declared_exchange = MagicMock()
    declared_queue = AsyncMock()
    broker.declare_exchange = AsyncMock(return_value=declared_exchange)
    broker.declare_queue = AsyncMock(side_effect=[MagicMock(), declared_queue])

    await declare_topology(broker, topology_settings)

    broker.declare_exchange.assert_awaited_once()
    assert broker.declare_queue.await_count == 2
    declared_queue.bind.assert_awaited_once_with(
        declared_exchange,
        routing_key=topology_settings.rabbitmq_payments_new_routing_key,
    )
