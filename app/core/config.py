"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    database_url: str
    database_url_sync: str
    rabbitmq_url: str
    api_key: str
    error_type_base: str = "https://payments.local/errors"
    log_level: str = "INFO"

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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
