"""RFC 7807 Problem Details schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response body."""

    type: str = Field(description="URI reference identifying the problem type.")
    title: str = Field(description="Short, human-readable summary of the problem.")
    status: int = Field(description="HTTP status code.")
    detail: str = Field(description="Human-readable explanation of the problem.")
    instance: str | None = Field(
        default=None,
        description="URI reference identifying the specific occurrence.",
    )
    code: str = Field(description="Machine-readable application error code.")
    request_id: str | None = Field(
        default=None,
        description="Request identifier for support and log correlation.",
    )
    errors: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional field-level validation errors.",
    )
