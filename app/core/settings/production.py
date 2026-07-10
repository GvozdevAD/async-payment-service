"""Production settings profile."""

from app.core.settings.base import BaseAppSettings


class ProductionSettings(BaseAppSettings):
    """Production profile — defaults only, overridable via env."""

    outbox_publisher_enabled: bool = False
    log_level: str = "INFO"
