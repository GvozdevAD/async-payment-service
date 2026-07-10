"""Payment consumer process entrypoint."""

import asyncio

from faststream import FastStream

from app.consumer.handlers import register_handlers
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
from app.messaging.topology import declare_topology
from app.services.payment_processor import create_payment_processor


async def main() -> None:
    """Run the payment consumer until interrupted.

    Initializes database and RabbitMQ connections, registers payment-new
    handlers, and shuts down resources on exit.
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    observability = setup_observability(service_name="consumer", settings=settings)
    instrument_logging()
    await init_db()
    instrument_sqlalchemy_if_ready()

    broker = create_broker(settings.rabbitmq_url)
    processor = create_payment_processor(settings, get_async_sessionmaker())
    register_handlers(broker, processor, settings)

    app = FastStream(broker)

    @app.after_startup
    async def declare_broker_topology() -> None:
        await declare_topology(broker, settings)

    try:
        await app.run()
    finally:
        await close_db()
        shutdown_observability(observability)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
