from __future__ import annotations

from packages.data.x_twitter_provider import XTwitterProvider


class XProvider(XTwitterProvider):
    """Compatibility facade; new ingestion uses XTwitterProvider directly."""

    def scan_sentiment(self, assets: list[str]) -> dict[str, float]:
        return {asset: 0.5 for asset in assets}
