from __future__ import annotations

from packages.data.provider import ProviderError


class RedditProvider:
    """Legacy social facade. Synthetic sentiment is forbidden."""

    def sentiment(self, assets: list[str]) -> dict[str, str]:
        raise ProviderError(
            "provider_unavailable",
            "Reddit sentiment is not connected to a reviewed ingestion path",
        )
