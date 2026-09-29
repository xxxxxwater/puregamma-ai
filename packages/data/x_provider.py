from __future__ import annotations

from packages.data.provider import ProviderError
from packages.data.x_twitter_provider import XTwitterProvider


class XProvider(XTwitterProvider):
    """Compatibility facade; production ingestion uses XTwitterProvider."""

    def scan_sentiment(self, assets: list[str]) -> dict[str, float]:
        raise ProviderError(
            "legacy_placeholder_disabled",
            "Synthetic X sentiment scoring is disabled; use persisted official-API evidence",
        )
