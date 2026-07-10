"""Payment gateway emulation."""

import asyncio
import logging
import random
from typing import Protocol

from app.core.metrics import (
    record_payment_processed,
    record_payment_processing_duration,
)
from app.core.settings import Settings
from app.db.enums import PaymentStatus
from app.db.models.payment import Payment

logger = logging.getLogger(__name__)


class PaymentGateway(Protocol):
    """External payment gateway contract."""

    async def emulate(self, payment: Payment) -> PaymentStatus:
        """Emulate gateway processing and return the final status.

        Args:
            payment: Payment record being processed.

        Returns:
            Simulated gateway outcome status.
        """


class GatewayEmulator:
    """Emulate external payment gateway latency and success rate."""

    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        self._min_delay = settings.gateway_min_delay_seconds
        self._max_delay = settings.gateway_max_delay_seconds
        self._success_rate = settings.gateway_success_rate
        self._rng = rng or random.Random()

    async def emulate(self, payment: Payment) -> PaymentStatus:
        """Sleep for a random delay and return succeeded or failed.

        Args:
            payment: Payment record being processed by the gateway.

        Returns:
            Simulated gateway outcome status.
        """
        delay = self._rng.uniform(self._min_delay, self._max_delay)
        await asyncio.sleep(delay)

        status = (
            PaymentStatus.SUCCEEDED
            if self._rng.random() < self._success_rate
            else PaymentStatus.FAILED
        )
        logger.info(
            "Gateway emulation finished payment_id=%s delay=%.2fs status=%s",
            payment.id,
            delay,
            status.value,
        )
        record_payment_processing_duration(delay)
        record_payment_processed(status.value)
        return status
