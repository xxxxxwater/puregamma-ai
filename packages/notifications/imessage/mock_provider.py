from __future__ import annotations

from packages.notifications.base import NotificationResult
from packages.notifications.imessage.base import IMessageProvider


class MockIMessageProvider(IMessageProvider):
    def send_message(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        return NotificationResult(
            True,
            self.channel,
            {
                "mode": "mock",
                "recipient": recipient,
                "length": len(message),
                "idempotency_key": idempotency_key,
            },
        )
