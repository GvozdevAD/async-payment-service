"""Global FastAPI exception handlers."""

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import log_exception
from app.core.middleware import REQUEST_ID_HEADER, get_request_id
from app.schemas.error import ProblemDetail

PROBLEM_MEDIA_TYPE = "application/problem+json"


def _log_request_exception(request: Request, exc: Exception) -> None:
    """Log an exception with the current request context."""
    log_exception(
        exc,
        request_id=get_request_id(request),
        method=request.method,
        path=request.url.path,
    )


def _build_problem_detail(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    type_suffix: str,
    errors: list[dict[str, Any]] | None = None,
) -> ProblemDetail:
    """Build an RFC 7807 Problem Detail instance."""
    settings = get_settings()
    error_type_base = settings.error_type_base.rstrip("/")
    return ProblemDetail(
        type=f"{error_type_base}/{type_suffix}",
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
        code=code,
        request_id=get_request_id(request),
        errors=errors,
    )


def _problem_response(problem: ProblemDetail) -> JSONResponse:
    """Serialize a Problem Detail response."""
    response = JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )
    if problem.request_id is not None:
        response.headers[REQUEST_ID_HEADER] = problem.request_id
    return response


def build_problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    type_suffix: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build and return a Problem Detail JSON response."""
    problem = _build_problem_detail(
        request,
        status_code=status_code,
        title=title,
        detail=detail,
        code=code,
        type_suffix=type_suffix,
        errors=errors,
    )
    return _problem_response(problem)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle application-specific exceptions."""
    _log_request_exception(request, exc)
    problem = _build_problem_detail(
        request,
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        code=exc.code,
        type_suffix=exc.type_suffix,
    )
    return _problem_response(problem)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle request validation errors."""
    _log_request_exception(request, exc)
    return build_problem_response(
        request,
        status_code=422,
        title="Validation Error",
        detail="Invalid request data.",
        code="validation_error",
        type_suffix="validation-error",
        errors=list(exc.errors()),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle legacy HTTP exceptions."""
    _log_request_exception(request, exc)
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return build_problem_response(
        request,
        status_code=exc.status_code,
        title="Request Error",
        detail=detail,
        code="http_error",
        type_suffix="http-error",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    _log_request_exception(request, exc)
    return build_problem_response(
        request,
        status_code=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        code="internal_error",
        type_suffix="internal-error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
