"""Application-specific exceptions with safe client-facing messages."""


class AppException(Exception):
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


class UnauthorizedError(AppException):
    """Raised when API key authentication fails."""

    status_code = 401
    code = "unauthorized"
    title = "Unauthorized"
    type_suffix = "unauthorized"

    def default_detail(self) -> str:
        return "Invalid or missing API key."


class PaymentNotFoundError(AppException):
    """Raised when a payment cannot be found."""

    status_code = 404
    code = "payment_not_found"
    title = "Payment Not Found"
    type_suffix = "payment-not-found"

    def default_detail(self) -> str:
        return "The requested payment was not found."


class DuplicateIdempotencyKeyError(AppException):
    """Raised when an idempotency key was already used."""

    status_code = 409
    code = "duplicate_idempotency_key"
    title = "Conflict"
    type_suffix = "duplicate-idempotency-key"

    def default_detail(self) -> str:
        return "A payment with this idempotency key already exists."


class ValidationAppError(AppException):
    """Raised for business-level validation failures."""

    status_code = 422
    code = "validation_error"
    title = "Validation Error"
    type_suffix = "validation-error"

    def default_detail(self) -> str:
        return "The request data is invalid."
