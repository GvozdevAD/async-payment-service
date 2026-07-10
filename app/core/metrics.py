"""OpenTelemetry business and technical metrics."""

from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter, Observation

METER_NAME = "async-payment-service"


class Metrics:
    """Application metric instruments backed by an OpenTelemetry meter.

    Encapsulates the process-wide metric state so it can be initialized,
    reset, and exercised in tests without relying on module-level globals.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._payments_created: Counter | None = None
        self._payment_processing_duration: Histogram | None = None
        self._payments_processed: Counter | None = None
        self._webhook_delivery: Counter | None = None
        self._messages_dlq: Counter | None = None
        self._outbox_pending_value = 0

    @property
    def enabled(self) -> bool:
        """Return whether metric recording is enabled."""
        return self._enabled

    def init(self, *, enabled: bool) -> None:
        """(Re)initialize metric instruments.

        Args:
            enabled: Whether metric recording and export are active.
        """
        self._enabled = enabled
        if not enabled:
            self._reset_instruments()
            return

        meter = self._get_meter()
        self._payments_created = meter.create_counter(
            "payments.created",
            description="Created payments",
        )
        self._payment_processing_duration = meter.create_histogram(
            "payment.processing.duration",
            unit="s",
            description="Gateway processing latency",
        )
        self._payments_processed = meter.create_counter(
            "payments.processed",
            description="Processed payments",
        )
        self._webhook_delivery = meter.create_counter(
            "webhook.delivery",
            description="Webhook deliveries",
        )
        self._messages_dlq = meter.create_counter(
            "messages.dlq",
            description="Messages sent to DLQ",
        )
        meter.create_observable_gauge(
            "outbox.pending",
            callbacks=[self._observe_outbox_pending],
            description="Pending outbox records",
        )

    def record_payment_created(self, currency: str) -> None:
        """Increment the created payments counter."""
        if self._payments_created is not None:
            self._payments_created.add(1, {"currency": currency})

    def record_payment_processing_duration(self, seconds: float) -> None:
        """Record gateway processing latency."""
        if self._payment_processing_duration is not None:
            self._payment_processing_duration.record(seconds)

    def record_payment_processed(self, status: str) -> None:
        """Increment processed payments by final status."""
        if self._payments_processed is not None:
            self._payments_processed.add(1, {"status": status})

    def record_webhook_delivery(self, outcome: str) -> None:
        """Increment webhook delivery outcomes."""
        if self._webhook_delivery is not None:
            self._webhook_delivery.add(1, {"outcome": outcome})

    def record_message_dlq(self) -> None:
        """Increment messages rejected to DLQ."""
        if self._messages_dlq is not None:
            self._messages_dlq.add(1)

    def set_outbox_pending(self, count: int) -> None:
        """Update the cached pending outbox gauge value."""
        if self._enabled:
            self._outbox_pending_value = count

    def _reset_instruments(self) -> None:
        self._payments_created = None
        self._payment_processing_duration = None
        self._payments_processed = None
        self._webhook_delivery = None
        self._messages_dlq = None

    def _observe_outbox_pending(
        self,
        _: Iterable[Observation],
    ) -> list[Observation]:
        return [Observation(self._outbox_pending_value)]

    @staticmethod
    def _get_meter() -> Meter:
        return metrics.get_meter(METER_NAME)


_metrics = Metrics()


def get_metrics() -> Metrics:
    """Return the process-wide metrics instance."""
    return _metrics


def init_metrics(*, enabled: bool) -> None:
    """Initialize application metric instruments.

    Args:
        enabled: Whether metric recording and export are active.
    """
    _metrics.init(enabled=enabled)


def is_metrics_enabled() -> bool:
    """Return whether metric recording is enabled."""
    return _metrics.enabled


def record_payment_created(currency: str) -> None:
    """Increment the created payments counter."""
    _metrics.record_payment_created(currency)


def record_payment_processing_duration(seconds: float) -> None:
    """Record gateway processing latency."""
    _metrics.record_payment_processing_duration(seconds)


def record_payment_processed(status: str) -> None:
    """Increment processed payments by final status."""
    _metrics.record_payment_processed(status)


def record_webhook_delivery(outcome: str) -> None:
    """Increment webhook delivery outcomes."""
    _metrics.record_webhook_delivery(outcome)


def record_message_dlq() -> None:
    """Increment messages rejected to DLQ."""
    _metrics.record_message_dlq()


def set_outbox_pending(count: int) -> None:
    """Update the cached pending outbox gauge value."""
    _metrics.set_outbox_pending(count)
