from __future__ import annotations

from abc import ABC, abstractmethod

from packages.notifications.base import NotificationResult


class IMessageProvider(ABC):
    channel = "imessage"

    @abstractmethod
    def send_message(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        raise NotImplementedError

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        return self.send_message(recipient, message, idempotency_key)
