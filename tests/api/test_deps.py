"""API dependency integration tests."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_service
from app.core.constants import PAYMENT_NEW_EVENT_TYPE
from app.core.settings import get_settings
from app.db.enums import Currency, OutboxStatus
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment
from app.schemas.payment import PaymentCreateRequest


@pytest.fixture
def payment_create_request() -> PaymentCreateRequest:
    """Return a valid payment creation request."""
    return PaymentCreateRequest(
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Deps integration",
        metadata={"order_id": "deps"},
        webhook_url="https://example.com/webhook",
    )


async def test_get_payment_service_creates_payment_and_outbox_in_database(
    db_session: AsyncSession,
    payment_create_request: PaymentCreateRequest,
) -> None:
    """Wired PaymentService should persist payment and outbox via real repositories."""
    service = get_payment_service(session=db_session, settings=get_settings())

    result = await service.create_payment(
        payment_create_request, "deps-integration-key"
    )

    payment = await db_session.get(Payment, result.payment_id)
    assert payment is not None
    assert payment.idempotency_key == "deps-integration-key"
    assert payment.status.value == "pending"

    outbox_rows = (
        (
            await db_session.execute(
                select(Outbox).where(Outbox.aggregate_id == result.payment_id),
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox_rows) == 1
    assert outbox_rows[0].event_type == PAYMENT_NEW_EVENT_TYPE
    assert outbox_rows[0].status == OutboxStatus.PENDING
    assert outbox_rows[0].payload["payment_id"] == str(result.payment_id)
