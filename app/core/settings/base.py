"""Shared application settings loaded from environment variables."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """Shared settings — all env-backed fields and validators."""

    database_url: str
    database_url_sync: str
    rabbitmq_url: str
    api_key: str
    error_type_base: str = "https://payments.local/errors"
    log_level: str = "INFO"

    outbox_poll_interval_seconds: float = 5.0
    outbox_batch_size: int = 10
    outbox_publish_max_attempts: int = 3

    rabbitmq_exchange: str
    rabbitmq_payments_new_queue: str
    rabbitmq_payments_new_dlq: str
    rabbitmq_payments_new_routing_key: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", "database_url_sync")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Ensure database URL is provided and uses a PostgreSQL driver."""
        if not value.strip():
            msg = "Database URL must not be empty"
            raise ValueError(msg)
        if not value.startswith("postgresql"):
            msg = "Database URL must use a PostgreSQL driver"
            raise ValueError(msg)
        return value

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        """Ensure API key is provided and meets minimum length."""
        if not value.strip():
            msg = "API key must not be empty"
            raise ValueError(msg)
        if len(value) < 16:
            msg = "API key must be at least 16 characters long"
            raise ValueError(msg)
        return value

    @field_validator("rabbitmq_url")
    @classmethod
    def validate_rabbitmq_url(cls, value: str) -> str:
        """Ensure RabbitMQ URL is provided and uses AMQP."""
        if not value.strip():
            msg = "RabbitMQ URL must not be empty"
            raise ValueError(msg)
        if not value.startswith("amqp"):
            msg = "RabbitMQ URL must use an AMQP scheme"
            raise ValueError(msg)
        return value

    @field_validator("outbox_batch_size")
    @classmethod
    def validate_outbox_batch_size(cls, value: int) -> int:
        """Ensure outbox batch size is positive."""
        if value < 1:
            msg = "Outbox batch size must be at least 1"
            raise ValueError(msg)
        return value

    @field_validator("outbox_poll_interval_seconds")
    @classmethod
    def validate_outbox_poll_interval(cls, value: float) -> float:
        """Ensure outbox poll interval is positive."""
        if value <= 0:
            msg = "Outbox poll interval must be greater than 0"
            raise ValueError(msg)
        return value

    @field_validator("outbox_publish_max_attempts")
    @classmethod
    def validate_outbox_publish_max_attempts(cls, value: int) -> int:
        """Ensure publish retry count is positive."""
        if value < 1:
            msg = "Outbox publish max attempts must be at least 1"
            raise ValueError(msg)
        return value
