"""Application settings tests."""

import pytest
from pydantic import ValidationError

from app.core.settings import get_settings
from app.core.settings.local import LocalSettings
from app.core.settings.migration import get_migration_settings
from app.core.settings.production import ProductionSettings

VALID_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://payments:payments@localhost:5432/payments",
    "DATABASE_URL_SYNC": "postgresql+psycopg://payments:payments@localhost:5432/payments",
    "RABBITMQ_URL": "amqp://payments:payments@localhost:5672/payments",
    "API_KEY": "test-api-key-16chars",
    "RABBITMQ_EXCHANGE": "payments",
    "RABBITMQ_PAYMENTS_NEW_QUEUE": "payments.new",
    "RABBITMQ_PAYMENTS_NEW_DLQ": "payments.new.dlq",
    "RABBITMQ_PAYMENTS_NEW_ROUTING_KEY": "payments.new",
}


def _apply_env(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None
) -> None:
    """Set valid base environment variables for settings construction."""
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    if overrides:
        for key, value in overrides.items():
            monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    get_migration_settings.cache_clear()


def test_get_settings_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local profile should enable embedded outbox publisher by default."""
    _apply_env(
        monkeypatch,
        {
            "OUTBOX_PUBLISHER_ENABLED": "true",
            "WEBHOOK_DISPATCHER_ENABLED": "true",
        },
    )
    monkeypatch.setenv("APP_ENV", "local")

    settings = get_settings()

    assert isinstance(settings, LocalSettings)
    assert settings.outbox_publisher_enabled is True
    assert settings.webhook_dispatcher_enabled is True


def test_get_settings_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production profile should disable embedded outbox publisher by default."""
    _apply_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    settings = get_settings()

    assert isinstance(settings, ProductionSettings)
    assert settings.outbox_publisher_enabled is False
    assert settings.webhook_dispatcher_enabled is False


def test_get_settings_unsupported_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported APP_ENV should raise ValueError."""
    _apply_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")

    with pytest.raises(ValueError, match="Unsupported APP_ENV"):
        get_settings()


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("DATABASE_URL", "", "must not be empty"),
        ("DATABASE_URL", "mysql://localhost/db", "PostgreSQL driver"),
        ("DATABASE_URL_SYNC", "", "must not be empty"),
        ("DATABASE_URL_SYNC", "sqlite:///db", "PostgreSQL driver"),
        ("API_KEY", "", "must not be empty"),
        ("API_KEY", "short-key", "at least 16 characters"),
        ("RABBITMQ_URL", "", "must not be empty"),
        ("RABBITMQ_URL", "http://localhost", "AMQP scheme"),
        ("OUTBOX_BATCH_SIZE", "0", "at least 1"),
        ("OUTBOX_POLL_INTERVAL_SECONDS", "0", "greater than 0"),
        ("OUTBOX_PUBLISH_MAX_ATTEMPTS", "0", "at least 1"),
        ("GATEWAY_MIN_DELAY_SECONDS", "0", "greater than 0"),
        ("GATEWAY_SUCCESS_RATE", "0", "in \\(0, 1\\]"),
        ("GATEWAY_SUCCESS_RATE", "1.5", "in \\(0, 1\\]"),
        ("WEBHOOK_MAX_ATTEMPTS", "0", "at least 1"),
        ("WEBHOOK_TIMEOUT_SECONDS", "0", "greater than 0"),
        ("WEBHOOK_DISPATCHER_BATCH_SIZE", "0", "at least 1"),
        ("WEBHOOK_DISPATCHER_POLL_INTERVAL_SECONDS", "0", "greater than 0"),
        ("CONSUMER_MAX_ATTEMPTS", "0", "at least 1"),
        ("CONSUMER_PREFETCH_COUNT", "0", "at least 1"),
    ],
)
def test_base_settings_validators_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    match: str,
) -> None:
    """Base settings validators should reject invalid configuration."""
    _apply_env(monkeypatch, {field: value})

    with pytest.raises(ValidationError, match=match):
        LocalSettings()


def test_gateway_max_delay_must_be_gte_min_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway max delay must not be below min delay."""
    _apply_env(
        monkeypatch,
        {
            "GATEWAY_MIN_DELAY_SECONDS": "5",
            "GATEWAY_MAX_DELAY_SECONDS": "2",
        },
    )

    with pytest.raises(ValidationError, match="max delay must be >= min delay"):
        LocalSettings()


def test_migration_settings_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Migration settings should load a valid sync database URL."""
    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg://payments:payments@localhost:5432/payments",
    )
    get_migration_settings.cache_clear()

    settings = get_migration_settings()

    assert settings.database_url_sync.startswith("postgresql")


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("", "must not be empty"),
        ("sqlite:///db", "PostgreSQL driver"),
    ],
)
def test_migration_settings_invalid_url(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    match: str,
) -> None:
    """Migration settings should reject invalid database URLs."""
    monkeypatch.setenv("DATABASE_URL_SYNC", value)
    get_migration_settings.cache_clear()

    with pytest.raises(ValidationError, match=match):
        get_migration_settings()
