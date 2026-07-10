"""Payment ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.enums import Currency, PaymentStatus, enum_values


class Payment(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Payment entity stored for asynchronous processing."""

    __tablename__ = "payments"

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency", values_callable=enum_values),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        insert_default=dict,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=enum_values),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    webhook_url: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
