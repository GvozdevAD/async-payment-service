"""Health service unit tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aio_pika.exceptions import AMQPConnectionError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.services.health import HealthService, SERVICE_UNAVAILABLE_DETAIL
from tests.conftest import TEST_API_KEY


@pytest.fixture
def health_service() -> HealthService:
    """Return a health service with test settings."""
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        database_url_sync="postgresql+psycopg://user:pass@localhost/db",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        api_key=TEST_API_KEY,
    )
    return HealthService(settings=settings)


async def test_check_postgres_returns_ok_on_success(
    health_service: HealthService,
) -> None:
    """PostgreSQL check should report ok when the query succeeds."""
    session = AsyncMock()

    result = await health_service.check_postgres(session)

    assert result.status == "ok"
    assert result.detail is None
    session.execute.assert_awaited_once()


async def test_check_postgres_returns_error_on_db_failure(
    health_service: HealthService,
) -> None:
    """PostgreSQL check should report error on database failures."""
    session = AsyncMock()
    session.execute.side_effect = OperationalError("stmt", {}, Exception("db down"))

    result = await health_service.check_postgres(session)

    assert result.status == "error"
    assert result.detail == SERVICE_UNAVAILABLE_DETAIL


async def test_check_postgres_propagates_unexpected_errors(
    health_service: HealthService,
) -> None:
    """Unexpected errors during PostgreSQL check should propagate."""
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("unexpected bug")

    with pytest.raises(RuntimeError, match="unexpected bug"):
        await health_service.check_postgres(session)


@patch("app.services.health.aio_pika.connect_robust", new_callable=AsyncMock)
async def test_check_rabbitmq_returns_ok_on_success(
    connect_robust: AsyncMock,
    health_service: HealthService,
) -> None:
    """RabbitMQ check should report ok when the connection succeeds."""
    connection = MagicMock()
    connection.close = AsyncMock()
    connect_robust.return_value = connection

    result = await health_service.check_rabbitmq()

    assert result.status == "ok"
    assert result.detail is None
    connect_robust.assert_awaited_once_with(health_service._settings.rabbitmq_url)
    connection.close.assert_awaited_once()


@patch("app.services.health.aio_pika.connect_robust", new_callable=AsyncMock)
async def test_check_rabbitmq_returns_error_on_connection_failure(
    connect_robust: AsyncMock,
    health_service: HealthService,
) -> None:
    """RabbitMQ check should report error on AMQP failures."""
    connect_robust.side_effect = AMQPConnectionError("connection refused")

    result = await health_service.check_rabbitmq()

    assert result.status == "error"
    assert result.detail == SERVICE_UNAVAILABLE_DETAIL


@patch("app.services.health.aio_pika.connect_robust", new_callable=AsyncMock)
async def test_check_rabbitmq_propagates_unexpected_errors(
    connect_robust: AsyncMock,
    health_service: HealthService,
) -> None:
    """Unexpected errors during RabbitMQ check should propagate."""
    connect_robust.side_effect = RuntimeError("unexpected bug")

    with pytest.raises(RuntimeError, match="unexpected bug"):
        await health_service.check_rabbitmq()


@patch("app.services.health.aio_pika.connect_robust", new_callable=AsyncMock)
async def test_get_readiness_returns_error_when_postgres_fails(
    connect_robust: AsyncMock,
    health_service: HealthService,
) -> None:
    """Readiness should be error when PostgreSQL is unavailable."""
    session = AsyncMock()
    session.execute.side_effect = OperationalError("stmt", {}, Exception("db down"))
    connection = MagicMock()
    connection.close = AsyncMock()
    connect_robust.return_value = connection

    result = await health_service.get_readiness(session)

    assert result.status == "error"
    assert result.postgres.status == "error"
    assert result.rabbitmq.status == "ok"
