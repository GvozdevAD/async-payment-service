"""Webhook delivery dispatcher process."""

import asyncio

from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.core.telemetry import (
    instrument_httpx,
    instrument_logging,
    instrument_sqlalchemy_if_ready,
    setup_observability,
    shutdown_observability,
)
from app.db.session import close_db, get_async_sessionmaker, init_db
from app.services.webhook_dispatcher import create_webhook_dispatcher


async def main() -> None:
    """Run the webhook dispatcher until interrupted.

    Initializes database connection, polls pending webhook deliveries,
    and shuts down resources on exit.
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    observability = setup_observability(
        service_name="webhook-dispatcher",
        settings=settings,
    )
    instrument_logging()
    instrument_httpx()
    await init_db()
    instrument_sqlalchemy_if_ready()

    dispatcher = create_webhook_dispatcher(
        settings=settings,
        session_factory=get_async_sessionmaker(),
    )
    await dispatcher.start()
    try:
        await dispatcher.run_forever()
    finally:
        await dispatcher.stop()
        await close_db()
        shutdown_observability(observability)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
