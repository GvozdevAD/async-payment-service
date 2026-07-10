"""OpenTelemetry metrics helper tests."""

from unittest.mock import MagicMock, patch

from app.core import metrics as metrics_module
from app.core.metrics import Metrics


def test_init_metrics_disabled_clears_state() -> None:
    """Disabled metrics should reset instrument references."""
    metrics = Metrics()
    metrics.init(enabled=True)
    metrics.init(enabled=False)

    assert metrics.enabled is False


def test_init_metrics_enabled_registers_instruments() -> None:
    """Enabled metrics should create OTel instruments from the meter."""
    mock_meter = MagicMock()
    mock_counter = MagicMock()
    mock_histogram = MagicMock()
    mock_meter.create_counter.return_value = mock_counter
    mock_meter.create_histogram.return_value = mock_histogram
    metrics = Metrics()

    with patch.object(Metrics, "_get_meter", return_value=mock_meter):
        metrics.init(enabled=True)

    assert metrics.enabled is True
    assert mock_meter.create_counter.call_count == 4
    assert mock_meter.create_histogram.call_count == 1
    mock_meter.create_observable_gauge.assert_called_once()


def test_record_payment_created() -> None:
    """Created payments counter should increment with currency label."""
    counter = MagicMock()
    metrics = Metrics()
    metrics._payments_created = counter

    metrics.record_payment_created("RUB")

    counter.add.assert_called_once_with(1, {"currency": "RUB"})


def test_record_payment_processing_duration() -> None:
    """Gateway latency histogram should record seconds."""
    histogram = MagicMock()
    metrics = Metrics()
    metrics._payment_processing_duration = histogram

    metrics.record_payment_processing_duration(1.5)

    histogram.record.assert_called_once_with(1.5)


def test_record_payment_processed() -> None:
    """Processed payments counter should use status labels."""
    counter = MagicMock()
    metrics = Metrics()
    metrics._payments_processed = counter

    metrics.record_payment_processed("succeeded")

    counter.add.assert_called_once_with(1, {"status": "succeeded"})


def test_record_webhook_delivery_and_dlq() -> None:
    """Webhook and DLQ counters should record outcomes."""
    webhook_counter = MagicMock()
    dlq_counter = MagicMock()
    metrics = Metrics()
    metrics._webhook_delivery = webhook_counter
    metrics._messages_dlq = dlq_counter

    metrics.record_webhook_delivery("delivered")
    metrics.record_message_dlq()

    webhook_counter.add.assert_called_once_with(1, {"outcome": "delivered"})
    dlq_counter.add.assert_called_once_with(1)


def test_set_outbox_pending_updates_cache() -> None:
    """Pending outbox gauge cache should store the latest value."""
    metrics = Metrics()
    metrics._enabled = True

    metrics.set_outbox_pending(7)

    assert metrics._outbox_pending_value == 7


def test_set_outbox_pending_ignored_when_disabled() -> None:
    """Pending outbox gauge cache should not change while disabled."""
    metrics = Metrics()

    metrics.set_outbox_pending(9)

    assert metrics._outbox_pending_value == 0


def test_observe_outbox_pending_callback_returns_cached_value() -> None:
    """Observable gauge callback should expose the cached pending count."""
    mock_meter = MagicMock()
    captured_callbacks: list[object] = []

    def capture_gauge(*_args: object, **kwargs: object) -> None:
        captured_callbacks.extend(kwargs["callbacks"])  # type: ignore[arg-type]

    mock_meter.create_observable_gauge.side_effect = capture_gauge
    metrics = Metrics()

    with patch.object(Metrics, "_get_meter", return_value=mock_meter):
        metrics.init(enabled=True)
        metrics.set_outbox_pending(42)

    observations = list(captured_callbacks[0]([]))  # type: ignore[operator]

    assert observations[0].value == 42


def test_metric_helpers_noop_when_disabled() -> None:
    """Metric helpers should not fail when metrics are disabled."""
    metrics_module.init_metrics(enabled=False)

    metrics_module.record_payment_created("RUB")
    metrics_module.record_payment_processed("succeeded")
    metrics_module.record_payment_processing_duration(1.0)
    metrics_module.record_webhook_delivery("delivered")
    metrics_module.record_message_dlq()
    metrics_module.set_outbox_pending(3)

    assert metrics_module.is_metrics_enabled() is False


def test_module_helpers_delegate_to_singleton() -> None:
    """Module-level helpers should delegate to the shared metrics instance."""
    metrics = metrics_module.get_metrics()
    metrics.init(enabled=False)

    metrics_module.init_metrics(enabled=True)
    assert metrics_module.is_metrics_enabled() is True
    assert metrics.enabled is True

    metrics_module.set_outbox_pending(5)
    assert metrics._outbox_pending_value == 5

    metrics_module.init_metrics(enabled=False)
    assert metrics_module.is_metrics_enabled() is False
