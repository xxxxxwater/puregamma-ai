from __future__ import annotations

from collections.abc import Iterable


# Product entitlements intentionally stay stable ("rss") while storage keeps
# independently observable providers. This lets ChainCatcher have its own
# health, cursor, circuit breaker, and schedule without changing every plan.
DOCUMENT_PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "rss": ("rss", "chaincatcher"),
}


def expand_document_providers(providers: Iterable[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for provider in providers:
        for storage_provider in DOCUMENT_PROVIDER_ALIASES.get(provider, (provider,)):
            if storage_provider not in expanded:
                expanded.append(storage_provider)
    return tuple(expanded)
