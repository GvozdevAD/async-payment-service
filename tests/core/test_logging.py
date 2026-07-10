"""Logging helper tests."""

import logging

from app.core.logging import get_logger, log_exception, setup_logging
from app.core.exceptions import AppException, PaymentNotFoundError


def test_setup_logging_configures_root_level() -> None:
    """setup_logging should configure the root logger level."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    setup_logging("DEBUG")

    assert root.level == logging.DEBUG


def test_get_logger_returns_named_logger() -> None:
    """get_logger should return a logger with the requested name."""
    logger = get_logger("app.test")

    assert logger.name == "app.test"


def test_log_exception_app_exception_logs_warning(caplog) -> None:
    """Application exceptions should be logged as warnings without traceback."""
    exc = PaymentNotFoundError()

    with caplog.at_level(logging.WARNING):
        log_exception(exc, request_id="req-1", method="GET", path="/payments/1")

    assert "Request failed: GET /payments/1" in caplog.text
    assert "payment_not_found" in caplog.text


def test_log_exception_unexpected_logs_traceback(caplog) -> None:
    """Unexpected exceptions should be logged with traceback."""
    exc = RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="app"):
        log_exception(exc, request_id="req-2", method="POST", path="/payments")

    assert "Request failed: POST /payments" in caplog.text
    assert any(record.exc_info is not None for record in caplog.records)


def test_log_exception_base_app_exception_uses_default_detail(caplog) -> None:
    """Base AppException should use its default safe detail message."""
    exc = AppException()

    with caplog.at_level(logging.WARNING):
        log_exception(exc, request_id=None, method="GET", path="/")

    assert "internal_error" in caplog.text
