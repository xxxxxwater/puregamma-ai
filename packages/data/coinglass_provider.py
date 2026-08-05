from __future__ import annotations


class CoinglassProvider:
    def liquidations(self, assets: list[str]) -> dict[str, float]:
        return {asset: 0.0 for asset in assets}
