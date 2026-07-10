"""Settings profile for Alembic migrations only."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MigrationSettings(BaseSettings):
    """Minimal settings required to run database migrations."""

    database_url_sync: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url_sync")
    @classmethod
    def validate_database_url_sync(cls, value: str) -> str:
        """Ensure database URL is provided and uses a PostgreSQL driver."""
        if not value.strip():
            msg = "Database URL must not be empty"
            raise ValueError(msg)
        if not value.startswith("postgresql"):
            msg = "Database URL must use a PostgreSQL driver"
            raise ValueError(msg)
        return value


@lru_cache
def get_migration_settings() -> MigrationSettings:
    """Return cached migration settings instance.

    Returns:
        Settings loaded from environment for Alembic migrations.
    """
    return MigrationSettings()
