from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request

from apps.api.config import get_settings
from packages.notifications.base import NotificationResult
from packages.notifications.imessage.base import IMessageProvider


def sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


class MacOSIMessageRelayClient(IMessageProvider):
    def send_message(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        settings = get_settings()
        if not settings.imessage_relay_secret:
            return NotificationResult(False, self.channel, {"error": "missing_relay_secret"})
        payload = {"recipient": recipient, "message": message, "idempotency_key": idempotency_key}
        body = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = sign_payload(settings.imessage_relay_secret, timestamp, body)
        last_error = None
        for attempt in range(3):
            request = urllib.request.Request(
                f"{settings.imessage_relay_url.rstrip('/')}/send",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-PG-Timestamp": timestamp,
                    "X-PG-Signature": signature,
                    "X-PG-Idempotency-Key": idempotency_key,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    data = json.loads(response.read().decode() or "{}")
                    return NotificationResult(response.status < 300, self.channel, data)
            except Exception as exc:  # pragma: no cover - network failure path is environment-dependent.
                last_error = str(exc)
                if attempt < 2:
                    time.sleep(0.1 * (2**attempt))
        return NotificationResult(False, self.channel, {"error": last_error or "relay_failed"})
