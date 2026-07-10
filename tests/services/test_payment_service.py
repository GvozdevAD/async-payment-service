"""Payment service unit tests."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import PaymentNotFoundError
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.repositories.outbox import OutboxRepository
from app.repositories.payment import PaymentRepository
from app.schemas.payment import PaymentCreateRequest
from app.services.payment import PaymentService


@pytest.fixture
def payment_create_request() -> PaymentCreateRequest:
    """Return a valid payment creation request."""
    return PaymentCreateRequest(
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        metadata={"order_id": "42"},
        webhook_url="https://example.com/webhook",
    )


@pytest.fixture
def payment_service() -> tuple[
    PaymentService, AsyncMock, PaymentRepository, OutboxRepository
]:
    """Return a payment service with mocked session and real repositories."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    payment_repo = PaymentRepository(session)
    outbox_repo = OutboxRepository(session)
    service = PaymentService(session, payment_repo, outbox_repo)
    return service, session, payment_repo, outbox_repo


def _make_payment(
    *,
    payment_id: uuid.UUID | None = None,
    idempotency_key: str = "order-123",
) -> Payment:
    """Build a payment ORM instance for tests."""
    return Payment(
        id=payment_id or uuid.uuid4(),
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        metadata_={"order_id": "42"},
        webhook_url="https://example.com/webhook",
        idempotency_key=idempotency_key,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )


async def test_create_payment_success(
    payment_service: tuple[
        PaymentService, AsyncMock, PaymentRepository, OutboxRepository
    ],
    payment_create_request: PaymentCreateRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Creating a payment should persist payment and outbox records."""
    service, session, payment_repo, outbox_repo = payment_service
    created_payment = _make_payment(idempotency_key="order-new")

    async def fake_get_by_idempotency_key(key: str) -> Payment | None:
        return None

    async def fake_create(payment: Payment) -> Payment:
        payment.id = created_payment.id
        payment.created_at = created_payment.created_at
        payment.status = PaymentStatus.PENDING
        return payment

    monkeypatch.setattr(
        payment_repo, "get_by_idempotency_key", fake_get_by_idempotency_key
    )
    monkeypatch.setattr(payment_repo, "create", fake_create)
    outbox_create = AsyncMock(side_effect=lambda outbox: outbox)
    monkeypatch.setattr(outbox_repo, "create", outbox_create)

    result = await service.create_payment(payment_create_request, "order-new")

    assert result.payment_id == created_payment.id
    assert result.status == PaymentStatus.PENDING
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    outbox_create.assert_awaited_once()
    outbox_record = outbox_create.await_args.args[0]
    assert outbox_record.event_type == "payments.new"
    assert outbox_record.aggregate_id == created_payment.id


async def test_create_payment_idempotent(
    payment_service: tuple[
        PaymentService, AsyncMock, PaymentRepository, OutboxRepository
    ],
    payment_create_request: PaymentCreateRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate idempotency key should return the existing payment."""
    service, session, payment_repo, _outbox_repo = payment_service
    existing = _make_payment(idempotency_key="order-existing")

    monkeypatch.setattr(
        payment_repo,
        "get_by_idempotency_key",
        AsyncMock(return_value=existing),
    )

    result = await service.create_payment(payment_create_request, "order-existing")

    assert result.payment_id == existing.id
    session.commit.assert_not_awaited()


async def test_create_payment_race_integrity(
    payment_service: tuple[
        PaymentService, AsyncMock, PaymentRepository, OutboxRepository
    ],
    payment_create_request: PaymentCreateRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IntegrityError on commit should fall back to the existing payment."""
    service, session, payment_repo, outbox_repo = payment_service
    existing = _make_payment(idempotency_key="order-race")
    calls = {"count": 0}

    async def fake_get_by_idempotency_key(key: str) -> Payment | None:
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return existing

    async def fake_create(payment: Payment) -> Payment:
        payment.id = existing.id
        payment.created_at = existing.created_at
        payment.status = PaymentStatus.PENDING
        return payment

    session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    monkeypatch.setattr(
        payment_repo, "get_by_idempotency_key", fake_get_by_idempotency_key
    )
    monkeypatch.setattr(payment_repo, "create", fake_create)
    monkeypatch.setattr(
        outbox_repo, "create", AsyncMock(side_effect=lambda outbox: outbox)
    )

    result = await service.create_payment(payment_create_request, "order-race")

    assert result.payment_id == existing.id
    session.rollback.assert_awaited_once()


async def test_get_payment_found(
    payment_service: tuple[
        PaymentService, AsyncMock, PaymentRepository, OutboxRepository
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing payment should be returned as a detail response."""
    service, _session, payment_repo, _outbox_repo = payment_service
    payment = _make_payment()
    monkeypatch.setattr(payment_repo, "get_by_id", AsyncMock(return_value=payment))

    result = await service.get_payment(payment.id)

    assert result.payment_id == payment.id
    assert result.amount == payment.amount
    assert result.metadata == payment.metadata_


async def test_create_payment_unexpected_integrity_error_reraises(
    payment_service: tuple[
        PaymentService, AsyncMock, PaymentRepository, OutboxRepository
    ],
    payment_create_request: PaymentCreateRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected IntegrityError should be re-raised after rollback."""
    service, session, payment_repo, outbox_repo = payment_service

    async def fake_get_by_idempotency_key(key: str) -> Payment | None:
        return None

    async def fake_create(payment: Payment) -> Payment:
        payment.id = uuid.uuid4()
        payment.created_at = datetime.now(UTC)
        payment.status = PaymentStatus.PENDING
        return payment

    session.commit.side_effect = IntegrityError("insert", {}, Exception("other"))
    monkeypatch.setattr(
        payment_repo, "get_by_idempotency_key", fake_get_by_idempotency_key
    )
    monkeypatch.setattr(payment_repo, "create", fake_create)
    monkeypatch.setattr(
        outbox_repo, "create", AsyncMock(side_effect=lambda outbox: outbox)
    )

    with pytest.raises(IntegrityError):
        await service.create_payment(payment_create_request, "order-fail")

    session.rollback.assert_awaited_once()


async def test_get_payment_not_found(
    payment_service: tuple[
        PaymentService, AsyncMock, PaymentRepository, OutboxRepository
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing payment should raise PaymentNotFoundError."""
    service, _session, payment_repo, _outbox_repo = payment_service
    monkeypatch.setattr(payment_repo, "get_by_id", AsyncMock(return_value=None))

    with pytest.raises(PaymentNotFoundError):
        await service.get_payment(uuid.uuid4())
