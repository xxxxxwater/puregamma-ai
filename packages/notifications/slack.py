from __future__ import annotations

import json
import urllib.request

from apps.api.config import get_settings
from packages.notifications.base import NotificationResult


class SlackProvider:
    channel = "slack"

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        settings = get_settings()
        webhook = recipient or settings.slack_webhook_url
        if not webhook or webhook.startswith("mock"):
            return NotificationResult(True, self.channel, {"mode": "mock", "webhook": webhook, "idempotency_key": idempotency_key})
        request = urllib.request.Request(
            webhook,
            data=json.dumps({"text": message}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return NotificationResult(True, self.channel, {"status": response.status})
