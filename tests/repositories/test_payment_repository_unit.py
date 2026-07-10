"""Payment repository unit tests without PostgreSQL."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.repositories.payment import PaymentRepository


def _make_payment() -> Payment:
    """Build a payment ORM instance for repository unit tests."""
    return Payment(
        id=uuid.uuid4(),
        amount="10.00",
        currency=Currency.RUB,
        description="Repository unit test",
        metadata_={},
        webhook_url="https://example.com/webhook",
        idempotency_key=f"repo-unit-{uuid.uuid4()}",
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_get_by_id_returns_payment() -> None:
    """get_by_id should return the scalar result."""
    payment = _make_payment()
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = payment
    session.execute = AsyncMock(return_value=result)
    repo = PaymentRepository(session)

    found = await repo.get_by_id(payment.id)

    assert found == payment
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_idempotency_key_returns_payment() -> None:
    """get_by_idempotency_key should return the scalar result."""
    payment = _make_payment()
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = payment
    session.execute = AsyncMock(return_value=result)
    repo = PaymentRepository(session)

    found = await repo.get_by_idempotency_key(payment.idempotency_key)

    assert found == payment
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_adds_payment_to_session() -> None:
    """create should add the payment to the current session."""
    payment = _make_payment()
    session = AsyncMock(spec=AsyncSession)
    repo = PaymentRepository(session)

    created = await repo.create(payment)

    session.add.assert_called_once_with(payment)
    assert created == payment


@pytest.mark.asyncio
async def test_update_status_executes_update() -> None:
    """update_status should execute an update statement."""
    payment_id = uuid.uuid4()
    processed_at = datetime.now(UTC)
    session = AsyncMock(spec=AsyncSession)
    repo = PaymentRepository(session)

    await repo.update_status(
        payment_id,
        status=PaymentStatus.SUCCEEDED,
        processed_at=processed_at,
    )

    session.execute.assert_awaited_once()
