from __future__ import annotations


class GlassnodeProvider:
    def onchain_health(self, assets: list[str]) -> dict[str, str]:
        return {asset: "healthy" for asset in assets}
