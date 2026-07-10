"""FastAPI dependencies."""

import secrets
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_session

get_db = get_session

API_KEY_HEADER = "X-API-Key"


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate the static API key from the request header."""
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise UnauthorizedError()
