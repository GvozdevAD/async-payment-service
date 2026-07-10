"""Shared pytest fixtures."""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment

TEST_API_KEY = "test-api-key-16chars"


@pytest.fixture
def api_key() -> str:
    """Return the API key used in tests."""
    return TEST_API_KEY


@pytest.fixture(autouse=True)
def configure_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure required environment variables for all tests."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("API_KEY", TEST_API_KEY)
    monkeypatch.setenv("OUTBOX_PUBLISHER_ENABLED", "false")
    monkeypatch.setenv(
        "DATABASE_URL",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://payments:payments@localhost:5432/payments",
        ),
    )
    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        os.getenv(
            "DATABASE_URL_SYNC",
            "postgresql+psycopg://payments:payments@localhost:5432/payments",
        ),
    )
    monkeypatch.setenv(
        "RABBITMQ_URL",
        os.getenv(
            "RABBITMQ_URL",
            "amqp://payments:payments@localhost:5672/payments",
        ),
    )
    monkeypatch.setenv("RABBITMQ_EXCHANGE", "payments")
    monkeypatch.setenv("RABBITMQ_PAYMENTS_NEW_QUEUE", "payments.new")
    monkeypatch.setenv("RABBITMQ_PAYMENTS_NEW_DLQ", "payments.new.dlq")
    monkeypatch.setenv("RABBITMQ_PAYMENTS_NEW_ROUTING_KEY", "payments.new")
    get_settings.cache_clear()


@pytest.fixture
async def db_session(
    configure_test_env: None,
) -> AsyncIterator[AsyncSession]:
    """Yield a database session and clean up payment-related tables."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not available: {exc}")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.execute(delete(Outbox))
            await session.execute(delete(Payment))
            await session.commit()

    await engine.dispose()


@pytest.fixture
def payment_payload() -> dict[str, object]:
    """Return a valid payment creation payload."""
    return {
        "amount": "100.50",
        "currency": "RUB",
        "description": "Test payment",
        "metadata": {"order_id": "42"},
        "webhook_url": "https://example.com/webhook",
    }


@pytest.fixture
def idempotency_key() -> str:
    """Return a unique idempotency key."""
    return f"order-{uuid.uuid4()}"
