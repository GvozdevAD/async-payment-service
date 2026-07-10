"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.db.session import close_db, init_db
from app.version import get_version


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and tear down application resources."""
    settings = get_settings()
    setup_logging(settings.log_level)
    await init_db()
    yield
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
