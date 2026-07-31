from __future__ import annotations

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
