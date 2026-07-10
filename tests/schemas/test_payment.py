"""Payment schema validation tests."""

from decimal import Decimal

import pytest

from app.schemas.payment import PaymentCreateRequest


def test_amount_scale_validation_rejects_extra_decimals() -> None:
    """Amount with more than two decimal places should fail custom validation."""
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        PaymentCreateRequest.validate_amount_scale(Decimal("0.001"))
