"""Standalone outbox publisher process."""

import asyncio

from app.core.settings import get_settings
from app.core.logging import setup_logging
from app.db.session import close_db, get_async_sessionmaker, init_db
from app.messaging.broker import create_broker
from app.services.outbox_publisher import create_outbox_publisher


async def main() -> None:
    """Run the outbox publisher until interrupted."""
    settings = get_settings()
    setup_logging(settings.log_level)
    await init_db()

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


if __name__ == "__main__":
    asyncio.run(main())
