"""Database enums and helpers for SQLAlchemy Enum columns."""

from enum import StrEnum


def enum_values(enum: type[StrEnum]) -> list[str]:
    """Return enum member values for SQLAlchemy Enum configuration.

    Args:
        enum: StrEnum class to extract values from.

    Returns:
        List of enum member string values.
    """
    return [member.value for member in enum]


class Currency(StrEnum):
    """Supported payment currencies."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(StrEnum):
    """Payment processing lifecycle status."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    """Outbox event publication status."""

    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
