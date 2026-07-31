from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from threading import RLock


class RuntimeEventBus:
    def __init__(self, native_bridge=None):
        self._handlers: dict[str, list[Callable[[dict], None]]] = defaultdict(list)
        self._lock = RLock()
        self._native_bridge = native_bridge

    def subscribe(self, event_type: str, handler: Callable[[dict], None]) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event_type: str, payload: dict) -> None:
        if self._native_bridge:
            self._native_bridge.publish(
                f"puregamma.runtime.{event_type.lower()}", payload
            )
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))
        for handler in handlers:
            handler(payload)
