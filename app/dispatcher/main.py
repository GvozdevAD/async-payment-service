"""Webhook delivery dispatcher process."""

import asyncio

from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.db.session import close_db, get_async_sessionmaker, init_db
from app.services.webhook_dispatcher import create_webhook_dispatcher


async def main() -> None:
    """Run the webhook dispatcher until interrupted.

    Initializes database connection, polls pending webhook deliveries,
    and shuts down resources on exit.
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    await init_db()

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


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
