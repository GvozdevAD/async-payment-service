"""Health check service."""

import aio_pika
from aio_pika.exceptions import AMQPError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.health import ComponentHealth, LivenessResponse, ReadinessResponse

logger = get_logger(__name__)
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable."


class HealthService:
    """Check application and infrastructure health."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_liveness(self) -> LivenessResponse:
        """Return API liveness status.

        Returns:
            Liveness response indicating the API process is running.
        """
        return LivenessResponse(status="ok")

    async def check_postgres(self, session: AsyncSession) -> ComponentHealth:
        """Verify PostgreSQL connectivity.

        Args:
            session: Active async database session.

        Returns:
            Component health with ok or error status.
        """
        try:
            await session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("PostgreSQL health check failed")
            return ComponentHealth(status="error", detail=SERVICE_UNAVAILABLE_DETAIL)
        return ComponentHealth(status="ok")

    async def check_rabbitmq(self) -> ComponentHealth:
        """Verify RabbitMQ connectivity.

        Returns:
            Component health with ok or error status.
        """
        try:
            connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
            await connection.close()
        except AMQPError:
            logger.exception("RabbitMQ health check failed")
            return ComponentHealth(status="error", detail=SERVICE_UNAVAILABLE_DETAIL)
        return ComponentHealth(status="ok")

    async def get_readiness(self, session: AsyncSession) -> ReadinessResponse:
        """Return readiness status for all dependencies.

        Args:
            session: Active async database session for PostgreSQL check.

        Returns:
            Aggregated readiness response for PostgreSQL and RabbitMQ.
        """
        postgres = await self.check_postgres(session)
        rabbitmq = await self.check_rabbitmq()

        status = (
            "ok" if postgres.status == "ok" and rabbitmq.status == "ok" else "error"
        )
        return ReadinessResponse(
            status=status,
            postgres=postgres,
            rabbitmq=rabbitmq,
        )


def get_health_service() -> HealthService:
    """Return a health service instance.

    Returns:
        Health service configured from application settings.
    """
    return HealthService(settings=get_settings())
