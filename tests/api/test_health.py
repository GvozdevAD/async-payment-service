"""Health API endpoint tests."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.v1 import health
from app.schemas.health import ComponentHealth, ReadinessResponse
from app.services.health import HealthService, get_health_service


@pytest.fixture
def health_app() -> FastAPI:
    """Return a FastAPI app with only the health router."""
    test_app = FastAPI()
    test_app.include_router(health.router, prefix="/api/v1")
    return test_app


@pytest.fixture
async def health_client(health_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an async HTTP client bound to the health test application."""
    transport = ASGITransport(app=health_app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_liveness_returns_ok(health_client: AsyncClient) -> None:
    """Liveness endpoint should always return 200 with status ok."""
    response = await health_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_returns_ok_when_dependencies_are_healthy(
    health_app: FastAPI,
    health_client: AsyncClient,
) -> None:
    """Readiness should return 200 when all dependencies are healthy."""
    mock_service = AsyncMock(spec=HealthService)
    mock_service.get_readiness.return_value = ReadinessResponse(
        status="ok",
        postgres=ComponentHealth(status="ok"),
        rabbitmq=ComponentHealth(status="ok"),
    )

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    health_app.dependency_overrides[get_db] = override_get_db
    health_app.dependency_overrides[get_health_service] = lambda: mock_service

    response = await health_client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"]["status"] == "ok"
    assert body["rabbitmq"]["status"] == "ok"


async def test_readiness_returns_503_when_dependencies_are_degraded(
    health_app: FastAPI,
    health_client: AsyncClient,
) -> None:
    """Readiness should return 503 when a dependency is unhealthy."""
    mock_service = AsyncMock(spec=HealthService)
    mock_service.get_readiness.return_value = ReadinessResponse(
        status="error",
        postgres=ComponentHealth(
            status="error",
            detail="Service unavailable.",
        ),
        rabbitmq=ComponentHealth(status="ok"),
    )

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    health_app.dependency_overrides[get_db] = override_get_db
    health_app.dependency_overrides[get_health_service] = lambda: mock_service

    response = await health_client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["postgres"]["status"] == "error"
    assert body["postgres"]["detail"] == "Service unavailable."
    assert body["rabbitmq"]["status"] == "ok"
