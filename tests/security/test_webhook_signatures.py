from __future__ import annotations

import time

from packages.notifications.imessage.webhook_gateway import compute_hmac, verify_hmac_signature


def test_imessage_hmac_valid_and_invalid():
    body = b'{"message":"hello"}'
    timestamp = str(int(time.time()))
    signature = compute_hmac("secret", timestamp, body)

    assert verify_hmac_signature("secret", timestamp, body, signature)
    assert not verify_hmac_signature("secret", timestamp, body, "bad")


def test_imessage_hmac_rejects_replay_timestamp():
    body = b'{"message":"hello"}'
    timestamp = str(int(time.time()) - 1000)
    signature = compute_hmac("secret", timestamp, body)

    assert not verify_hmac_signature("secret", timestamp, body, signature, tolerance_seconds=10)
