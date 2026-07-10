"""API dependency unit tests without PostgreSQL."""

from unittest.mock import MagicMock

import pytest

from app.api.deps import get_payment_service, verify_api_key
from app.core.exceptions import UnauthorizedError
from app.core.settings import get_settings
from app.services.payment import PaymentService


async def test_verify_api_key_raises_when_missing() -> None:
    """Missing API key should raise UnauthorizedError."""
    settings = get_settings()

    with pytest.raises(UnauthorizedError):
        await verify_api_key(x_api_key=None, settings=settings)


async def test_verify_api_key_raises_when_invalid() -> None:
    """Invalid API key should raise UnauthorizedError."""
    settings = get_settings()

    with pytest.raises(UnauthorizedError):
        await verify_api_key(x_api_key="wrong-api-key", settings=settings)


def test_get_payment_service_builds_payment_service() -> None:
    """get_payment_service should wire repositories to PaymentService."""
    session = MagicMock()

    service = get_payment_service(session=session)

    assert isinstance(service, PaymentService)
