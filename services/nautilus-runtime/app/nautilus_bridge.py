from __future__ import annotations

import platform
import sys
from typing import Any


class NautilusCoreBridge:
    """Optional bridge to NautilusTrader's native clock and MessageBus.

    The runtime remains usable in Mock Exchange mode when the native wheel is
    absent. Production images install the pinned wheel and events are mirrored
    onto Nautilus' MessageBus without copying any upstream source.
    """

    def __init__(self) -> None:
        self.available = False
        self.version: str | None = None
        self.error: str | None = None
        self._message_bus: Any = None
        try:
            import nautilus_trader
            from nautilus_trader.common.component import MessageBus, TestClock
            from nautilus_trader.model.identifiers import TraderId

            self._message_bus = MessageBus(
                trader_id=TraderId("PUREGAMMA-001"),
                clock=TestClock(),
            )
            self.version = getattr(nautilus_trader, "__version__", "unknown")
            self.available = True
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {str(exc)[:180]}"

    def publish(self, topic: str, payload: dict) -> None:
        if not self._message_bus:
            return
        try:
            self._message_bus.publish(topic=topic, msg=payload)
        except Exception as exc:
            self.error = f"publish_failed: {type(exc).__name__}: {str(exc)[:160]}"

    def status(self) -> dict:
        return {
            "available": self.available,
            "version": self.version,
            "messageBus": self._message_bus is not None,
            "error": self.error,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
