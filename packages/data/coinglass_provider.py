from __future__ import annotations

from packages.data.provider import ProviderError


class CoinglassProvider:
    """Compatibility facade that refuses to fabricate liquidation data."""

    def liquidations(self, assets: list[str]) -> dict[str, float]:
        raise ProviderError(
            "provider_unavailable",
            "CoinGlass is not connected to a reviewed production adapter",
        )
