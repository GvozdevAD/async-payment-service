"""Application exception tests."""

from app.core.exceptions import (
    AppError,
    PoisonMessageError,
    UnauthorizedError,
    UnsafeWebhookUrlError,
    ValidationAppError,
)


def test_app_exception_default_detail() -> None:
    """AppError without detail should use the default safe message."""
    exc = AppError()

    assert exc.detail == "An unexpected error occurred."
    assert str(exc) == "An unexpected error occurred."


def test_validation_app_error_default_detail() -> None:
    """ValidationAppError without detail should use the default message."""
    exc = ValidationAppError()

    assert exc.detail == "The request data is invalid."


def test_unauthorized_error_default_detail() -> None:
    """UnauthorizedError without detail should use the default message."""
    exc = UnauthorizedError()

    assert exc.detail == "Invalid or missing API key."


def test_unsafe_webhook_url_error_default_detail() -> None:
    """UnsafeWebhookUrlError without detail should use the default message."""
    exc = UnsafeWebhookUrlError()

    assert exc.status_code == 422
    assert exc.detail == "The webhook URL is not allowed."


def test_poison_message_error_is_standalone() -> None:
    """PoisonMessageError should remain a plain Exception for messaging layer."""
    exc = PoisonMessageError("bad payload")

    assert isinstance(exc, Exception)
    assert not isinstance(exc, AppError)
    assert str(exc) == "bad payload"
