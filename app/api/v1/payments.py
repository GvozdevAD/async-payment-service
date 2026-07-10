"""Payment API endpoints."""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from app.api.deps import verify_api_key
from app.core.exceptions import ValidationAppError
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
)
from app.services.payment import PaymentService, get_payment_service

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(verify_api_key)],
)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x20-\x7E]+$")


def _validate_idempotency_key(value: str) -> str:
    """Validate idempotency key length and printable ASCII characters."""
    if not 1 <= len(value) <= 255:
        msg = "Idempotency-Key must be between 1 and 255 characters"
        raise ValueError(msg)
    if _IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        msg = "Idempotency-Key must contain printable ASCII characters only"
        raise ValueError(msg)
    return value


@router.post(
    "",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={"security": [{"ApiKeyAuth": []}]},
)
async def create_payment(
    body: PaymentCreateRequest,
    idempotency_key: Annotated[str, Header(alias=IDEMPOTENCY_KEY_HEADER)],
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentCreateResponse:
    """Create a new payment for asynchronous processing."""
    try:
        validated_key = _validate_idempotency_key(idempotency_key)
    except ValueError as exc:
        raise ValidationAppError(detail=str(exc)) from exc
    return await payment_service.create_payment(body, validated_key)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailResponse,
    openapi_extra={"security": [{"ApiKeyAuth": []}]},
)
async def get_payment(
    payment_id: uuid.UUID,
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentDetailResponse:
    """Return detailed information about a payment."""
    return await payment_service.get_payment(payment_id)
