from __future__ import annotations

import base64
import hashlib
import hmac
import time


def compute_hmac(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_hmac_signature(secret: str, timestamp: str, body: bytes, signature: str, tolerance_seconds: int = 300) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > tolerance_seconds:
        return False
    expected = compute_hmac(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)


def compute_photon_hmac(secret: str, timestamp: str, body: bytes) -> str:
    """Photon webhook signature: HMAC_SHA256(secret, "v0:{timestamp}:{rawBody}")."""
    signed = f"v0:{timestamp}:".encode() + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def verify_photon_signature(
    secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify the Photon X-Spectrum webhook signature with a five minute
    replay window and constant-time comparison. Accepts the hex digest and,
    for proxies that ship base64 digests, the base64 encoding of the same.
    """
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > tolerance_seconds:
        return False
    expected_hex = compute_photon_hmac(secret, timestamp, body)
    # Photon’s documented wire representation is versioned (`v0=<hex>`).
    # Keep bare-hex compatibility for older proxy deployments while requiring
    # the same MAC over the exact timestamp and raw request body.
    if hmac.compare_digest(f"v0={expected_hex}", signature):
        return True
    if hmac.compare_digest(expected_hex, signature):
        return True
    try:
        expected_b64 = base64.b64encode(bytes.fromhex(expected_hex)).decode()
    except ValueError:
        return False
    return hmac.compare_digest(expected_b64, signature)
