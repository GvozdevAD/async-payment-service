"""Request ID middleware tests."""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from app.core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware, get_request_id


def test_get_request_id_from_request_state() -> None:
    """get_request_id should prefer the value stored on request.state."""
    request = MagicMock(spec=Request)
    request.state.request_id = "from-state"

    assert get_request_id(request) == "from-state"


def test_get_request_id_falls_back_to_context() -> None:
    """get_request_id should fall back to the context variable."""
    request = MagicMock(spec=Request)
    request.state.request_id = None

    assert get_request_id(request) is None


async def _echo_request_id(request: Request) -> Response:
    """Return the request id attached by middleware."""
    return Response(request.state.request_id, media_type="text/plain")


@pytest.fixture
def middleware_app() -> Starlette:
    """Return a Starlette app with request ID middleware."""
    app = Starlette(routes=[Route("/", _echo_request_id)])
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture
async def middleware_client(middleware_app: Starlette) -> AsyncClient:
    """Return an HTTP client for middleware integration tests."""
    transport = ASGITransport(app=middleware_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_request_id_middleware_propagates_incoming_header(
    middleware_client: AsyncClient,
) -> None:
    """Provided X-Request-ID should be attached to request state and echoed back."""
    response = await middleware_client.get(
        "/",
        headers={REQUEST_ID_HEADER: "incoming-request-id"},
    )

    assert response.status_code == 200
    assert response.text == "incoming-request-id"
    assert response.headers[REQUEST_ID_HEADER] == "incoming-request-id"


async def test_request_id_middleware_generates_id_when_missing(
    middleware_client: AsyncClient,
) -> None:
    """Missing X-Request-ID should be generated and returned in the response."""
    response = await middleware_client.get("/")

    assert response.status_code == 200
    assert response.text
    assert response.headers[REQUEST_ID_HEADER] == response.text


async def test_request_id_is_added_to_active_span(
    middleware_client: AsyncClient,
) -> None:
    """Middleware should attach request.id to the active recording span."""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("http_request") as span:
        response = await middleware_client.get(
            "/",
            headers={REQUEST_ID_HEADER: "span-request-id"},
        )

    assert response.status_code == 200
    assert span.attributes.get("request.id") == "span-request-id"
