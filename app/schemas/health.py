"""Health check API schemas."""

from typing import Literal

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    """Health status of a single infrastructure component."""

    status: Literal["ok", "error"]
    detail: str | None = None


class LivenessResponse(BaseModel):
    """Response for the API liveness probe."""

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    """Response for the API readiness probe."""

    status: Literal["ok", "error"]
    postgres: ComponentHealth
    rabbitmq: ComponentHealth
