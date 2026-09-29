from __future__ import annotations

from packages.data.provider import ProviderError


class GlassnodeProvider:
    """Compatibility facade that refuses to fabricate on-chain health."""

    def onchain_health(self, assets: list[str]) -> dict[str, str]:
        raise ProviderError(
            "provider_unavailable",
            "Glassnode is not connected to a reviewed production adapter",
        )
