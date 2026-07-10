"""Application settings profiles and factory."""

import os
from functools import lru_cache

from app.core.settings.base import BaseAppSettings
from app.core.settings.local import LocalSettings
from app.core.settings.production import ProductionSettings

Settings = LocalSettings | ProductionSettings


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for the active APP_ENV profile.

    Returns:
        Settings instance for the local or production profile.

    Raises:
        ValueError: If APP_ENV is not supported.
    """
    app_env = os.getenv("APP_ENV", "local").lower()
    if app_env == "production":
        return ProductionSettings()
    if app_env == "local":
        return LocalSettings()
    msg = f"Unsupported APP_ENV: {app_env}"
    raise ValueError(msg)


__all__ = [
    "BaseAppSettings",
    "LocalSettings",
    "ProductionSettings",
    "Settings",
    "get_settings",
]
