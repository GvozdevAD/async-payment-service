"""Payment API endpoint tests."""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import API_KEY_HEADER, get_db, get_payment_service
from app.api.exception_handlers import register_exception_handlers
from app.api.v1 import health, payments
from app.core.middleware import RequestIdMiddleware
from app.repositories.outbox import OutboxRepository
from app.repositories.payment import PaymentRepository
from app.services.payment import PaymentService
from tests.conftest import TEST_API_KEY


@pytest.fixture
def payments_app(configure_test_env: None) -> FastAPI:
    """Return a FastAPI app with payment and health routes."""
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(test_app)
    test_app.include_router(health.router, prefix="/api/v1")
    test_app.include_router(payments.router, prefix="/api/v1")
    return test_app


@pytest.fixture
async def payments_client(
    payments_app: FastAPI,
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """Return an async HTTP client with database overrides."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    def override_get_payment_service() -> PaymentService:
        return PaymentService(
            session=db_session,
            payment_repo=PaymentRepository(db_session),
            outbox_repo=OutboxRepository(db_session),
        )

    payments_app.dependency_overrides[get_db] = override_get_db
    payments_app.dependency_overrides[get_payment_service] = (
        override_get_payment_service
    )

    transport = ASGITransport(app=payments_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

    payments_app.dependency_overrides.clear()


async def test_create_payment_without_api_key_returns_401(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
    idempotency_key: str,
) -> None:
    """Missing API key should return unauthorized."""
    response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers={"Idempotency-Key": idempotency_key},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_create_payment_with_invalid_api_key_returns_401(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
    idempotency_key: str,
) -> None:
    """Invalid API key should return unauthorized."""
    response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers={
            API_KEY_HEADER: "invalid-api-key-value",
            "Idempotency-Key": idempotency_key,
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_create_payment_success_returns_202(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
    idempotency_key: str,
) -> None:
    """Valid request should create a payment and return 202."""
    response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers={
            API_KEY_HEADER: TEST_API_KEY,
            "Idempotency-Key": idempotency_key,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert uuid.UUID(body["payment_id"])
    assert body["created_at"] is not None


async def test_create_payment_without_idempotency_key_returns_422(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
) -> None:
    """Missing idempotency key should return validation error."""
    response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers={API_KEY_HEADER: TEST_API_KEY},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_create_payment_idempotent_returns_same_payment(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
    idempotency_key: str,
) -> None:
    """Repeating the same idempotency key should return the same payment."""
    headers = {
        API_KEY_HEADER: TEST_API_KEY,
        "Idempotency-Key": idempotency_key,
    }
    first_response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers=headers,
    )
    second_response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers=headers,
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert first_response.json()["payment_id"] == second_response.json()["payment_id"]


async def test_get_payment_success(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
    idempotency_key: str,
) -> None:
    """Created payment should be retrievable by id."""
    create_response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers={
            API_KEY_HEADER: TEST_API_KEY,
            "Idempotency-Key": idempotency_key,
        },
    )
    payment_id = create_response.json()["payment_id"]

    response = await payments_client.get(
        f"/api/v1/payments/{payment_id}",
        headers={API_KEY_HEADER: TEST_API_KEY},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payment_id"] == payment_id
    assert body["amount"] == "100.50"
    assert body["currency"] == "RUB"
    assert body["description"] == "Test payment"
    assert body["metadata"] == {"order_id": "42"}
    assert body["status"] == "pending"
    assert body["webhook_url"].startswith("https://example.com/webhook")


async def test_get_payment_not_found_returns_404(
    payments_client: AsyncClient,
) -> None:
    """Unknown payment id should return not found."""
    response = await payments_client.get(
        f"/api/v1/payments/{uuid.uuid4()}",
        headers={API_KEY_HEADER: TEST_API_KEY},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "payment_not_found"


async def test_create_payment_invalid_idempotency_key_too_long(
    payments_client: AsyncClient,
    payment_payload: dict[str, object],
) -> None:
    """Idempotency key longer than 255 characters should return validation error."""
    response = await payments_client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers={
            API_KEY_HEADER: TEST_API_KEY,
            "Idempotency-Key": "x" * 256,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "255 characters" in response.json()["detail"]


async def test_create_payment_invalid_idempotency_key_non_ascii(
    payment_payload: dict[str, object],
) -> None:
    """Non-ASCII idempotency key should return validation error."""
    from unittest.mock import AsyncMock

    from app.api.v1.payments import _validate_idempotency_key, create_payment
    from app.core.exceptions import ValidationAppError
    from app.schemas.payment import PaymentCreateRequest

    with pytest.raises(ValueError, match="printable ASCII"):
        _validate_idempotency_key("ключ-emoji")

    body = PaymentCreateRequest.model_validate(payment_payload)
    service = AsyncMock()

    with pytest.raises(ValidationAppError, match="printable ASCII"):
        await create_payment(body, "ключ-emoji", service)

    service.create_payment.assert_not_called()


async def test_create_payment_amount_too_many_decimals_returns_422(
    payments_client: AsyncClient,
    idempotency_key: str,
) -> None:
    """Amount with more than two decimal places should return validation error."""
    payload = {
        "amount": "10.999",
        "currency": "RUB",
        "description": "Too precise",
        "metadata": {},
        "webhook_url": "https://example.com/webhook",
    }
    response = await payments_client.post(
        "/api/v1/payments",
        json=payload,
        headers={
            API_KEY_HEADER: TEST_API_KEY,
            "Idempotency-Key": idempotency_key,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_health_still_works_without_api_key(
    payments_client: AsyncClient,
) -> None:
    """Health endpoint should remain accessible without authentication."""
    response = await payments_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
