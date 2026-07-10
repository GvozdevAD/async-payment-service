"""Shared application settings loaded from environment variables."""

from pydantic import ValidationInfo, field_validator
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

    gateway_min_delay_seconds: float = 2.0
    gateway_max_delay_seconds: float = 5.0
    gateway_success_rate: float = 0.9

    webhook_max_attempts: int = 3
    webhook_timeout_seconds: float = 10.0

    webhook_dispatcher_poll_interval_seconds: float = 5.0
    webhook_dispatcher_batch_size: int = 10

    consumer_max_attempts: int = 3
    consumer_prefetch_count: int = 10

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

    @field_validator("gateway_min_delay_seconds")
    @classmethod
    def validate_gateway_min_delay(cls, value: float) -> float:
        """Ensure gateway minimum delay is positive."""
        if value <= 0:
            msg = "Gateway min delay must be greater than 0"
            raise ValueError(msg)
        return value

    @field_validator("gateway_max_delay_seconds")
    @classmethod
    def validate_gateway_max_delay(cls, value: float, info: ValidationInfo) -> float:
        """Ensure gateway max delay is not below min delay."""
        min_delay = info.data.get("gateway_min_delay_seconds", 0.0)
        if value < min_delay:
            msg = "Gateway max delay must be >= min delay"
            raise ValueError(msg)
        return value

    @field_validator("gateway_success_rate")
    @classmethod
    def validate_gateway_success_rate(cls, value: float) -> float:
        """Ensure gateway success rate is within (0, 1]."""
        if value <= 0 or value > 1:
            msg = "Gateway success rate must be in (0, 1]"
            raise ValueError(msg)
        return value

    @field_validator("webhook_max_attempts", "consumer_max_attempts")
    @classmethod
    def validate_retry_attempts(cls, value: int) -> int:
        """Ensure retry attempt counts are positive."""
        if value < 1:
            msg = "Retry attempts must be at least 1"
            raise ValueError(msg)
        return value

    @field_validator("webhook_timeout_seconds")
    @classmethod
    def validate_webhook_timeout(cls, value: float) -> float:
        """Ensure webhook timeout is positive."""
        if value <= 0:
            msg = "Webhook timeout must be greater than 0"
            raise ValueError(msg)
        return value

    @field_validator("webhook_dispatcher_batch_size")
    @classmethod
    def validate_webhook_dispatcher_batch_size(cls, value: int) -> int:
        """Ensure webhook dispatcher batch size is positive."""
        if value < 1:
            msg = "Webhook dispatcher batch size must be at least 1"
            raise ValueError(msg)
        return value

    @field_validator("webhook_dispatcher_poll_interval_seconds")
    @classmethod
    def validate_webhook_dispatcher_poll_interval(cls, value: float) -> float:
        """Ensure webhook dispatcher poll interval is positive."""
        if value <= 0:
            msg = "Webhook dispatcher poll interval must be greater than 0"
            raise ValueError(msg)
        return value

    @field_validator("consumer_prefetch_count")
    @classmethod
    def validate_consumer_prefetch_count(cls, value: int) -> int:
        """Ensure consumer prefetch count is positive."""
        if value < 1:
            msg = "Consumer prefetch count must be at least 1"
            raise ValueError(msg)
        return value
