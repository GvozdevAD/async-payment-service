"""HMAC webhook signing unit tests."""

import hashlib
import hmac

from app.core.signing import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_signature_headers,
    sign_payload,
)


def test_sign_payload_matches_manual_hmac() -> None:
    """The signature should equal a manually computed HMAC-SHA256."""
    secret = "super-secret-value-32chars-long!"
    body = b'{"payment_id":"abc"}'
    timestamp = 1_700_000_000

    signature = sign_payload(secret, body, timestamp)

    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected


def test_sign_payload_is_deterministic() -> None:
    """Identical inputs should produce identical signatures."""
    secret = "super-secret-value-32chars-long!"
    body = b"payload"
    assert sign_payload(secret, body, 1) == sign_payload(secret, body, 1)


def test_sign_payload_changes_with_timestamp() -> None:
    """A different timestamp should change the signature."""
    secret = "super-secret-value-32chars-long!"
    body = b"payload"
    assert sign_payload(secret, body, 1) != sign_payload(secret, body, 2)


def test_build_signature_headers_shape() -> None:
    """Headers should carry the versioned signature and the timestamp."""
    secret = "super-secret-value-32chars-long!"
    body = b'{"k":"v"}'
    timestamp = 1_700_000_000

    headers = build_signature_headers(secret, body, timestamp)

    signature = sign_payload(secret, body, timestamp)
    assert headers[SIGNATURE_HEADER] == f"t={timestamp},v1={signature}"
    assert headers[TIMESTAMP_HEADER] == str(timestamp)
