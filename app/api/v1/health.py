"""Health check API endpoints."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import HealthService, get_health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=LivenessResponse)
async def liveness(
    health_service: HealthService = Depends(get_health_service),
) -> LivenessResponse:
    """Return API liveness status."""
    return health_service.get_liveness()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    session: AsyncSession = Depends(get_db),
    health_service: HealthService = Depends(get_health_service),
) -> ReadinessResponse:
    """Return API readiness status including PostgreSQL and RabbitMQ."""
    result = await health_service.get_readiness(session)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
