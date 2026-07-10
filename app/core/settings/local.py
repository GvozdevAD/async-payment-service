"""Development settings profile."""

from app.core.settings.base import BaseAppSettings


class LocalSettings(BaseAppSettings):
    """Development profile — defaults only, overridable via env."""

    outbox_publisher_enabled: bool = True
    webhook_dispatcher_enabled: bool = True
    log_level: str = "INFO"
