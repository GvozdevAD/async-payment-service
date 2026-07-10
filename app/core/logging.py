"""Application logging configuration and helpers."""

import logging
from typing import Any

from app.core.exceptions import AppException

APP_LOGGER_NAME = "app"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging for the application."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def get_logger(name: str = APP_LOGGER_NAME) -> logging.Logger:
    """Return an application logger."""
    return logging.getLogger(name)


def log_exception(
    exc: Exception,
    *,
    request_id: str | None,
    method: str,
    path: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an exception with request context.

    Application exceptions are logged as warnings. Unexpected exceptions
    include a full traceback.
    """
    logger = get_logger()
    context = {
        "request_id": request_id,
        "method": method,
        "path": path,
        **(extra or {}),
    }
    message = "Request failed: %s %s" % (method, path)

    if isinstance(exc, AppException):
        logger.warning(
            "%s | code=%s detail=%s | context=%s",
            message,
            exc.code,
            exc.detail,
            context,
        )
        return

    logger.exception("%s | context=%s", message, context)
