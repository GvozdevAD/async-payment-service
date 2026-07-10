"""FastAPI dependencies."""

import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.settings import Settings, get_settings
from app.db.session import get_session
from app.repositories.outbox import OutboxRepository
from app.repositories.payment import PaymentRepository
from app.services.payment import PaymentService

get_db = get_session

API_KEY_HEADER = "X-API-Key"


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate the static API key from the request header."""
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise UnauthorizedError()


def get_payment_service(
    session: AsyncSession = Depends(get_db),
) -> PaymentService:
    """Return a payment service bound to the request database session."""
    return PaymentService(
        session=session,
        payment_repo=PaymentRepository(session),
        outbox_repo=OutboxRepository(session),
    )
