from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from enum import StrEnum


class CapabilityStatus(StrEnum):
    HEALTHY = "HEALTHY"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    NEED_KEY = "NEED_KEY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DISABLED = "DISABLED"
    NOT_LICENSED = "NOT_LICENSED"
    MOCK = "MOCK"
    PLACEHOLDER = "PLACEHOLDER"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"

@dataclass
class Capability:
    capability_name: str
    mode: str
    configured: bool
    enabled: bool
    healthy: bool
    production_allowed: bool
    mock: bool = False
    fallback: bool = False
    status: str = CapabilityStatus.NOT_CONFIGURED
    last_checked_at: str | None = None
    last_success_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def check(self, *, healthy: bool, status: str | None = None, error_code: str | None = None, error_message: str | None = None) -> "Capability":
        now = datetime.now(timezone.utc).isoformat()
        self.last_checked_at = now
        self.healthy = healthy
        self.status = status or (CapabilityStatus.HEALTHY if healthy else CapabilityStatus.FAILED)
        self.error_code, self.error_message = error_code, error_message
        if healthy: self.last_success_at = now
        return self

    def public(self) -> dict:
        return asdict(self)

class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Capability] = {}

    def register(self, capability: Capability) -> Capability:
        self._items[capability.capability_name] = capability
        return capability

    def get(self, name: str) -> Capability | None:
        return self._items.get(name)

    def public(self) -> list[dict]:
        return [item.public() for item in self._items.values()]
