from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    provider: str
    response: dict


class NotificationProvider(Protocol):
    channel: str

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        raise NotImplementedError
