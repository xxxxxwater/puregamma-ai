from __future__ import annotations

import urllib.parse
import urllib.request

from apps.api.config import get_settings
from packages.notifications.base import NotificationResult


class TelegramProvider:
    channel = "telegram"

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        settings = get_settings()
        if not settings.telegram_bot_token or recipient.startswith("mock"):
            return NotificationResult(True, self.channel, {"mode": "mock", "chat_id": recipient, "idempotency_key": idempotency_key})
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": recipient, "text": message}).encode()
        with urllib.request.urlopen(url, payload, timeout=8) as response:
            return NotificationResult(True, self.channel, {"status": response.status})
