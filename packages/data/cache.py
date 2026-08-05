from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime


class TTLCache:
    def __init__(self):
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._items.get(key)
        if not entry or entry.expires_at < datetime.now(timezone.utc):
            self._items.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._items[key] = CacheEntry(value=value, expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))


market_cache = TTLCache()
