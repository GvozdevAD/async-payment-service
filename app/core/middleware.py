"""HTTP middleware components."""

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id(request: Request | None = None) -> str | None:
    """Return the current request identifier from context or request state.

    Args:
        request: Optional request whose state should be checked first.

    Returns:
        Request ID string or None if not available.
    """
    if request is not None:
        state_request_id = getattr(request.state, "request_id", None)
        if state_request_id is not None:
            return state_request_id
    return request_id_ctx.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request identifier to each HTTP request and response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Propagate or generate a request ID for the current request.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            HTTP response with X-Request-ID header set.
        """
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        except Exception:
            request_id_ctx.reset(token)
            raise

        request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
