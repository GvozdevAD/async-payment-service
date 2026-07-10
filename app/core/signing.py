"""HMAC-SHA256 signing for outbound webhook requests.

Receivers verify authenticity by recomputing the signature over
``f"{timestamp}.".encode() + body`` with the shared secret and comparing it,
in constant time, against the ``v1`` value in the ``X-Webhook-Signature``
header. The timestamp guards against replay attacks.
"""

import hashlib
import hmac

SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"


def sign_payload(secret: str, body: bytes, timestamp: int) -> str:
    """Return the hex HMAC-SHA256 signature for a webhook body.

    Args:
        secret: Shared signing secret.
        body: Exact request body bytes that will be transmitted.
        timestamp: Unix timestamp bound into the signed message.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    signed_message = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), signed_message, hashlib.sha256)
    return digest.hexdigest()


def build_signature_headers(secret: str, body: bytes, timestamp: int) -> dict[str, str]:
    """Build the signature headers for an outbound webhook request.

    Args:
        secret: Shared signing secret.
        body: Exact request body bytes that will be transmitted.
        timestamp: Unix timestamp bound into the signed message.

    Returns:
        Mapping of header names to values, including the versioned signature
        and the standalone timestamp header.
    """
    signature = sign_payload(secret, body, timestamp)
    return {
        SIGNATURE_HEADER: f"t={timestamp},v1={signature}",
        TIMESTAMP_HEADER: str(timestamp),
    }
