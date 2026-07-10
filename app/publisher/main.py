"""Standalone outbox publisher process."""

import asyncio

from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.core.telemetry import (
    instrument_logging,
    instrument_sqlalchemy_if_ready,
    setup_observability,
    shutdown_observability,
)
from app.db.session import close_db, get_async_sessionmaker, init_db
from app.messaging.broker import create_broker
from app.services.outbox_publisher import create_outbox_publisher


async def main() -> None:
    """Run the outbox publisher until interrupted.

    Initializes database and RabbitMQ connections, polls pending outbox
    records, and shuts down resources on exit.
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    observability = setup_observability(service_name="publisher", settings=settings)
    instrument_logging()
    await init_db()
    instrument_sqlalchemy_if_ready()

    publisher = create_outbox_publisher(
        settings=settings,
        session_factory=get_async_sessionmaker(),
        broker=create_broker(settings.rabbitmq_url),
    )
    await publisher.start()
    try:
        await publisher.run_forever()
    finally:
        await publisher.stop()
        await close_db()
        shutdown_observability(observability)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
