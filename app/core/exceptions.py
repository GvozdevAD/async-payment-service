"""Application-specific exceptions with safe client-facing messages."""


class AppError(Exception):
    """Base application exception with a safe client message."""

    status_code: int = 500
    code: str = "internal_error"
    title: str = "Internal Server Error"
    type_suffix: str = "internal-error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail()
        super().__init__(self.detail)

    def default_detail(self) -> str:
        """Return the default safe error message for clients."""
        return "An unexpected error occurred."


class UnauthorizedError(AppError):
    """Raised when API key authentication fails."""

    status_code = 401
    code = "unauthorized"
    title = "Unauthorized"
    type_suffix = "unauthorized"

    def default_detail(self) -> str:
        return "Invalid or missing API key."


class PaymentNotFoundError(AppError):
    """Raised when a payment cannot be found."""

    status_code = 404
    code = "payment_not_found"
    title = "Payment Not Found"
    type_suffix = "payment-not-found"

    def default_detail(self) -> str:
        return "The requested payment was not found."


class PoisonMessageError(Exception):
    """Unrecoverable queue message — should be rejected to DLQ.

    Intentionally not an AppError: this is a messaging-layer error,
    not an HTTP API error.
    """


class ValidationAppError(AppError):
    """Raised for business-level validation failures."""

    status_code = 422
    code = "validation_error"
    title = "Validation Error"
    type_suffix = "validation-error"

    def default_detail(self) -> str:
        return "The request data is invalid."
