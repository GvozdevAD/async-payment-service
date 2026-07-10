"""Gateway emulator unit tests."""

import random
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.settings import Settings, get_settings
from app.db.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.services.gateway import GatewayEmulator


@pytest.fixture
def payment() -> Payment:
    """Return a pending payment for gateway tests."""
    return Payment(
        amount=Decimal("100.00"),
        currency=Currency.RUB,
        description="Gateway test",
        metadata_={},
        webhook_url="https://example.com/webhook",
        idempotency_key="gateway-test",
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def gateway_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return settings with a fast gateway for tests."""
    monkeypatch.setenv("GATEWAY_MIN_DELAY_SECONDS", "1")
    monkeypatch.setenv("GATEWAY_MAX_DELAY_SECONDS", "2")
    monkeypatch.setenv("GATEWAY_SUCCESS_RATE", "0.9")
    get_settings.cache_clear()
    return get_settings()


async def test_emulate_returns_succeeded_above_threshold(
    gateway_settings,
    payment: Payment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Random below success rate should return succeeded."""
    rng = random.Random()
    monkeypatch.setattr(rng, "random", lambda: 0.89)
    monkeypatch.setattr(rng, "uniform", lambda _a, _b: 1.5)
    monkeypatch.setattr("app.services.gateway.asyncio.sleep", AsyncMock())

    emulator = GatewayEmulator(gateway_settings, rng=rng)
    result = await emulator.emulate(payment)

    assert result == PaymentStatus.SUCCEEDED


async def test_emulate_returns_failed_below_threshold(
    gateway_settings,
    payment: Payment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Random above success rate should return failed."""
    rng = random.Random()
    monkeypatch.setattr(rng, "random", lambda: 0.91)
    monkeypatch.setattr(rng, "uniform", lambda _a, _b: 1.5)
    monkeypatch.setattr("app.services.gateway.asyncio.sleep", AsyncMock())

    emulator = GatewayEmulator(gateway_settings, rng=rng)
    result = await emulator.emulate(payment)

    assert result == PaymentStatus.FAILED


async def test_emulate_sleeps_within_range(
    gateway_settings,
    payment: Payment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway should sleep for the configured delay."""
    rng = random.Random()
    monkeypatch.setattr(rng, "random", lambda: 0.5)
    monkeypatch.setattr(rng, "uniform", lambda _a, _b: 3.25)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.services.gateway.asyncio.sleep", sleep_mock)

    emulator = GatewayEmulator(gateway_settings, rng=rng)
    await emulator.emulate(payment)

    sleep_mock.assert_awaited_once_with(3.25)
