"""API exception handler tests."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.exception_handlers import PROBLEM_MEDIA_TYPE, register_exception_handlers
from app.core.exceptions import PaymentNotFoundError
from app.core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware


@pytest.fixture
def app() -> FastAPI:
    """Return a FastAPI app with exception handlers registered."""
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(test_app)

    @test_app.get("/test/app-error")
    async def app_error() -> None:
        raise PaymentNotFoundError()

    @test_app.get("/test/unhandled")
    async def unhandled_error() -> None:
        raise RuntimeError("secret internal error")

    @test_app.get("/test/validation")
    async def validation_error(required_query: int) -> None:
        pass

    @test_app.get("/test/http-error")
    async def http_error() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail={"field": "invalid"})

    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an async HTTP client bound to the test application."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_app_exception_returns_problem_detail(client: AsyncClient) -> None:
    """Application exceptions should return RFC 7807 responses."""
    response = await client.get("/test/app-error")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert body["code"] == "payment_not_found"
    assert body["title"] == "Payment Not Found"
    assert body["detail"] == "The requested payment was not found."
    assert body["status"] == 404
    assert body["type"].endswith("/payment-not-found")
    assert body["instance"] == "/test/app-error"
    assert body["request_id"] is not None
    assert response.headers[REQUEST_ID_HEADER] == body["request_id"]


async def test_unhandled_exception_returns_safe_message(client: AsyncClient) -> None:
    """Unexpected exceptions should not expose internal details."""
    response = await client.get("/test/unhandled")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["detail"] == "An unexpected error occurred."
    assert "secret internal error" not in response.text
    assert "Traceback" not in response.text
    assert body["request_id"] is not None
    assert response.headers[REQUEST_ID_HEADER] == body["request_id"]


async def test_request_id_is_propagated_from_header(client: AsyncClient) -> None:
    """Provided X-Request-ID should be echoed in the response."""
    request_id = "test-request-id-123"
    response = await client.get(
        "/test/app-error",
        headers={REQUEST_ID_HEADER: request_id},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json()["request_id"] == request_id


async def test_validation_error_returns_problem_detail(client: AsyncClient) -> None:
    """Request validation errors should return RFC 7807 responses."""
    response = await client.get("/test/validation")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["title"] == "Validation Error"
    assert body["detail"] == "Invalid request data."
    assert body["status"] == 422
    assert body["type"].endswith("/validation-error")
    assert body["errors"] is not None
    assert len(body["errors"]) > 0


async def test_http_exception_non_string_detail(client: AsyncClient) -> None:
    """HTTPException with non-string detail should use a safe fallback message."""
    response = await client.get("/test/http-error")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "http_error"
    assert body["detail"] == "Request failed."
