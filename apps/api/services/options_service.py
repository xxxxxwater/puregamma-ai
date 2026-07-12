from __future__ import annotations

import time
from threading import RLock

from apps.api.config import get_settings
from packages.options.deribit import DeribitPublicProvider, DeribitUnavailable


_cache: dict[str, tuple[float, dict]] = {}
_lock = RLock()


def get_option_chain(currency: str, *, force: bool = False) -> dict:
    settings = get_settings()
    key = currency.upper()
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and not force and cached[0] > now:
            return cached[1]
    provider = DeribitPublicProvider(
        settings.deribit_public_url, settings.deribit_timeout_seconds
    )
    try:
        result = provider.option_chain(key, settings.deribit_detail_limit)
    except DeribitUnavailable as exc:
        result = {
            "provider": provider.provider_name,
            "status": "DEGRADED",
            "currency": key,
            "instruments": [],
            "error": str(exc),
            "live_trading": False,
        }
    with _lock:
        _cache[key] = (now + settings.deribit_cache_ttl_seconds, result)
    return result
