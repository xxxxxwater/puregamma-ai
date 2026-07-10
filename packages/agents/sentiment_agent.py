from __future__ import annotations


class SentimentAgent:
    def aggregate(self, assets: list[str]) -> dict[str, float]:
        return {asset: 0.55 + min(index * 0.03, 0.2) for index, asset in enumerate(assets)}
