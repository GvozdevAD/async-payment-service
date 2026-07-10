"""FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.router import router as api_v1_router
from app.core.settings import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.db.session import close_db, get_async_sessionmaker, init_db
from app.messaging.broker import create_broker
from app.services.outbox_publisher import create_outbox_publisher
from app.services.webhook_dispatcher import create_webhook_dispatcher
from app.version import get_version


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and tear down application resources.

    Args:
        app: FastAPI application instance.

    Yields:
        Control to the running application after startup completes.
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    await init_db()

    publisher_task: asyncio.Task[None] | None = None
    publisher = None
    if settings.outbox_publisher_enabled:
        publisher = create_outbox_publisher(
            settings=settings,
            session_factory=get_async_sessionmaker(),
            broker=create_broker(settings.rabbitmq_url),
        )
        await publisher.start()
        publisher_task = asyncio.create_task(publisher.run_forever())

    dispatcher_task: asyncio.Task[None] | None = None
    dispatcher = None
    if settings.webhook_dispatcher_enabled:
        dispatcher = create_webhook_dispatcher(
            settings=settings,
            session_factory=get_async_sessionmaker(),
        )
        await dispatcher.start()
        dispatcher_task = asyncio.create_task(dispatcher.run_forever())

    yield

    if dispatcher_task is not None:
        dispatcher_task.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher_task
    if dispatcher is not None:
        await dispatcher.stop()
    if publisher_task is not None:
        publisher_task.cancel()
        with suppress(asyncio.CancelledError):
            await publisher_task
    if publisher is not None:
        await publisher.stop()
    await close_db()


app = FastAPI(
    title="Async Payment Processing Service",
    description=(
        "A microservice for asynchronous payment processing. "
        "Accepts payment requests, processes them through an external "
        "payment gateway (emulation), and notifies the client of the result via webhook."
    ),
    version=get_version(),
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    openapi_components={
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            },
        },
    },
)

app.add_middleware(RequestIdMiddleware)
register_exception_handlers(app)
app.include_router(api_v1_router)
