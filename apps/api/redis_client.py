"""Shared process-wide Redis client.

Previously every caller built `Redis.from_url(...)` per request and discarded
it, leaking sockets that only GC pressure would reclaim. redis-py clients are
thread-safe connection pools, so a single module-level instance is both safe
and cheaper.
"""

from __future__ import annotations

from redis import Redis

from apps.api.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client
