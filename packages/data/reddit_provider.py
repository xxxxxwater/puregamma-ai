from __future__ import annotations


class RedditProvider:
    def sentiment(self, assets: list[str]) -> dict[str, str]:
        return {asset: "neutral-positive" for asset in assets}
