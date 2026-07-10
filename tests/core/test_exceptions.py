"""Application exception tests."""

from app.core.exceptions import AppException, PoisonMessageError, ValidationAppError


def test_app_exception_default_detail() -> None:
    """AppException without detail should use the default safe message."""
    exc = AppException()

    assert exc.detail == "An unexpected error occurred."
    assert str(exc) == "An unexpected error occurred."


def test_validation_app_error_default_detail() -> None:
    """ValidationAppError without detail should use the default message."""
    exc = ValidationAppError()

    assert exc.detail == "The request data is invalid."


def test_poison_message_error_is_standalone() -> None:
    """PoisonMessageError should remain a plain Exception for messaging layer."""
    exc = PoisonMessageError("bad payload")

    assert isinstance(exc, Exception)
    assert not isinstance(exc, AppException)
    assert str(exc) == "bad payload"
